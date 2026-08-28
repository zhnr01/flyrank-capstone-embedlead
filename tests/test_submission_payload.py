import pytest

from app.core.submission_payload import (
    MAX_ANSWER_LENGTHS,
    MAX_HONEYPOT_LENGTH,
    SubmissionAnswers,
    validate_against_config,
)
from app.core.widget_config import WidgetConfig, WidgetField, default_config

CUSTOM = WidgetConfig(
    title="Book a demo",
    submit_label="Request slot",
    theme="dark",
    fields=[
        WidgetField(name="email", label="Work email", kind="email", required=True),
        WidgetField(name="company", label="Company", kind="text", required=True),
        WidgetField(name="phone", label="Phone", kind="tel", required=False),
    ],
)


def test_answers_matching_the_config_are_accepted() -> None:
    answers = validate_against_config(
        {"email": "buyer@example.com", "company": "Acme", "phone": "+49 30 1"},
        config=CUSTOM,
    )

    assert answers.email == "buyer@example.com"
    assert answers.values["company"] == "Acme"


def test_an_optional_field_may_be_omitted() -> None:
    answers = validate_against_config(
        {"email": "buyer@example.com", "company": "Acme"},
        config=CUSTOM,
    )

    assert answers.values.get("phone") is None


def test_a_missing_required_field_is_rejected() -> None:
    with pytest.raises(ValueError, match="company"):
        validate_against_config({"email": "buyer@example.com"}, config=CUSTOM)


def test_a_field_absent_from_the_config_is_rejected() -> None:
    with pytest.raises(ValueError, match="unexpected"):
        validate_against_config(
            {"email": "a@example.com", "company": "Acme", "salary": "99999"},
            config=CUSTOM,
        )


def test_an_invalid_email_answer_is_rejected() -> None:
    with pytest.raises(ValueError, match="email"):
        validate_against_config(
            {"email": "not-an-email", "company": "Acme"},
            config=CUSTOM,
        )


def test_an_oversized_answer_is_rejected() -> None:
    with pytest.raises(ValueError, match="too long"):
        validate_against_config(
            {
                "email": "a@example.com",
                "company": "C" * (MAX_ANSWER_LENGTHS["text"] + 1),
            },
            config=CUSTOM,
        )


def test_a_blank_required_answer_is_rejected() -> None:
    with pytest.raises(ValueError, match="company"):
        validate_against_config(
            {"email": "a@example.com", "company": "   "},
            config=CUSTOM,
        )


def test_the_honeypot_is_accepted_and_flagged_without_being_a_field() -> None:
    answers = validate_against_config(
        {"email": "a@example.com", "company": "Acme", "website": "http://spam"},
        config=CUSTOM,
    )

    assert answers.looks_automated is True


def test_an_empty_honeypot_is_not_automated() -> None:
    answers = validate_against_config(
        {"email": "a@example.com", "company": "Acme", "website": ""},
        config=CUSTOM,
    )

    assert answers.looks_automated is False


def test_the_default_config_still_accepts_the_original_shape() -> None:
    answers = validate_against_config(
        {"email": "a@example.com", "name": "Visitor", "message": "hello"},
        config=default_config(),
    )

    assert answers.email == "a@example.com"
    assert answers.name == "Visitor"
    assert answers.message == "hello"


def test_name_and_message_fall_back_when_the_config_omits_them() -> None:
    answers = validate_against_config(
        {"email": "a@example.com", "company": "Acme"},
        config=CUSTOM,
    )

    assert answers.email == "a@example.com"
    assert answers.name == ""
    assert answers.message is None


def test_answers_are_a_plain_mapping_safe_to_store() -> None:
    answers = validate_against_config(
        {"email": "a@example.com", "company": "Acme"},
        config=CUSTOM,
    )

    assert isinstance(answers, SubmissionAnswers)
    assert set(answers.values) <= {"email", "company", "phone"}


def test_an_oversized_honeypot_is_rejected() -> None:
    with pytest.raises(ValueError, match="website"):
        validate_against_config(
            {
                "email": "a@example.com",
                "company": "Acme",
                "website": "x" * (MAX_HONEYPOT_LENGTH + 1),
            },
            config=CUSTOM,
        )
