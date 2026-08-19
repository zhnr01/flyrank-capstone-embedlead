from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

from app.api.widget_dependencies import get_widget_repository
from app.main import app
from app.repositories.widgets import InMemoryWidgetRepository, WidgetRepository

client = TestClient(app)


@pytest.fixture(autouse=True)
def widget_repository() -> Generator[WidgetRepository]:
    repository = InMemoryWidgetRepository()
    app.dependency_overrides[get_widget_repository] = lambda: repository
    yield repository
    app.dependency_overrides.clear()


def test_create_widget_requires_authentication() -> None:
    response = client.post(
        "/api/v1/widgets",
        json={"name": "Contact form", "kind": "contact"},
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated"}


def test_authenticated_owner_can_create_and_read_widget() -> None:
    headers = {"Authorization": "Bearer owner-alpha"}
    create_response = client.post(
        "/api/v1/widgets",
        headers=headers,
        json={"name": "Contact form", "kind": "contact"},
    )

    assert create_response.status_code == 201
    widget = create_response.json()
    assert widget["name"] == "Contact form"
    assert widget["kind"] == "contact"
    assert "tenant_id" not in widget

    read_response = client.get(
        f"/api/v1/widgets/{widget['id']}",
        headers=headers,
    )

    assert read_response.status_code == 200
    assert read_response.json() == widget


def test_tenant_cannot_read_another_tenants_widget() -> None:
    first_headers = {"Authorization": "Bearer owner-alpha"}
    second_headers = {"Authorization": "Bearer owner-beta"}

    create_response = client.post(
        "/api/v1/widgets",
        headers=first_headers,
        json={"name": "Private form", "kind": "contact"},
    )
    widget_id = create_response.json()["id"]

    read_response = client.get(
        f"/api/v1/widgets/{widget_id}",
        headers=second_headers,
    )

    assert read_response.status_code == 404
    assert read_response.json() == {"detail": "Widget not found"}


def test_client_cannot_encode_tenant_authority_in_token() -> None:
    response = client.post(
        "/api/v1/widgets",
        headers={"Authorization": "Bearer user-7-tenant-20"},
        json={"name": "Forged form", "kind": "contact"},
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid authentication credentials"}


def test_create_widget_rejects_unsupported_kind() -> None:
    response = client.post(
        "/api/v1/widgets",
        headers={"Authorization": "Bearer owner-alpha"},
        json={"name": "Unsupported form", "kind": "unknown"},
    )

    assert response.status_code == 422
