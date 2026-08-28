from __future__ import annotations

import re
from dataclasses import dataclass

from app.core.widget_config import FieldKind, WidgetConfig

HONEYPOT_FIELD = "website"
MAX_HONEYPOT_LENGTH = 200
MAX_ANSWER_LENGTHS: dict[FieldKind, int] = {
    "text": 120,
    "email": 320,
    "tel": 40,
    "textarea": 2_000,
}
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s.]+\.[^@\s]+$")
LEGACY_NAME_FIELD = "name"
LEGACY_MESSAGE_FIELD = "message"


@dataclass(frozen=True)
class SubmissionAnswers:
    values: dict[str, str | None]
    looks_automated: bool

    @property
    def email(self) -> str:
        return self.values.get("email") or ""

    @property
    def name(self) -> str:
        return self.values.get(LEGACY_NAME_FIELD) or ""

    @property
    def message(self) -> str | None:
        return self.values.get(LEGACY_MESSAGE_FIELD)


def validate_against_config(
    payload: dict[str, object],
    *,
    config: WidgetConfig,
) -> SubmissionAnswers:
    allowed = {field.name: field for field in config.fields}
    unexpected = set(payload) - set(allowed) - {HONEYPOT_FIELD}
    if unexpected:
        raise ValueError(f"unexpected field(s): {', '.join(sorted(unexpected))}")

    values: dict[str, str | None] = {}
    for name, field in allowed.items():
        raw = payload.get(name)
        if raw is None:
            answer = ""
        elif isinstance(raw, str):
            answer = raw.strip()
        else:
            raise ValueError(f"{name} must be a string")

        if not answer:
            if field.required:
                raise ValueError(f"{name} is required")
            values[name] = None
            continue

        limit = MAX_ANSWER_LENGTHS[field.kind]
        if len(answer) > limit:
            raise ValueError(f"{name} is too long (max {limit} characters)")
        if field.kind == "email" and not EMAIL_PATTERN.match(answer):
            raise ValueError(f"{name} must be a valid email address")
        values[name] = answer

    trap = payload.get(HONEYPOT_FIELD)
    if isinstance(trap, str) and len(trap) > MAX_HONEYPOT_LENGTH:
        raise ValueError(f"{HONEYPOT_FIELD} is too long")
    automated = isinstance(trap, str) and bool(trap.strip())
    return SubmissionAnswers(values=values, looks_automated=automated)
