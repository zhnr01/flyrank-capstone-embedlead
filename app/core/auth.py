from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt.exceptions import InvalidTokenError
from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher

from app.core.config import settings

bearer_scheme = HTTPBearer(auto_error=False)
password_hash = PasswordHash((Argon2Hasher(),))
ALGORITHM = "HS256"
BearerCredentials = Annotated[
    HTTPAuthorizationCredentials | None,
    Depends(bearer_scheme),
]


@dataclass(frozen=True)
class Identity:
    user_id: int
    tenant_id: int


demo_identities = {
    "owner-alpha": Identity(user_id=7, tenant_id=10),
    "owner-beta": Identity(user_id=8, tenant_id=20),
}


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


def get_current_identity(
    credentials: BearerCredentials,
) -> Identity:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )

    try:
        subject = verify_access_token(credentials.credentials)
        user_id = int(subject.removeprefix("user-"))
    except (InvalidTokenError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
        ) from None
    identity = next(
        (
            candidate
            for candidate in demo_identities.values()
            if candidate.user_id == user_id
        ),
        None,
    )
    if identity is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
        )
    return identity
