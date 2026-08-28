from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from httpx import Response

from app.api.membership_dependencies import get_membership_repository
from app.api.rate_limit_dependencies import reset_rate_limiters
from app.api.widget_dependencies import get_widget_repository
from app.core.config import settings
from app.core.identity import Identity
from app.core.widget_config import CONTACT_KIND, default_config
from app.main import app
from app.repositories.memberships import InMemoryMembershipRepository
from app.repositories.widgets import InMemoryWidgetRepository

TENANT_ID = 10
USER_ID = 7
ORIGIN = "http://localhost:5500"

FORBIDDEN_FRAGMENTS = (
    "psycopg",
    "sqlalchemy",
    "postgresql",
    "OperationalError",
    "ProgrammingError",
    "IntegrityError",
    "SELECT ",
    "INSERT ",
    "UPDATE ",
    "[SQL:",
    "Traceback",
    "File \"",
    "site-packages",
    ".venv",
    "app/core/",
    "app\\core\\",
    "app/repositories/",
    "secret_key",
    "SECRET_KEY",
    "POSTGRES_PASSWORD",
    "metrics_token",
    "statement_timeout",
    "SubmissionRecord",
    "WidgetRecord",
    "Session",
    "sqlalche.me",
)


client = TestClient(app)


def get_path(path: str) -> Response:
    result: Response = client.get(path)
    return result


@pytest.fixture(autouse=True)
def _wiring() -> Generator[None]:
    reset_rate_limiters()
    widgets = InMemoryWidgetRepository()
    widgets.create(
        identity=Identity(user_id=USER_ID, tenant_id=TENANT_ID),
        name="Contact",
        kind=CONTACT_KIND,
        config=default_config(),
    )
    app.dependency_overrides[get_widget_repository] = lambda: widgets
    app.dependency_overrides[get_membership_repository] = lambda: (
        InMemoryMembershipRepository({USER_ID: TENANT_ID})
    )
    yield
    app.dependency_overrides.clear()
    reset_rate_limiters()


def assert_no_internal_detail(body: str, label: str) -> None:
    for fragment in FORBIDDEN_FRAGMENTS:
        assert fragment not in body, f"{label} leaked {fragment!r}: {body[:400]}"


def test_unknown_widget_404_body_is_opaque() -> None:
    response = get_path("/api/v1/public/widgets/999999/config")

    assert response.status_code == 404
    assert_no_internal_detail(response.text, "404 config")


def test_bad_bundle_version_404_body_is_opaque() -> None:
    for version in ("v1", "v2%00", "..\\..\\main", "../../etc/passwd"):
        response = get_path(f"/api/v1/public/widgets/bundle/{version}/widget.js")

        assert response.status_code == 404
        assert_no_internal_detail(response.text, f"bundle {version}")


def test_oversized_submission_413_body_is_opaque() -> None:
    response = client.post(
        "/api/v1/public/widgets/1/submissions",
        headers={"Content-Type": "application/json", "Origin": ORIGIN},
        content=b'{"email":"a@b.co","name":"' + b"x" * 20_000 + b'"}',
    )

    assert response.status_code == 413
    assert_no_internal_detail(response.text, "413")


def test_invalid_submission_422_body_is_opaque() -> None:
    bodies: list[dict[str, object]] = [
        {"email": "not-an-email", "name": "V"},
        {"email": {"nested": "object"}, "name": "V"},
        {"email": ["a", "list"], "name": "V"},
        {"email": "a@b.co", "name": "V", "'; DROP TABLE submissions; --": "x"},
        {"email": "a@b.co", "name": "V", "__class__": "x"},
    ]
    for body in bodies:
        response = client.post(
            "/api/v1/public/widgets/1/submissions",
            headers={"Origin": ORIGIN},
            json=body,
        )

        assert response.status_code == 422
        assert_no_internal_detail(response.text, f"422 {list(body)}")


def test_malformed_json_body_is_opaque() -> None:
    for raw in (b"{not json", b"[]", b'"a string"', b"null", b"123"):
        response = client.post(
            "/api/v1/public/widgets/1/submissions",
            headers={"Content-Type": "application/json", "Origin": ORIGIN},
            content=raw,
        )

        assert response.status_code == 422
        assert_no_internal_detail(response.text, f"malformed {raw!r}")


def test_unauthenticated_dashboard_body_is_opaque() -> None:
    for path in ("/api/v1/widgets", "/api/v1/dashboard/stats"):
        response = get_path(path)

        assert response.status_code == 401
        assert_no_internal_detail(response.text, f"401 {path}")


def test_malformed_token_body_never_names_the_jwt_failure() -> None:
    for token in ("garbage", "a.b.c", "", "Bearer"):
        response = client.get(
            "/api/v1/widgets", headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 401
        body = response.text
        assert_no_internal_detail(body, f"token {token!r}")
        for jwt_word in ("Signature", "algorithm", "HS256", "claim", "expired", "jwt"):
            assert jwt_word not in body, f"{token!r} leaked {jwt_word}"


def test_gated_metrics_body_is_opaque() -> None:
    response = get_path("/api/v1/system/metrics")

    assert response.status_code in {401, 404}
    assert_no_internal_detail(response.text, "metrics")


def test_every_error_body_is_a_detail_only_object() -> None:
    response = client.post(
        "/api/v1/public/widgets/999999/submissions",
        headers={"Origin": ORIGIN},
        json={"email": "a@b.co", "name": "V"},
    )

    assert response.status_code == 404
    assert set(response.json()) == {"detail"}


def test_rate_limited_429_body_is_opaque() -> None:
    body = {"email": "a@b.co", "name": "V"}
    statuses = set()
    for _ in range(settings.submission_rate_limit_per_ip + 3):
        response = client.post(
            "/api/v1/public/widgets/1/submissions",
            headers={"Origin": ORIGIN},
            json=body,
        )
        statuses.add(response.status_code)
        assert_no_internal_detail(response.text, f"{response.status_code} burst")

    assert 429 in statuses
