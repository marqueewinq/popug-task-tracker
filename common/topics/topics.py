import typing as ty

from common.proto.auth import UserRole
from pydantic import BaseModel


class Topic(BaseModel):
    name: str
    base_model: ty.Type[BaseModel]

    def __hash__(self):
        return hash(self.name)


# Classes below are intentionally copy-pasted from *.models to reduce coupling


class UserCreatedSchema(BaseModel):
    user_id: str
    role: UserRole
    full_name: str


class IssueOnlyIdSchema(BaseModel):
    issue_id: str


class IssueReassignedSchema(BaseModel):
    assigned_to: str
    assigned_from: ty.Optional[str] = None


USER_CREATED = Topic(name="User.Created.0", base_model=UserCreatedSchema)
ISSUE_CREATED = Topic(name="Issue.Created.0", base_model=IssueOnlyIdSchema)
ISSUE_ASSIGNED = Topic(name="Issue.Assigned.0", base_model=IssueReassignedSchema)
ISSUE_DONE = Topic(name="Issue.MarkedDone.0", base_model=IssueOnlyIdSchema)
