import hashlib
import typing as ty


class HasSecret(ty.Protocol):
    secret: str


def hexify_secret(entity: HasSecret) -> HasSecret:
    entity.secret = hashlib.sha1(bytes(entity.secret, "utf-8")).hexdigest()
    return entity
