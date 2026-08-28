from collections.abc import Generator
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from app.api.membership_dependencies import get_membership_repository
from app.api.widget_dependencies import get_widget_repository
from app.core.auth import create_access_token
from app.core.config import settings
from app.main import app
from app.repositories.memberships import InMemoryMembershipRepository
from app.repositories.widgets import InMemoryWidgetRepository

client = TestClient(app)


@pytest.fixture(autouse=True)
def widgets() -> Generator[InMemoryWidgetRepository]:
    repository = InMemoryWidgetRepository()
    memberships = InMemoryMembershipRepository({7: 10, 8: 20})
    app.dependency_overrides[get_widget_repository] = lambda: repository
    app.dependency_overrides[get_membership_repository] = lambda: memberships
    yield repository
    app.dependency_overrides.clear()


def token_for(user_id: int) -> str:
    return create_access_token(f"user-{user_id}", timedelta(minutes=5))


def create_widget(user_id: int = 7, name: str = "Contact us") -> int:
    response = client.post(
        "/api/v1/widgets",
        headers={"Authorization": f"Bearer {token_for(user_id)}"},
        json={"name": name, "kind": "contact"},
    )
    return int(response.json()["id"])


def test_public_config_returns_minimal_payload_with_etag() -> None:
    widget_id = create_widget()

    response = client.get(f"/api/v1/public/widgets/{widget_id}/config")

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"widget_id", "name", "kind", "version", "config"}
    assert body["widget_id"] == widget_id
    assert body["name"] == "Contact us"
    assert body["kind"] == "contact"
    assert body["version"] == settings.widget_bundle_version
    assert set(body["config"]) == {
        "title",
        "description",
        "submit_label",
        "theme",
        "fields",
    }
    assert response.headers["etag"].startswith('"')
    assert "max-age" in response.headers["cache-control"]
    assert "must-revalidate" in response.headers["cache-control"]


def test_public_config_never_exposes_tenant_or_internal_fields() -> None:
    widget_id = create_widget()

    body = client.get(f"/api/v1/public/widgets/{widget_id}/config").json()

    for leaked in ("tenant_id", "created_at", "updated_at", "owner", "email"):
        assert leaked not in body


def test_matching_if_none_match_returns_304_without_body() -> None:
    widget_id = create_widget()
    first = client.get(f"/api/v1/public/widgets/{widget_id}/config")
    etag = first.headers["etag"]

    second = client.get(
        f"/api/v1/public/widgets/{widget_id}/config",
        headers={"If-None-Match": etag},
    )

    assert second.status_code == 304
    assert second.content == b""
    assert second.headers["etag"] == etag


def test_stale_if_none_match_returns_200_with_body() -> None:
    widget_id = create_widget()

    response = client.get(
        f"/api/v1/public/widgets/{widget_id}/config",
        headers={"If-None-Match": '"stale-etag"'},
    )

    assert response.status_code == 200
    assert response.json()["widget_id"] == widget_id


def test_etag_changes_when_the_widget_changes() -> None:
    widget_id = create_widget()
    before = client.get(f"/api/v1/public/widgets/{widget_id}/config").headers["etag"]

    client.patch(
        f"/api/v1/widgets/{widget_id}",
        headers={"Authorization": f"Bearer {token_for(7)}"},
        json={"name": "Renamed form"},
    )
    after = client.get(f"/api/v1/public/widgets/{widget_id}/config").headers["etag"]

    assert before != after


def test_unknown_widget_config_returns_404() -> None:
    response = client.get("/api/v1/public/widgets/987654/config")

    assert response.status_code == 404


def test_bundle_is_javascript_with_immutable_cache_headers() -> None:
    version = settings.widget_bundle_version

    response = client.get(f"/api/v1/public/widgets/bundle/{version}/widget.js")

    assert response.status_code == 200
    assert "javascript" in response.headers["content-type"]
    cache_control = response.headers["cache-control"]
    assert "immutable" in cache_control
    assert "max-age=31536000" in cache_control
    assert "data-widget-id" in response.text


def test_unknown_bundle_version_returns_404() -> None:
    response = client.get("/api/v1/public/widgets/bundle/v99/widget.js")

    assert response.status_code == 404


def test_embed_snippet_contains_widget_id_and_versioned_bundle_url() -> None:
    widget_id = create_widget()

    response = client.get(
        f"/api/v1/widgets/{widget_id}/embed",
        headers={"Authorization": f"Bearer {token_for(7)}"},
    )

    assert response.status_code == 200
    body = response.json()
    snippet = body["snippet"]
    assert f'data-widget-id="{widget_id}"' in snippet
    assert f"/bundle/{settings.widget_bundle_version}/widget.js" in snippet
    assert "async" in snippet
    assert snippet.startswith("<script")


def test_embed_snippet_requires_authentication() -> None:
    widget_id = create_widget()

    response = client.get(f"/api/v1/widgets/{widget_id}/embed")

    assert response.status_code == 401


def test_embed_snippet_for_foreign_tenant_returns_404() -> None:
    widget_id = create_widget(user_id=7)

    response = client.get(
        f"/api/v1/widgets/{widget_id}/embed",
        headers={"Authorization": f"Bearer {token_for(8)}"},
    )

    assert response.status_code == 404
