from datetime import timedelta

from fastapi import APIRouter, HTTPException, status

from app.api.membership_dependencies import MembershipRepositoryDep
from app.api.schemas.auth import TokenRequest, TokenResponse
from app.api.user_dependencies import UserRepositoryDep
from app.core.auth import create_access_token, get_password_hash, verify_password
from app.core.config import settings

router = APIRouter(prefix="/auth", tags=["auth"])
DUMMY_PASSWORD_HASH = get_password_hash("dummy-password-for-unknown-users")


@router.post("/token", response_model=TokenResponse)
def create_token(
    payload: TokenRequest,
    users: UserRepositoryDep,
    memberships: MembershipRepositoryDep,
) -> TokenResponse:
    email = payload.email.strip().lower()
    user = users.get_by_email(email)
    password_hash = user.password_hash if user is not None else DUMMY_PASSWORD_HASH
    password_valid = verify_password(payload.password, password_hash)

    if user is None or not password_valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    if memberships.get_identity_for_user(user.id) is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant membership required",
        )

    token = create_access_token(
        f"user-{user.id}",
        timedelta(minutes=settings.access_token_expire_minutes),
    )
    return TokenResponse(access_token=token)
