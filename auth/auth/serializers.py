import datetime as dt

from pydantic import BaseModel

from auth.models import UserRole


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
