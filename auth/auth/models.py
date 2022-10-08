import enum
from uuid import uuid4

from pydantic import BaseModel, Field


class UserRole(enum.Enum):
    regular = "regular"
    admin = "admin"


class User(BaseModel):
    uuid: str = Field(default_factory=uuid4, alias="_id")

    user_id: str
    secret: str
    role: UserRole

    full_name: str = ""
