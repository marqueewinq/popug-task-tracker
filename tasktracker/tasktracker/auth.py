import os
import requests
import fastapi as fa

from common.proto.auth import AuthNPayload


class AuthZException(Exception):
    """
    Raised when an authentication failed
    """

    pass


def verify_request(
    request: fa.Request, authorization_header_name: str = "Authorization"
) -> AuthNPayload:
    response = requests.post(
        os.path.join(request.app.auth_url, "user/authZ"),
        headers={
            authorization_header_name: request.headers.get(authorization_header_name)
        },
    )
    if response.status_code != 200:
        raise AuthZException(response.json().get("error"))

    return AuthNPayload(**response.json())
