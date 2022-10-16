import os
import typing as ty
from functools import wraps

import fastapi as fa
import requests
from fastapi.encoders import jsonable_encoder as to_json
from fastapi.responses import JSONResponse

from common.proto.auth import AuthPayload
from common.proto.common import ErrorContent


class AuthException(Exception):
    """
    Raised when an authentication failed
    """

    pass


def verify_request(
    request: fa.Request, authorization_header_name: str = "Authorization"
) -> AuthPayload:
    response = requests.post(
        os.path.join(request.app.auth_url, "auth/verify"),
        headers={
            authorization_header_name: request.headers.get(authorization_header_name)
        },
    )
    if response.status_code != 200:
        raise AuthException(response.json().get("error"))

    return AuthPayload(**response.json())


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
        request.auth_payload = payload
        return await func(*args, request=request, **kwargs)

    return wrapper
