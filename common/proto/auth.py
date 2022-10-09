import enum
import datetime as dt

from pydantic import BaseModel


class UserRole(enum.Enum):
    regular = "regular"
    admin = "admin"


class AuthNRequest(BaseModel):
    user_id: str
    secret: str


class AuthNPayload(BaseModel):
    user_id: str
    role: UserRole
    expires_at: dt.datetime


class AuthNResponse(BaseModel):
    token: str
    expires_at: dt.datetime
