import base64
from datetime import timedelta

import jwt
import pytest
from jwt import InvalidTokenError

from app.core.auth import (
    create_access_token,
    get_password_hash,
    verify_access_token,
    verify_password,
)
from app.core.config import Settings, settings


def test_password_hash_verifies_original_and_rejects_other_password() -> None:
    hashed = get_password_hash("correct-password")

    assert verify_password("correct-password", hashed) is True
    assert verify_password("wrong-password", hashed) is False
    assert hashed != "correct-password"


def test_access_token_round_trips_user_subject(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "secret_key", "test-only-key-with-at-least-32-bytes")

    token = create_access_token("user-7", timedelta(minutes=5))

    assert verify_access_token(token) == "user-7"


def test_tampered_access_token_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "secret_key", "test-only-key-with-at-least-32-bytes")
    header, _, signature = create_access_token(
        "user-7",
        timedelta(minutes=5),
    ).split(".")
    forged = base64.urlsafe_b64encode(b'{"sub":"user-1","exp":9999999999}').rstrip(b"=")
    tampered = f"{header}.{forged.decode()}.{signature}"

    with pytest.raises(InvalidTokenError):
        verify_access_token(tampered)


def test_token_signed_with_another_key_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "secret_key", "attacker-key-with-at-least-32-bytes!")
    forged = create_access_token("user-7", timedelta(minutes=5))
    monkeypatch.setattr(settings, "secret_key", "test-only-key-with-at-least-32-bytes")

    with pytest.raises(InvalidTokenError):
        verify_access_token(forged)


def test_unsigned_token_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "secret_key", "test-only-key-with-at-least-32-bytes")
    unsigned = jwt.encode({"sub": "user-7", "exp": 9999999999}, "", algorithm="none")

    with pytest.raises(InvalidTokenError):
        verify_access_token(unsigned)


def test_expired_access_token_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "secret_key", "test-only-key-with-at-least-32-bytes")
    token = create_access_token("user-7", timedelta(seconds=-1))

    with pytest.raises(InvalidTokenError):
        verify_access_token(token)


def test_production_settings_reject_development_secret() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        Settings(
            environment="production",
            secret_key="local-development-only-change-me-32-bytes",
        )
