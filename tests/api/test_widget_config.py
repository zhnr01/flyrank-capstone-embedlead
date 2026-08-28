import json
from collections.abc import Generator
from datetime import timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from httpx import Response

from app.api.membership_dependencies import get_membership_repository
from app.api.widget_dependencies import get_widget_repository
from app.core.auth import create_access_token
from app.main import app
from app.repositories.memberships import InMemoryMembershipRepository
from app.repositories.widgets import InMemoryWidgetRepository

TENANT_ID = 10
USER_ID = 7
MAX_FIELDS = 12

client = TestClient(app)


@pytest.fixture(autouse=True)
def _wiring() -> Generator[None]:
    widgets = InMemoryWidgetRepository()
    memberships = InMemoryMembershipRepository({USER_ID: TENANT_ID})
    app.dependency_overrides[get_widget_repository] = lambda: widgets
    app.dependency_overrides[get_membership_repository] = lambda: memberships
    yield
    app.dependency_overrides.clear()


def auth_headers() -> dict[str, str]:
    token = create_access_token(f"user-{USER_ID}", timedelta(minutes=5))
    return {"Authorization": f"Bearer {token}"}


ConfigDict = dict[str, Any]
FieldDict = dict[str, Any]


def valid_config() -> ConfigDict:
    return {
        "title": "Talk to sales",
        "description": "We reply within one business day.",
        "submit_label": "Send it",
        "theme": "dark",
        "fields": [
            {"name": "email", "label": "Work email", "kind": "email", "required": True},
            {"name": "name", "label": "Your name", "kind": "text", "required": True},
            {
                "name": "message",
                "label": "How can we help?",
                "kind": "textarea",
                "required": False,
            },
        ],
    }


def create_widget(config: object) -> Response:
    result: Response = client.post(
        "/api/v1/widgets",
        headers=auth_headers(),
        json={"name": "Contact", "kind": "contact", "config": config},
    )
    return result


def test_widget_can_be_created_with_a_display_config() -> None:
    response = create_widget(valid_config())

    assert response.status_code == 201
    body = response.json()
    assert body["config"]["title"] == "Talk to sales"
    assert body["config"]["submit_label"] == "Send it"
    assert [field["name"] for field in body["config"]["fields"]] == [
        "email",
        "name",
        "message",
    ]


def test_config_is_optional_and_defaults_are_applied() -> None:
    response = client.post(
        "/api/v1/widgets",
        headers=auth_headers(),
        json={"name": "Bare", "kind": "contact"},
    )

    assert response.status_code == 201
    config = response.json()["config"]
    assert config["title"]
    assert config["submit_label"]
    assert len(config["fields"]) >= 1


def test_public_config_endpoint_serves_the_stored_config() -> None:
    widget_id = create_widget(valid_config()).json()["id"]

    public = client.get(f"/api/v1/public/widgets/{widget_id}/config")

    assert public.status_code == 200
    assert public.json()["config"]["title"] == "Talk to sales"


def test_unknown_config_field_is_rejected() -> None:
    config = valid_config()
    config["evil_extra"] = "payload"

    assert create_widget(config).status_code == 422


def test_unknown_field_property_is_rejected() -> None:
    config = valid_config()
    config["fields"][0]["onclick"] = "alert(1)"

    assert create_widget(config).status_code == 422


def test_unsupported_field_kind_is_rejected() -> None:
    config = valid_config()
    config["fields"][0]["kind"] = "file"

    assert create_widget(config).status_code == 422


def test_too_many_fields_is_rejected() -> None:
    config = valid_config()
    config["fields"] = [
        {"name": f"f{index}", "label": "L", "kind": "text", "required": False}
        for index in range(MAX_FIELDS + 1)
    ]

    assert create_widget(config).status_code == 422


def test_empty_field_list_is_rejected() -> None:
    config = valid_config()
    config["fields"] = []

    assert create_widget(config).status_code == 422


def test_duplicate_field_names_are_rejected() -> None:
    config = valid_config()
    config["fields"] = [
        {"name": "email", "label": "A", "kind": "email", "required": True},
        {"name": "email", "label": "B", "kind": "text", "required": False},
    ]

    assert create_widget(config).status_code == 422


def test_field_name_must_be_a_safe_identifier() -> None:
    for unsafe in ('"><script>', "field name", "a-b", "../etc", "naïve"):
        config = valid_config()
        config["fields"][0]["name"] = unsafe

        assert create_widget(config).status_code == 422, unsafe


def test_oversized_config_strings_are_rejected() -> None:
    config = valid_config()
    config["title"] = "T" * 5_000

    assert create_widget(config).status_code == 422


def test_unsupported_theme_is_rejected() -> None:
    config = valid_config()
    config["theme"] = "neon"

    assert create_widget(config).status_code == 422


def test_config_is_not_a_place_for_arbitrary_structure() -> None:
    for bad in ("a string", 42, ["a", "list"], True):
        assert create_widget(bad).status_code == 422, bad


def test_markup_in_labels_is_stored_verbatim_not_interpreted() -> None:
    config = valid_config()
    config["fields"][0]["label"] = "<b>Email</b>"
    widget_id = create_widget(config).json()["id"]

    public = client.get(f"/api/v1/public/widgets/{widget_id}/config")

    assert public.json()["config"]["fields"][0]["label"] == "<b>Email</b>"


def test_config_change_produces_a_new_etag() -> None:
    widget_id = create_widget(valid_config()).json()["id"]
    first = client.get(f"/api/v1/public/widgets/{widget_id}/config")
    first_etag = first.headers["ETag"]

    client.patch(
        f"/api/v1/widgets/{widget_id}",
        headers=auth_headers(),
        json={"config": {**valid_config(), "title": "Different title"}},
    )
    second = client.get(f"/api/v1/public/widgets/{widget_id}/config")

    assert second.headers["ETag"] != first_etag


def test_unchanged_config_still_revalidates_to_304() -> None:
    widget_id = create_widget(valid_config()).json()["id"]
    etag = client.get(f"/api/v1/public/widgets/{widget_id}/config").headers["ETag"]

    again = client.get(
        f"/api/v1/public/widgets/{widget_id}/config",
        headers={"If-None-Match": etag},
    )

    assert again.status_code == 304


def test_config_cannot_be_set_on_another_tenants_widget() -> None:
    widget_id = create_widget(valid_config()).json()["id"]
    intruder = create_access_token("user-99", timedelta(minutes=5))

    response = client.patch(
        f"/api/v1/widgets/{widget_id}",
        headers={"Authorization": f"Bearer {intruder}"},
        json={"config": valid_config()},
    )

    assert response.status_code in {401, 403, 404}


def test_stored_config_is_valid_json_for_the_bundle() -> None:
    widget_id = create_widget(valid_config()).json()["id"]

    public = client.get(f"/api/v1/public/widgets/{widget_id}/config")

    assert json.loads(public.text)["config"]["theme"] == "dark"
