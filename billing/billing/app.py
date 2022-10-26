import os
import typing as ty

import fastapi as fa
from common.auth import verify_request, AuthPayload
from common.connectors import create_db_client, create_kafka_producer
from common.proto.auth import UserRole
from common.proto.common import ErrorContent, VersionContent
from fastapi.encoders import jsonable_encoder as to_json
from fastapi.responses import JSONResponse

from billing.models import Account, Transaction
from billing.serializers import LastDayMetrics
from billing.utils import create_payroll, create_lastday_metrics

DB_HOST = os.environ["DB_HOST"]
DB_PORT = os.environ["DB_PORT"]
DB_USER = os.environ["MONGO_INITDB_ROOT_USERNAME"]
DB_PASS = os.environ["MONGO_INITDB_ROOT_PASSWORD"]
DB_NAME = os.environ["DB_DATABASE"]
AUTH_URL = os.environ["AUTH_URL"]
SYSTEM_ACCOUNT_USER_ID = os.environ["SYSTEM_ACCOUNT_USER_ID"]

KAFKA_PORT = os.environ["KAFKA_PORT"]
KAFKA_SERVER = os.environ["KAFKA_SERVER"]

VERSION = os.getenv("VERSION")

app = fa.FastAPI(title=str(__package__), version=VERSION)


@app.on_event("startup")
def startup() -> ty.Any:
    app.client = create_db_client(
        f"mongodb://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/?retryWrites=true&w=majority"
    )
    app.db = app.client[DB_NAME]
    app.auth_url = AUTH_URL
    app.kafka_producer = create_kafka_producer(f"{KAFKA_SERVER}:{KAFKA_PORT}")

    create_system_account(app)
    app.system_account_id = SYSTEM_ACCOUNT_USER_ID


def create_system_account(app: fa.FastAPI) -> None:
    if (
        app.db[Account.__name__].find_one({"user_id": SYSTEM_ACCOUNT_USER_ID})
        is not None
    ):
        return
    account = Account(user_id=SYSTEM_ACCOUNT_USER_ID, balance=0.0)
    app.db[Account.__name__].insert_one(to_json(account))


@app.on_event("shutdown")
def shutdown_db_client() -> None:
    app.client.close()


@app.get(
    "/",
    summary="Basic service metadata",
    status_code=fa.status.HTTP_200_OK,
    response_model=VersionContent,
)
async def root() -> dict:
    return JSONResponse(
        content=to_json(VersionContent(version=VERSION)),
        status_code=fa.status.HTTP_200_OK,
    )


account_router = fa.APIRouter()


@account_router.get(
    "/accounts",
    summary="List available accounts",
    response_model=ty.List[Account],
    status_code=fa.status.HTTP_200_OK,
)
async def list_accounts(
    request: fa.Request, auth_payload: AuthPayload = fa.Depends(verify_request)
) -> JSONResponse:
    query: dict
    if auth_payload.role == UserRole.regular:
        query = {"user_id": auth_payload.user_id}
    elif auth_payload.role == UserRole.admin:
        query = {}

    return JSONResponse(
        content=list(
            map(
                lambda x: to_json(Account(**x)),
                request.app.db[Account.__name__].find(query),
            )
        ),
        status_code=fa.status.HTTP_200_OK,
    )


@account_router.get(
    "/accounts/{user_id}/transactions",
    summary="List transactions for an account",
    status_code=fa.status.HTTP_200_OK,
    response_model=ty.List[Transaction],
    responses={
        404: {
            "model": ErrorContent,
            "description": "Account with public ID equal to the given `user_id` not found",
        }
    },
)
async def list_transactions(
    request: fa.Request,
    user_id: str,
    auth_payload: AuthPayload = fa.Depends(verify_request),
) -> JSONResponse:
    account_document: ty.Optional[dict] = None
    if auth_payload.role == UserRole.admin or (
        auth_payload.role == UserRole.regular and auth_payload.user_id == user_id
    ):
        account_document = request.app.db[Account.__name__].find_one(
            {"user_id": user_id}
        )

    if account_document is None:
        return JSONResponse(
            content=to_json(
                ErrorContent(message=f"Account with user_id {user_id} does not exist")
            ),
            status_code=fa.status.HTTP_404_NOT_FOUND,
        )
    account = Account(**account_document)

    return JSONResponse(
        content=list(
            map(
                lambda x: to_json(Transaction(**x)),
                request.app.db[Transaction.__name__].find(
                    {
                        "$or": [
                            {"account_from": account.user_id},
                            {"account_to": account.user_id},
                        ]
                    }
                ),
            )
        ),
        status_code=fa.status.HTTP_200_OK,
    )


@account_router.get(
    "/lastday",
    summary="List last day billing statistics",
    status_code=fa.status.HTTP_200_OK,
    response_model=LastDayMetrics,
    responses={403: {"model": ErrorContent, "description": "Admin role is required"}},
)
async def lastday(
    request: fa.Request, auth_payload: AuthPayload = fa.Depends(verify_request)
) -> JSONResponse:
    if auth_payload.role == UserRole.regular:
        return JSONResponse(
            content=to_json(ErrorContent(message="Admin role is required")),
            status_code=fa.status.HTTP_403_FORBIDDEN,
        )

    return JSONResponse(
        content=to_json(create_lastday_metrics(request)),
        status_code=fa.status.HTTP_200_OK,
    )


@account_router.post(
    "/payroll",
    summary="Pay each popug what he's owed",
    status_code=fa.status.HTTP_200_OK,
    responses={403: {"model": ErrorContent, "description": "Admin role is required"}},
)
async def payroll(
    request: fa.Request, auth_payload: AuthPayload = fa.Depends(verify_request)
) -> JSONResponse:
    if auth_payload.role == UserRole.regular:
        return JSONResponse(
            content=to_json(ErrorContent(message="Admin role is required")),
            status_code=fa.status.HTTP_403_FORBIDDEN,
        )

    create_payroll(request)

    return JSONResponse(content={}, status_code=fa.status.HTTP_200_OK)


app.include_router(account_router, tags=["Accounts"], prefix="/accounts")
