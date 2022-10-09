import datetime as dt
import os
import typing as ty

import fastapi as fa
import jwt
from common.proto.auth import AuthNPayload, AuthNRequest, AuthNResponse
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

VERSION = os.environ.get("VERSION")
EXPIRESSECONDS = int(os.environ.get("AUTH_EXPIRESSECONDS", str(30 * 60)))

app = fa.FastAPI(title=str(__package__), version=VERSION)


@app.on_event("startup")
def startup() -> ty.Any:
    url = f"mongodb://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/?retryWrites=true&w=majority"
    app.client = MongoClient(url)
    app.db = app.client[DB_NAME]


@app.on_event("shutdown")
def shutdown_db_client() -> None:
    app.client.close()


@app.get("/")
async def root() -> dict:
    return {"version": VERSION}


user_router = fa.APIRouter()


@user_router.get(
    "/users/{user_id}",
    response_description="Read user by ID",
    status_code=fa.status.HTTP_200_OK,
    response_model=User,
)
async def read_user(request: fa.Request, user_id: str) -> JSONResponse:
    user_account = request.app.db[User.__name__].find_one({"uuid": user_id})
    return JSONResponse(content=user_account, status_code=fa.status.HTTP_200_OK)


@user_router.post(
    "/users/",
    response_description="Create User",
    status_code=fa.status.HTTP_201_CREATED,
    response_model=User,
)
async def create_user(request: fa.Request, user: User) -> JSONResponse:
    user = ty.cast(User, hexify_secret(user))
    request.app.db[User.__name__].insert_one(to_json(user))
    return JSONResponse(content=to_json(user), status_code=fa.status.HTTP_201_CREATED)


@user_router.post(
    "/authN",
    response_description="AuthN",
    status_code=fa.status.HTTP_200_OK,
    response_model=AuthNResponse,
)
async def authn(request: fa.Request, authn_request: AuthNRequest) -> JSONResponse:
    user_data = request.app.db[User.__name__].find_one(
        to_json(hexify_secret(authn_request))
    )
    if user_data is None:
        return JSONResponse(
            content={"error": "User not found"},
            status_code=fa.status.HTTP_404_NOT_FOUND,
        )

    user = User(**user_data)

    payload = AuthNPayload(
        user_id=user.user_id,
        role=user.role,
        expires_at=dt.datetime.utcnow() + dt.timedelta(seconds=EXPIRESSECONDS),
    )
    token = jwt.encode(to_json(payload), AUTHSECRET, algorithm="HS256")

    return JSONResponse(
        content=to_json(AuthNResponse(token=token, expires_at=payload.expires_at)),
        status_code=fa.status.HTTP_200_OK,
    )


@user_router.post(
    "/authZ",
    response_description="AuthZ",
    status_code=fa.status.HTTP_200_OK,
    response_model=AuthNPayload,
)
async def authz(request: fa.Request):
    auth_header = request.headers.get("authorization")
    if auth_header is None:
        return JSONResponse(
            content={"error": "Missing authorization header"},
            status_code=fa.status.HTTP_401_UNAUTHORIZED,
        )
    token = auth_header.replace("Bearer ", "")
    try:
        decoded = AuthNPayload(**jwt.decode(token, AUTHSECRET, algorithms=["HS256"]))
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
    return JSONResponse(content=to_json(decoded), status_code=fa.status.HTTP_200_OK)


app.include_router(user_router, tags=["Auth"], prefix="/user")
