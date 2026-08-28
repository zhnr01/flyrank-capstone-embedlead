from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class WidgetCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    kind: Literal["contact"]


class WidgetResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    kind: str


class WidgetUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    kind: Literal["contact"] | None = None


class WidgetListResponse(BaseModel):
    data: list[WidgetResponse]
    next_after_id: int | None


class WidgetEmbedResponse(BaseModel):
    widget_id: int
    bundle_version: str
    bundle_url: str
    snippet: str


class WidgetConfigResponse(BaseModel):
    widget_id: int
    name: str
    kind: str
    version: str
