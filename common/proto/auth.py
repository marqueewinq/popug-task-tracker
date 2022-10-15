import enum
import datetime as dt

from pydantic import BaseModel


class UserRole(enum.Enum):
    regular = "regular"
    admin = "admin"


class AuthRequest(BaseModel):
    user_id: str
    secret: str


class AuthPayload(BaseModel):
    user_id: str
    role: UserRole
    expires_at: dt.datetime


class AuthResponse(BaseModel):
    token: str
    expires_at: dt.datetime
