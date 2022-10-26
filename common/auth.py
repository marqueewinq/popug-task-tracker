import os

import fastapi as fa
import requests

from common.proto.auth import AuthPayload


async def verify_request(request: fa.Request) -> AuthPayload:
    authorization_header_name = "Authorization"

    response = requests.post(
        os.path.join(request.app.auth_url, "auth/verify"),
        headers={
            authorization_header_name: request.headers.get(authorization_header_name)
        },
    )
    if response.status_code != 200:
        raise fa.HTTPException(
            status_code=fa.status.HTTP_401_UNAUTHORIZED,
            detail=response.json().get("error"),
            headers={"WWW-Authenticate": "Bearer"},
        )

    return AuthPayload(**response.json())
