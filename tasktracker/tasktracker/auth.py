import os
import requests
import fastapi as fa

from common.proto.auth import AuthPayload


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
