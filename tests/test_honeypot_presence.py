import pytest

from app.core.submission_payload import (
    HONEYPOT_FIELD,
    validate_against_config,
)
from app.core.widget_config import default_config


def submit(payload: dict[str, object]) -> bool:
    result = validate_against_config(payload=payload, config=default_config())
    return result.looks_automated


def test_a_filled_trap_is_automated() -> None:
    assert submit({"email": "a@b.co", "name": "N", HONEYPOT_FIELD: "spam"}) is True


def test_an_empty_trap_is_a_human() -> None:
    assert submit({"email": "a@b.co", "name": "N", HONEYPOT_FIELD: ""}) is False


def test_an_absent_trap_is_tolerated_because_a_client_may_omit_it() -> None:
    assert submit({"email": "a@b.co", "name": "N"}) is False


def test_a_whitespace_only_trap_is_a_human() -> None:
    assert submit({"email": "a@b.co", "name": "N", HONEYPOT_FIELD: "   "}) is False


def test_a_non_string_trap_is_treated_as_automated() -> None:
    assert submit({"email": "a@b.co", "name": "N", HONEYPOT_FIELD: 1}) is True


def test_an_oversized_trap_is_still_rejected_outright() -> None:
    with pytest.raises(ValueError, match=HONEYPOT_FIELD):
        submit({"email": "a@b.co", "name": "N", HONEYPOT_FIELD: "x" * 500})
