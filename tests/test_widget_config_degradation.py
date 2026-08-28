import pytest

from app.core.widget_config import CONTACT_KIND, WidgetKind, kind_from_stored
from app.repositories.widgets import config_from_stored, kind_or_default


def test_a_valid_stored_kind_is_returned_unchanged() -> None:
    assert kind_or_default("contact") is WidgetKind.CONTACT
    assert kind_or_default("newsletter") is WidgetKind.NEWSLETTER


def test_a_corrupt_stored_kind_degrades_instead_of_raising() -> None:
    for corrupt in ("bogus_kind", "", "CONTACT", "contact ", "1"):
        assert kind_or_default(corrupt) is CONTACT_KIND


def test_kind_from_stored_still_raises_for_callers_that_want_strictness() -> None:
    with pytest.raises(ValueError, match="unknown widget kind"):
        kind_from_stored("bogus_kind")


def test_a_corrupt_stored_config_degrades_to_the_default() -> None:
    for corrupt in (
        {"title": "x", "fields": []},
        {"fields": [{"name": "email", "label": "E", "kind": "file"}]},
        {"theme": "neon", "fields": [{"name": "email", "label": "E", "kind": "email"}]},
        {"unexpected_key": 1},
        {},
    ):
        recovered = config_from_stored(corrupt)

        assert recovered.fields
        assert any(field.kind == "email" for field in recovered.fields)


def test_a_non_mapping_stored_config_degrades_to_the_default() -> None:
    for corrupt in (None, "a string", 42, ["a", "list"], True):
        assert config_from_stored(corrupt).fields
