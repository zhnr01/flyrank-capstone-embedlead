from pydantic import BaseModel, ConfigDict, Field

from app.core.widget_config import WidgetConfig, WidgetKind

MAX_NAME_LENGTH = 120


class WidgetCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=MAX_NAME_LENGTH)
    kind: WidgetKind
    config: WidgetConfig | None = None


class WidgetUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=MAX_NAME_LENGTH)
    kind: WidgetKind | None = None
    config: WidgetConfig | None = None


class WidgetResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    kind: str
    config: WidgetConfig


class WidgetListResponse(BaseModel):
    data: list[WidgetResponse]
    next_after_id: int | None


class WidgetConfigResponse(BaseModel):
    widget_id: int
    name: str
    kind: str
    version: str
    config: WidgetConfig


class WidgetEmbedResponse(BaseModel):
    widget_id: int
    bundle_version: str
    bundle_url: str
    snippet: str
