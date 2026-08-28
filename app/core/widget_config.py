from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class WidgetKind(StrEnum):
    CONTACT = "contact"
    NEWSLETTER = "newsletter"


FieldKind = Literal["text", "email", "textarea", "tel"]
WidgetTheme = Literal["light", "dark"]

CONTACT_KIND = WidgetKind.CONTACT


def kind_from_stored(value: str) -> WidgetKind:
    try:
        return WidgetKind(value)
    except ValueError:
        raise ValueError(f"unknown widget kind: {value!r}") from None

MAX_CONFIG_FIELDS = 12
MAX_TITLE_LENGTH = 120
MAX_DESCRIPTION_LENGTH = 400
MAX_LABEL_LENGTH = 80
MAX_SUBMIT_LABEL_LENGTH = 40
MAX_FIELD_NAME_LENGTH = 40
FIELD_NAME_PATTERN = r"^[a-z][a-z0-9_]*$"

DEFAULT_TITLE = "Get in touch"
DEFAULT_SUBMIT_LABEL = "Send"
DEFAULT_THEME: WidgetTheme = "light"


class WidgetField(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(
        min_length=1,
        max_length=MAX_FIELD_NAME_LENGTH,
        pattern=FIELD_NAME_PATTERN,
    )
    label: str = Field(min_length=1, max_length=MAX_LABEL_LENGTH)
    kind: FieldKind = "text"
    required: bool = False


class WidgetConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(default=DEFAULT_TITLE, min_length=1, max_length=MAX_TITLE_LENGTH)
    description: str | None = Field(default=None, max_length=MAX_DESCRIPTION_LENGTH)
    submit_label: str = Field(
        default=DEFAULT_SUBMIT_LABEL,
        min_length=1,
        max_length=MAX_SUBMIT_LABEL_LENGTH,
    )
    theme: WidgetTheme = DEFAULT_THEME
    fields: list[WidgetField] = Field(min_length=1, max_length=MAX_CONFIG_FIELDS)

    @field_validator("fields")
    @classmethod
    def reject_duplicate_names(cls, value: list[WidgetField]) -> list[WidgetField]:
        names = [field.name for field in value]
        if len(names) != len(set(names)):
            raise ValueError("field names must be unique")
        return value

    @model_validator(mode="after")
    def require_a_contactable_field(self) -> WidgetConfig:
        if not any(field.kind == "email" for field in self.fields):
            raise ValueError("at least one field must have kind 'email'")
        return self


def default_config() -> WidgetConfig:
    return WidgetConfig(
        fields=[
            WidgetField(name="email", label="Email", kind="email", required=True),
            WidgetField(name="name", label="Name", kind="text", required=True),
            WidgetField(
                name="message",
                label="Message",
                kind="textarea",
                required=False,
            ),
        ]
    )
