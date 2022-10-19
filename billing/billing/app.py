import datetime as dt
import os
import typing as ty

import fastapi as fa
from common.auth import auth_required
from common.connectors import create_db_client, create_kafka_producer
from common.proto.auth import UserRole
from common.proto.common import ErrorContent, VersionContent
from fastapi.encoders import jsonable_encoder as to_json
from fastapi.responses import JSONResponse

from billing.models import Account, LastDayMetrics, Transaction

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
    response_model=Account,
    status_code=fa.status.HTTP_200_OK,
)
@auth_required
async def list_accounts(request: fa.Request) -> JSONResponse:
    query: dict
    if request.auth_payload.role == UserRole.regular:
        query = {"user_id": request.auth_payload.user_id}
    elif request.auth_payload.role == UserRole.admin:
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
    response_model=Transaction,
    responses={
        404: {
            "model": ErrorContent,
            "description": "Account with public ID equal to the given `user_id` not found",
        }
    },
)
@auth_required
async def list_transactions(request: fa.Request, user_id: str) -> JSONResponse:
    account_document: ty.Optional[dict] = None
    if request.auth_payload.role == UserRole.admin or (
        request.auth_payload.role == UserRole.regular
        and request.auth_payload.user_id == user_id
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
@auth_required
async def lastday(request: fa.Request) -> JSONResponse:
    if request.auth_payload.role == UserRole.regular:
        return JSONResponse(
            content=to_json(ErrorContent(message="Admin role is required")),
            status_code=fa.status.HTTP_403_FORBIDDEN,
        )

    date = dt.datetime.combine(dt.date.today(), dt.datetime.min.time())
    total_amount_gained: float = 0.0
    for transaction_document in request.app.db[Transaction.__name__].find(
        {
            "created_at": {"$gte": date.isoformat()},
            "$or": [
                {"account_from": app.system_account_id},
                {"account_to": app.system_account_id},
            ],
        }
    ):
        transaction = Transaction(**transaction_document)
        if transaction.account_from == app.system_account_id:
            total_amount_gained -= transaction.amount
        elif transaction.account_to == app.system_account_id:
            total_amount_gained += transaction.amount

    return JSONResponse(
        content=to_json(
            LastDayMetrics(date=date, total_amount_gained=total_amount_gained)
        ),
        status_code=fa.status.HTTP_200_OK,
    )


app.include_router(account_router, tags=["Accounts"], prefix="/accounts")
