import os
import typing as ty
from functools import wraps

import fastapi as fa
from common import topics
from common.proto.auth import UserRole
from common.proto.common import VersionContent, ErrorContent
from common.connectors import create_kafka_producer
from fastapi.encoders import jsonable_encoder as to_json
from fastapi.responses import JSONResponse
from pymongo import MongoClient

from tasktracker.auth import AuthException, verify_request
from tasktracker.models import Issue, IssueStatus, User
from tasktracker.utils import shuffle_issues

DB_HOST = os.environ["DB_HOST"]
DB_PORT = os.environ["DB_PORT"]
DB_USER = os.environ["MONGO_INITDB_ROOT_USERNAME"]
DB_PASS = os.environ["MONGO_INITDB_ROOT_PASSWORD"]
DB_NAME = os.environ["DB_DATABASE"]
AUTH_URL = os.environ["AUTH_URL"]

KAFKA_PORT = os.environ["KAFKA_PORT"]
KAFKA_SERVER = os.environ["KAFKA_SERVER"]

VERSION = os.getenv("VERSION")

app = fa.FastAPI(
    title=str(__package__),
    version=VERSION,
    # TODO: add auth method to docs
)


@app.on_event("startup")
def startup() -> ty.Any:
    url = f"mongodb://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/?retryWrites=true&w=majority"
    app.client = MongoClient(url)
    app.db = app.client[DB_NAME]

    app.auth_url = AUTH_URL

    app.kafka_producer = create_kafka_producer(f"{KAFKA_SERVER}:{KAFKA_PORT}")


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


issue_router = fa.APIRouter()


def auth_required(func: ty.Callable) -> ty.Callable:
    @wraps(func)
    async def wrapper(
        request: fa.Request, *args: ty.Any, **kwargs: ty.Any
    ) -> JSONResponse:
        try:
            payload = verify_request(request)
        except AuthException as e:
            return JSONResponse(
                content=to_json(ErrorContent(message=str(e))),
                status_code=fa.status.HTTP_401_UNAUTHORIZED,
            )
        request.payload = payload
        return await func(*args, request=request, **kwargs)

    return wrapper


@issue_router.get(
    "/issues",
    summary="List My Issues",
    status_code=fa.status.HTTP_200_OK,
    response_model=Issue,
)
@auth_required
async def issues_list(request: fa.Request) -> JSONResponse:
    return JSONResponse(
        content=list(
            request.app.db[Issue.__name__].find(
                {"assignee_id": request.payload.user_id}
            )
        ),
        status_code=fa.status.HTTP_200_OK,
    )


@issue_router.post(
    "/issues",
    summary="Create Issue",
    response_description="Issue created",
    status_code=fa.status.HTTP_201_CREATED,
    response_model=Issue,
    responses={
        404: {
            "model": ErrorContent,
            "description": "User with public ID equal to the given `assignee_id` not found",
        }
    },
)
@auth_required
async def issues_create(request: fa.Request, issue: Issue) -> JSONResponse:
    user = request.app.db[User.__name__].find_one({"user_id": issue.assignee_id})
    if user is None:
        return JSONResponse(
            to_json(
                ErrorContent(
                    message=f"User with user_id {issue.assignee_id} does not exist"
                )
            ),
            status_code=fa.status.HTTP_404_NOT_FOUND,
        )

    inserted_issue = request.app.db[Issue.__name__].insert_one(to_json(issue))
    returned_data = {"issue_id": inserted_issue.inserted_id}

    request.app.kafka_producer.send(topics.TASK_CREATED, returned_data)

    return JSONResponse(content=returned_data, status_code=fa.status.HTTP_201_CREATED)


@issue_router.put(
    "/issues/{issue_id}/done",
    summary="Put Issue to Done",
    response_description="Updated status to 'done'",
    status_code=fa.status.HTTP_200_OK,
    response_model=Issue,
    responses={404: {"model": ErrorContent, "description": "Issue not found"}},
)
@auth_required
async def issues_mark_done(request: fa.Request, issue_id: str) -> JSONResponse:
    update_report = request.app.db[Issue.__name__].update_one(
        {"_id": issue_id, "assignee_id": request.payload.user_id},
        {"$set": {"status": IssueStatus.done.value}},
    )
    if update_report.matched_count == 0:
        return JSONResponse(
            content=to_json(ErrorContent(message=f"Issue {issue_id} not found")),
            status_code=fa.status.HTTP_404_NOT_FOUND,
        )

    returned_data = {"issue_id": issue_id}

    request.app.kafka_producer.send(topics.TASK_DONE, returned_data)

    return JSONResponse(content=returned_data, status_code=fa.status.HTTP_200_OK)


@issue_router.post(
    "/issues/shuffle",
    summary="Shuffle Issue between Users",
    response_description="Issues' assignees shuffled",
    status_code=fa.status.HTTP_200_OK,
    responses={
        403: {"model": ErrorContent, "description": "Only admins can shuffle"},
        409: {"model": ErrorContent, "description": "No users were found in a service"},
    },
)
@auth_required
async def issues_shuffle(request: fa.Request) -> JSONResponse:
    if request.payload.role != UserRole.admin:
        return JSONResponse(
            content=to_json(ErrorContent(message="Only admins can shuffle")),
            status_code=fa.status.HTTP_403_FORBIDDEN,
        )

    user_id_list = [
        user_document["user_id"]
        for user_document in request.app.db[User.__name__].find({})
    ]
    if len(user_id_list) == 0:
        return JSONResponse(
            content=to_json(ErrorContent(message="No users found")),
            status_code=fa.status.HTTP_409_CONFLICT,
        )

    shuffle_issues(request, user_id_list)
    return JSONResponse(content={}, status_code=fa.status.HTTP_200_OK)


app.include_router(issue_router, tags=["Task tracker"], prefix="/issues")
