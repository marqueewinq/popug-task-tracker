import os
import typing as ty

import fastapi as fa
from common import topics
from common.auth import verify_request, AuthPayload
from common.connectors import create_db_client, create_kafka_producer
from common.proto.auth import UserRole
from common.proto.common import ErrorContent, VersionContent
from fastapi.encoders import jsonable_encoder as to_json
from fastapi.responses import JSONResponse

from tasktracker.models import Issue, IssueStatus, User
from tasktracker.utils import shuffle_issues, split_description_jira_id

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
    app.client = create_db_client(
        f"mongodb://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/?retryWrites=true&w=majority"
    )
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


@issue_router.get(
    "/issues",
    summary="List My Issues",
    status_code=fa.status.HTTP_200_OK,
    response_model=ty.List[Issue],
)
async def issues_list(
    request: fa.Request, auth_payload: AuthPayload = fa.Depends(verify_request)
) -> JSONResponse:
    return JSONResponse(
        content=to_json(
            list(
                map(
                    lambda x: Issue(**x),
                    request.app.db[Issue.__name__].find(
                        {"assignee_id": auth_payload.user_id}
                    ),
                )
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
async def issues_create(
    request: fa.Request,
    issue: Issue,
    auth_payload: AuthPayload = fa.Depends(verify_request),
) -> JSONResponse:
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

    # extract jira_id from desc if popug typed in "[UBERPOPOG-42] -- Change all colors"
    description, jira_id = split_description_jira_id(issue.description)
    issue.description = description
    issue.jira_id = jira_id

    inserted_issue = request.app.db[Issue.__name__].insert_one(to_json(issue))
    issue.uuid = inserted_issue.inserted_id

    topics.send_to_topic(
        request.app.kafka_producer,
        topics.ISSUE_CREATED,
        topics.IssueAssignedSchema(
            issue_id=inserted_issue.inserted_id, assignee_id=issue.assignee_id
        ),
    )
    return JSONResponse(content=to_json(issue), status_code=fa.status.HTTP_201_CREATED)


@issue_router.post(
    "/issues/{issue_id}/done",
    summary="Mark Issue as Done",
    response_description="Updated status to 'done'",
    status_code=fa.status.HTTP_200_OK,
    response_model=Issue,  # TODO: update docs
    responses={404: {"model": ErrorContent, "description": "Issue not found"}},
)
async def issues_mark_done(
    request: fa.Request,
    issue_id: str,
    auth_payload: AuthPayload = fa.Depends(verify_request),
) -> JSONResponse:
    update_report = request.app.db[Issue.__name__].update_one(
        {"_id": issue_id, "assignee_id": auth_payload.user_id},
        {"$set": {"status": IssueStatus.done.value}},
    )
    if update_report.matched_count == 0:
        return JSONResponse(
            content=to_json(ErrorContent(message=f"Issue {issue_id} not found")),
            status_code=fa.status.HTTP_404_NOT_FOUND,
        )

    returned_data = {"issue_id": issue_id}

    topics.send_to_topic(
        request.app.kafka_producer,
        topics.ISSUE_DONE,
        topics.IssueAssignedSchema(**returned_data, assignee_id=auth_payload.user_id),
    )

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
async def issues_shuffle(
    request: fa.Request, auth_payload: AuthPayload = fa.Depends(verify_request)
) -> JSONResponse:
    if auth_payload.role != UserRole.admin:
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
