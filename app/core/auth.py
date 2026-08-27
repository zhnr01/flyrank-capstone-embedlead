from datetime import UTC, datetime, timedelta

import jwt
from jwt.exceptions import InvalidTokenError
from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher

from app.core.config import settings

password_hash = PasswordHash((Argon2Hasher(),))
ALGORITHM = "HS256"


def get_password_hash(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, hashed_password: str) -> bool:
    return password_hash.verify(password, hashed_password)


def create_access_token(subject: str, expires_delta: timedelta) -> str:
    expires_at = datetime.now(UTC) + expires_delta
    claims = {"sub": subject, "exp": expires_at}
    return jwt.encode(claims, settings.secret_key, algorithm=ALGORITHM)


def verify_access_token(token: str) -> str:
    claims = jwt.decode(
        token,
        settings.secret_key,
        algorithms=[ALGORITHM],
        options={"require": ["sub", "exp"]},
    )
    subject = claims.get("sub")
    if not isinstance(subject, str) or not subject:
        raise InvalidTokenError("token subject is invalid")
    return subject
