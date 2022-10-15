import typing as ty
from pydantic import BaseModel


class VersionContent(BaseModel):
    version: ty.Optional[str]


class ErrorContent(BaseModel):
    message: str
