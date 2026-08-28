import re
from pathlib import Path

from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app

client = TestClient(app)
BUNDLE = (
    Path(__file__).resolve().parent.parent
    / "app"
    / "static"
    / f"widget-{settings.widget_bundle_version}.js"
)
SOURCE = BUNDLE.read_text(encoding="utf-8")


def test_the_configured_bundle_version_exists_on_disk() -> None:
    assert BUNDLE.is_file()


def test_bundle_is_served_under_its_version_and_is_immutable() -> None:
    response = client.get(
        f"/api/v1/public/widgets/bundle/{settings.widget_bundle_version}/widget.js"
    )

    assert response.status_code == 200
    assert "immutable" in response.headers["cache-control"]


def test_a_previous_bundle_version_is_not_served() -> None:
    response = client.get("/api/v1/public/widgets/bundle/v1/widget.js")

    assert response.status_code == 404


def test_bundle_never_assigns_config_text_through_innerhtml() -> None:
    assert "innerHTML" not in SOURCE


def test_bundle_builds_fields_from_config_rather_than_hardcoding_them() -> None:
    assert "config.fields.forEach" in SOURCE
    assert re.search(r"config\.title", SOURCE)
    assert re.search(r"config\.submit_label", SOURCE)
    assert re.search(r"config\.theme", SOURCE)


def test_bundle_keeps_the_honeypot_visually_hidden_and_out_of_tab_order() -> None:
    assert "left:-5000px" in SOURCE
    assert "tabIndex = -1" in SOURCE
    assert 'name = "website"' in SOURCE


def test_bundle_handles_every_status_the_api_can_return() -> None:
    for status_code in ("202", "413", "422", "429"):
        assert status_code in SOURCE, status_code


def test_bundle_sends_no_credentials_cross_origin() -> None:
    assert SOURCE.count('credentials: "omit"') >= 2
