import datetime as dt
import os
import logging
import typing as ty
import json
from time import sleep

import fastapi as fa
import kafka
import jwt
from common import topics
from common.proto.auth import AuthPayload, AuthRequest, AuthResponse
from fastapi.encoders import jsonable_encoder as to_json
from fastapi.responses import JSONResponse
from pymongo import MongoClient

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
    url = f"mongodb://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/?retryWrites=true&w=majority"
    app.client = MongoClient(url)
    app.db = app.client[DB_NAME]

    for delay in range(10):
        try:
            app.kafka_producer = kafka.KafkaProducer(
                bootstrap_servers=f"{KAFKA_SERVER}:{KAFKA_PORT}",
                value_serializer=lambda v: json.dumps(v).encode("utf-8"),
                linger_ms=100,
            )
        except kafka.errors.NoBrokersAvailable:
            logging.info(f"No brokers available, retrying in {delay} seconds")
            sleep(delay)
    assert hasattr(app, "kafka_producer"), "Couldn't connect to Kafka"


@app.on_event("shutdown")
def shutdown_db_client() -> None:
    app.client.close()
    del app.kafka_producer


@app.get("/")
async def root() -> dict:
    return {"version": VERSION}


user_router = fa.APIRouter()


@user_router.get(
    "/users/{user_id}",
    summary="Read user by Public ID",
    status_code=fa.status.HTTP_200_OK,
    response_model=User,
)
async def read_user(request: fa.Request, user_id: str) -> JSONResponse:
    user_document = request.app.db[User.__name__].find_one({"user_id": user_id})
    if user_document is None:
        return JSONResponse(
            {"error": "User not found"}, status_code=fa.status.HTTP_404_NOT_FOUND
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
)
async def create_user(request: fa.Request, user: User) -> JSONResponse:
    user = ty.cast(User, hexify_secret(user))
    if request.app.db[User.__name__].find_one({"user_id": user.user_id}) is not None:
        return JSONResponse(
            content={"error": "User already exists."},
            status_code=fa.status.HTTP_409_CONFLICT,
        )
    request.app.db[User.__name__].insert_one(to_json(user))

    user.secret = "***"
    app.kafka_producer.send(topics.USER_CREATED, to_json(user))

    return JSONResponse(content=to_json(user), status_code=fa.status.HTTP_201_CREATED)


auth_router = fa.APIRouter()


@auth_router.post(
    "/authenticate",
    summary="Authenticate credentials",
    response_description="User authenticated",
    status_code=fa.status.HTTP_200_OK,
    response_model=AuthResponse,
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
