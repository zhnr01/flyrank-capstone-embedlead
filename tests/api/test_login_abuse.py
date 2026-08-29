from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

from app.api.membership_dependencies import get_membership_repository
from app.api.rate_limit_dependencies import reset_rate_limiters
from app.api.user_dependencies import get_user_repository
from app.core.auth import get_password_hash
from app.core.config import settings
from app.main import app
from app.repositories.memberships import InMemoryMembershipRepository
from app.repositories.users import InMemoryUserRepository, User

EMAIL = "owner@acme.example"
PASSWORD = "correct-horse-battery"
TOKEN_URL = "/api/v1/auth/token"

client = TestClient(app)


@pytest.fixture(autouse=True)
def _wiring() -> Generator[None]:
    reset_rate_limiters()
    user = User(id=1, email=EMAIL, password_hash=get_password_hash(PASSWORD))
    app.dependency_overrides[get_user_repository] = lambda: (
        InMemoryUserRepository({EMAIL: user})
    )
    app.dependency_overrides[get_membership_repository] = lambda: (
        InMemoryMembershipRepository({1: 10})
    )
    yield
    app.dependency_overrides.clear()
    reset_rate_limiters()


def attempt(password: str) -> int:
    response = client.post(TOKEN_URL, json={"email": EMAIL, "password": password})
    return int(response.status_code)


def test_repeated_wrong_passwords_are_eventually_throttled() -> None:
    codes = [attempt(f"guess-number-{index}") for index in range(30)]

    assert 429 in codes, f"login was never throttled: {sorted(set(codes))}"


def test_the_throttled_response_advertises_retry_after() -> None:
    for index in range(30):
        response = client.post(
            TOKEN_URL, json={"email": EMAIL, "password": f"guess-{index}"}
        )
        if response.status_code == 429:
            assert response.headers.get("retry-after")
            assert set(response.json()) == {"detail"}
            return
    raise AssertionError("login was never throttled")


def test_the_throttled_body_never_reveals_whether_the_email_exists() -> None:
    for index in range(30):
        response = client.post(
            TOKEN_URL,
            json={"email": "nobody@example.com", "password": f"guess-{index}"},
        )
        if response.status_code == 429:
            body = response.text.lower()
            for leak in ("no such user", "unknown email", "not found", "exists"):
                assert leak not in body
            return
    raise AssertionError("login was never throttled")


def test_a_correct_password_still_works_within_the_budget() -> None:
    assert attempt("wrong-once") == 401
    response = client.post(TOKEN_URL, json={"email": EMAIL, "password": PASSWORD})

    assert response.status_code == 200
    assert response.json()["access_token"]


def test_the_login_budget_is_separate_from_the_submission_budget() -> None:
    for index in range(settings.login_rate_limit_per_ip + 5):
        attempt(f"drain-{index}")

    assert attempt("one-more") == 429

    reset_rate_limiters()

    assert attempt(PASSWORD) == 200
