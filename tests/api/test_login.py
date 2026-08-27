from fastapi.testclient import TestClient

from app.api.membership_dependencies import get_membership_repository
from app.api.user_dependencies import get_user_repository
from app.core.auth import get_password_hash
from app.main import app
from app.repositories.memberships import InMemoryMembershipRepository
from app.repositories.users import InMemoryUserRepository, User

client = TestClient(app)


def install_users(users: dict[str, User]) -> None:
    user_repository = InMemoryUserRepository(users)
    membership_repository = InMemoryMembershipRepository({7: 10})
    app.dependency_overrides[get_user_repository] = lambda: user_repository
    app.dependency_overrides[get_membership_repository] = lambda: membership_repository


def teardown_function() -> None:
    app.dependency_overrides.clear()


def test_valid_credentials_return_bearer_token() -> None:
    install_users(
        {
            "owner@example.com": User(
                id=7,
                email="owner@example.com",
                password_hash=get_password_hash("correct-password"),
            )
        }
    )

    response = client.post(
        "/api/v1/auth/token",
        json={"email": "owner@example.com", "password": "correct-password"},
    )

    assert response.status_code == 200
    assert response.json()["token_type"] == "bearer"
    assert response.json()["access_token"]


def test_wrong_password_and_unknown_email_share_safe_401() -> None:
    install_users(
        {
            "owner@example.com": User(
                id=7,
                email="owner@example.com",
                password_hash=get_password_hash("correct-password"),
            )
        }
    )

    wrong_password = client.post(
        "/api/v1/auth/token",
        json={"email": "owner@example.com", "password": "wrong-password"},
    )
    unknown_email = client.post(
        "/api/v1/auth/token",
        json={"email": "unknown@example.com", "password": "wrong-password"},
    )

    assert wrong_password.status_code == 401
    assert unknown_email.status_code == 401
    assert wrong_password.json() == unknown_email.json()


def test_login_normalizes_email_before_lookup() -> None:
    install_users(
        {
            "owner@example.com": User(
                id=7,
                email="owner@example.com",
                password_hash=get_password_hash("correct-password"),
            )
        }
    )

    response = client.post(
        "/api/v1/auth/token",
        json={"email": "  OWNER@EXAMPLE.COM ", "password": "correct-password"},
    )

    assert response.status_code == 200


def test_user_without_membership_cannot_receive_token() -> None:
    user_repository = InMemoryUserRepository(
        {
            "orphan@example.com": User(
                id=99,
                email="orphan@example.com",
                password_hash=get_password_hash("correct-password"),
            )
        }
    )
    membership_repository = InMemoryMembershipRepository({})
    app.dependency_overrides[get_user_repository] = lambda: user_repository
    app.dependency_overrides[get_membership_repository] = lambda: membership_repository

    response = client.post(
        "/api/v1/auth/token",
        json={"email": "orphan@example.com", "password": "correct-password"},
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "Tenant membership required"}
