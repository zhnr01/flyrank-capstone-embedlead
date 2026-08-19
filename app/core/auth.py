from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

bearer_scheme = HTTPBearer(auto_error=False)
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


def get_current_identity(
    credentials: BearerCredentials,
) -> Identity:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )

    identity = demo_identities.get(credentials.credentials)
    if identity is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
        )
    return identity
