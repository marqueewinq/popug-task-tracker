import os
import typing as ty
import random

import fastapi as fa
from common.proto.auth import UserRole
from fastapi.encoders import jsonable_encoder as to_json
from fastapi.responses import JSONResponse
from pymongo import MongoClient

from tasktracker.auth import AuthZException, verify_request
from tasktracker.models import Issue, User, IssueStatus

DB_HOST = os.environ["DB_HOST"]
DB_PORT = os.environ["DB_PORT"]
DB_USER = os.environ["MONGO_INITDB_ROOT_USERNAME"]
DB_PASS = os.environ["MONGO_INITDB_ROOT_PASSWORD"]
DB_NAME = os.environ["DB_DATABASE"]
AUTH_URL = os.environ["AUTH_URL"]

VERSION = os.getenv("VERSION")

app = fa.FastAPI(title=str(__package__), version=VERSION)


@app.on_event("startup")
def startup() -> ty.Any:
    url = f"mongodb://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/?retryWrites=true&w=majority"
    app.client = MongoClient(url)
    app.db = app.client[DB_NAME]

    app.auth_url = AUTH_URL


@app.on_event("shutdown")
def shutdown_db_client() -> None:
    app.client.close()


@app.get("/")
async def root() -> dict:
    return {"version": VERSION}


issue_router = fa.APIRouter()


@issue_router.get(
    "/issues",
    response_description="List My Issues",
    status_code=fa.status.HTTP_200_OK,
    response_model=Issue,
)
async def issues_list(request: fa.Request) -> JSONResponse:
    try:
        payload = verify_request(request)
    except AuthZException as e:
        return JSONResponse(
            content={"error": str(e)}, status_code=fa.status.HTTP_401_UNAUTHORIZED
        )  # TODO: put this into a decorator

    return JSONResponse(
        content=list(
            request.app.db[Issue.__name__].find({"assignee_id": payload.user_id})
        ),
        status_code=fa.status.HTTP_200_OK,
    )


@issue_router.post(
    "/issues",
    response_description="Create Issue",
    status_code=fa.status.HTTP_201_CREATED,
    response_model=Issue,
)
async def issues_create(request: fa.Request, issue: Issue) -> JSONResponse:
    try:
        verify_request(request)
    except AuthZException as e:
        return JSONResponse(
            content={"error": str(e)}, status_code=fa.status.HTTP_401_UNAUTHORIZED
        )

    issue = request.app.db[Issue.__name__].insert_one(to_json(issue))
    return JSONResponse(
        content={"id": issue.inserted_id}, status_code=fa.status.HTTP_200_OK
    )


@issue_router.put(
    "/issues/{issue_id}/done",
    response_description="Put Issue to Done",
    status_code=fa.status.HTTP_200_OK,
    response_model=Issue,
)
async def issues_mark_done(request: fa.Request, issue_id: str) -> JSONResponse:
    try:
        payload = verify_request(request)
    except AuthZException as e:
        return JSONResponse(
            content={"error": str(e)}, status_code=fa.status.HTTP_401_UNAUTHORIZED
        )

    update_report = request.app.db[Issue.__name__].update_one(
        {"_id": issue_id, "assignee_id": payload.user_id},
        {"$set": {"status": IssueStatus.done.value}},
    )
    if update_report.matched_count == 0:
        return JSONResponse(
            content={"error": f"Issue {issue_id} not found"},
            status_code=fa.status.HTTP_404_NOT_FOUND,
        )
    return JSONResponse(content={}, status_code=fa.status.HTTP_200_OK)


async def shuffle_issues(request: fa.Request, user_id_list: ty.List[str]):
    for issue_document in request.app.db[Issue.__name__].find(
        {"status": IssueStatus.todo.value}
    ):
        assignee_id = random.choice(user_id_list)
        request.app.db[Issue.__name__].update_one(
            {"_id": issue_document["_id"]}, {"$set": {"assignee_id": assignee_id}}
        )


@issue_router.post(
    "/issues/shuffle",
    response_description="Shuffle Issue between Users",
    status_code=fa.status.HTTP_200_OK,
)
async def issues_shuffle(request: fa.Request) -> JSONResponse:
    try:
        payload = verify_request(request)
    except AuthZException as e:
        return JSONResponse(
            content={"error": str(e)}, status_code=fa.status.HTTP_401_UNAUTHORIZED
        )
    if payload.role != UserRole.admin:
        return JSONResponse(
            content={"error": "Only admins can shuffle"},
            status_code=fa.status.HTTP_403_FORBIDDEN,
        )

    user_id_list = [
        user_document["user_id"]
        for user_document in request.app.db[User.__name__].find({})
    ]
    if len(user_id_list) == 0:
        return JSONResponse(
            content={"error": "No users found"}, status_code=fa.status.HTTP_409_CONFLICT
        )

    await shuffle_issues(request, user_id_list)  # async or no?
    return JSONResponse(content={}, status_code=fa.status.HTTP_200_OK)


app.include_router(issue_router, tags=["Task tracker"], prefix="/issues")
