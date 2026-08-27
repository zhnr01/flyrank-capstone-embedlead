from collections.abc import Generator
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from app.api.membership_dependencies import get_membership_repository
from app.api.widget_dependencies import get_widget_repository
from app.core.auth import create_access_token
from app.main import app
from app.repositories.memberships import InMemoryMembershipRepository
from app.repositories.widgets import InMemoryWidgetRepository, WidgetRepository

client = TestClient(app)


def auth_headers(user_id: int) -> dict[str, str]:
    token = create_access_token(f"user-{user_id}", timedelta(minutes=5))
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(autouse=True)
def widget_repository() -> Generator[WidgetRepository]:
    repository = InMemoryWidgetRepository()
    membership_repository = InMemoryMembershipRepository({7: 10, 8: 20})
    app.dependency_overrides[get_widget_repository] = lambda: repository
    app.dependency_overrides[get_membership_repository] = lambda: membership_repository
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
    headers = auth_headers(7)
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
    first_headers = auth_headers(7)
    second_headers = auth_headers(8)

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


def test_unsigned_demo_credential_is_rejected() -> None:
    response = client.post(
        "/api/v1/widgets",
        headers={"Authorization": "Bearer owner-alpha"},
        json={"name": "Unsigned form", "kind": "contact"},
    )

    assert response.status_code == 401


def test_authenticated_user_without_membership_is_forbidden() -> None:
    response = client.post(
        "/api/v1/widgets",
        headers=auth_headers(999),
        json={"name": "No tenant", "kind": "contact"},
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "Tenant membership required"}


def test_create_widget_rejects_unsupported_kind() -> None:
    response = client.post(
        "/api/v1/widgets",
        headers=auth_headers(7),
        json={"name": "Unsupported form", "kind": "unknown"},
    )

    assert response.status_code == 422


def test_owner_lists_only_its_widgets_newest_first() -> None:
    first = client.post(
        "/api/v1/widgets",
        headers=auth_headers(7),
        json={"name": "First", "kind": "contact"},
    ).json()
    second = client.post(
        "/api/v1/widgets",
        headers=auth_headers(7),
        json={"name": "Second", "kind": "contact"},
    ).json()
    client.post(
        "/api/v1/widgets",
        headers=auth_headers(8),
        json={"name": "Foreign", "kind": "contact"},
    )

    response = client.get("/api/v1/widgets", headers=auth_headers(7))

    assert response.status_code == 200
    assert [widget["id"] for widget in response.json()["data"]] == [
        second["id"],
        first["id"],
    ]


def test_widget_list_uses_cursor_without_duplicates() -> None:
    ids = [
        client.post(
            "/api/v1/widgets",
            headers=auth_headers(7),
            json={"name": f"Widget {number}", "kind": "contact"},
        ).json()["id"]
        for number in range(3)
    ]

    first_page = client.get(
        "/api/v1/widgets?limit=2",
        headers=auth_headers(7),
    ).json()
    second_page = client.get(
        f"/api/v1/widgets?limit=2&after_id={first_page['next_after_id']}",
        headers=auth_headers(7),
    ).json()

    returned = [widget["id"] for widget in first_page["data"] + second_page["data"]]
    assert returned == sorted(ids, reverse=True)
    assert len(returned) == len(set(returned))


def test_patch_changes_only_supplied_widget_fields() -> None:
    widget = client.post(
        "/api/v1/widgets",
        headers=auth_headers(7),
        json={"name": "Before", "kind": "contact"},
    ).json()

    response = client.patch(
        f"/api/v1/widgets/{widget['id']}",
        headers=auth_headers(7),
        json={"name": "After"},
    )

    assert response.status_code == 200
    assert response.json() == {**widget, "name": "After"}


def test_foreign_tenant_cannot_patch_widget() -> None:
    widget = client.post(
        "/api/v1/widgets",
        headers=auth_headers(7),
        json={"name": "Private", "kind": "contact"},
    ).json()

    response = client.patch(
        f"/api/v1/widgets/{widget['id']}",
        headers=auth_headers(8),
        json={"name": "Stolen"},
    )

    assert response.status_code == 404


def test_delete_removes_widget_for_owner() -> None:
    widget = client.post(
        "/api/v1/widgets",
        headers=auth_headers(7),
        json={"name": "Delete me", "kind": "contact"},
    ).json()

    deleted = client.delete(
        f"/api/v1/widgets/{widget['id']}",
        headers=auth_headers(7),
    )
    missing = client.get(
        f"/api/v1/widgets/{widget['id']}",
        headers=auth_headers(7),
    )

    assert deleted.status_code == 204
    assert missing.status_code == 404
