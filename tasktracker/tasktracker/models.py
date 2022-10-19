import enum
from uuid import uuid4

from pydantic import BaseModel, Field


class IssueStatus(enum.Enum):
    todo = "todo"
    done = "done"


class Issue(BaseModel):
    uuid: str = Field(default_factory=uuid4, alias="_id")

    description: str = ""
    jira_id: str = ""
    status: IssueStatus

    assignee_id: str


class User(BaseModel):
    uuid: str = Field(default_factory=uuid4, alias="_id")

    user_id: str
