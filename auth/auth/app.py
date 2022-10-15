import datetime as dt
import os
import typing as ty

import fastapi as fa
import jwt
from common import topics
from common.connectors import create_db_client, create_kafka_producer
from common.proto.auth import AuthPayload, AuthRequest, AuthResponse
from common.proto.common import ErrorContent, VersionContent
from fastapi.encoders import jsonable_encoder as to_json
from fastapi.responses import JSONResponse

from auth.models import User
from auth.utils import hexify_secret

DB_HOST = os.environ["DB_HOST"]
DB_PORT = os.environ["DB_PORT"]
DB_USER = os.environ["MONGO_INITDB_ROOT_USERNAME"]
DB_PASS = os.environ["MONGO_INITDB_ROOT_PASSWORD"]
DB_NAME = os.environ["DB_DATABASE"]
AUTHSECRET = os.environ["AUTH_AUTHSECRET"]

KAFKA_PORT = os.environ["KAFKA_PORT"]
KAFKA_SERVER = os.environ["KAFKA_SERVER"]

VERSION = os.environ.get("VERSION")
EXPIRESSECONDS = int(os.environ.get("AUTH_EXPIRESSECONDS", str(30 * 60)))

app = fa.FastAPI(title=str(__package__), version=VERSION)


@app.on_event("startup")
def startup() -> ty.Any:
    app.client = create_db_client(
        f"mongodb://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/?retryWrites=true&w=majority"
    )
    app.db = app.client[DB_NAME]
    app.kafka_producer = create_kafka_producer(f"{KAFKA_SERVER}:{KAFKA_PORT}")


@app.on_event("shutdown")
def shutdown_db_client() -> None:
    app.client.close()
    del app.kafka_producer


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


user_router = fa.APIRouter()


@user_router.get(
    "/users/{user_id}",
    summary="Read user by Public ID",
    status_code=fa.status.HTTP_200_OK,
    response_model=User,
    responses={404: {"model": ErrorContent, "description": "User not found"}},
)
async def read_user(request: fa.Request, user_id: str) -> JSONResponse:
    user_document = request.app.db[User.__name__].find_one({"user_id": user_id})
    if user_document is None:
        return JSONResponse(
            {"error": f"User {user_id} not found"},
            status_code=fa.status.HTTP_404_NOT_FOUND,
        )
    user = User(**user_document)
    user.secret = "***"

    return JSONResponse(content=to_json(user), status_code=fa.status.HTTP_200_OK)


@user_router.post(
    "/users/",
    summary="Create User",
    response_description="User created",
    status_code=fa.status.HTTP_201_CREATED,
    response_model=User,
    responses={409: {"model": ErrorContent, "description": "User already exists"}},
)
async def create_user(request: fa.Request, user: User) -> JSONResponse:
    user = ty.cast(User, hexify_secret(user))
    # TODO: uncomment this check
    # if request.app.db[User.__name__].find_one({"user_id": user.user_id}) is not None:
    #     return JSONResponse(
    #         content={"error": "User already exists."},
    #         status_code=fa.status.HTTP_409_CONFLICT,
    #     )
    request.app.db[User.__name__].insert_one(to_json(user))

    user.secret = "***"
    topics.send_to_topic(
        request.app.kafka_producer,
        topics.USER_CREATED,
        topics.UserCreatedSchema(**to_json(user)),
    )

    return JSONResponse(content=to_json(user), status_code=fa.status.HTTP_201_CREATED)


auth_router = fa.APIRouter()


@auth_router.post(
    "/authenticate",
    summary="Authenticate credentials",
    response_description="User authenticated",
    status_code=fa.status.HTTP_200_OK,
    response_model=AuthResponse,
    responses={404: {"model": ErrorContent, "description": "User not found"}},
)
async def authn(request: fa.Request, auth_request: AuthRequest) -> JSONResponse:
    user_data = request.app.db[User.__name__].find_one(
        to_json(hexify_secret(auth_request))
    )
    if user_data is None:
        return JSONResponse(
            content={"error": "User not found"},
            status_code=fa.status.HTTP_404_NOT_FOUND,
        )
    user = User(**user_data)

    payload = AuthPayload(
        user_id=user.user_id,
        role=user.role,
        expires_at=dt.datetime.utcnow() + dt.timedelta(seconds=EXPIRESSECONDS),
    )
    token = jwt.encode(to_json(payload), AUTHSECRET, algorithm="HS256")

    return JSONResponse(
        content=to_json(AuthResponse(token=token, expires_at=payload.expires_at)),
        status_code=fa.status.HTTP_200_OK,
    )


@auth_router.post(
    "/verify",
    summary="Verify token",
    response_description="Token authorized",
    status_code=fa.status.HTTP_200_OK,
    response_model=AuthPayload,
    responses={
        400: {
            "model": ErrorContent,
            "description": "Token can't be decoded or decoded payload does not match schema",
        },
        401: {
            "model": ErrorContent,
            "description": "Missing authorization header or token expired",
        },
    },
)
async def verify(request: fa.Request):
    auth_header = request.headers.get("authorization")
    if auth_header is None:
        return JSONResponse(
            content={"error": "Missing authorization header"},
            status_code=fa.status.HTTP_401_UNAUTHORIZED,
        )
    token = auth_header.replace("Bearer ", "")
    try:
        decoded = AuthPayload(**jwt.decode(token, AUTHSECRET, algorithms=["HS256"]))
    except jwt.exceptions.DecodeError:  # type: ignore
        return JSONResponse(
            content={"error": "Couldn't decode token"},
            status_code=fa.status.HTTP_400_BAD_REQUEST,
        )
    except AttributeError:
        return JSONResponse(
            content={"error": "Wrong payload type"},
            status_code=fa.status.HTTP_400_BAD_REQUEST,
        )
    if decoded.expires_at <= dt.datetime.utcnow():
        return JSONResponse(
            content={"error": "Token expired"},
            status_code=fa.status.HTTP_401_UNAUTHORIZED,
        )
    return JSONResponse(content=to_json(decoded), status_code=fa.status.HTTP_200_OK)


app.include_router(user_router, tags=["Users"], prefix="/user")
app.include_router(auth_router, tags=["Auth"], prefix="/auth")
