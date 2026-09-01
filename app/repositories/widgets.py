from dataclasses import dataclass, replace
from itertools import count
from typing import Protocol

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.identity import Identity
from app.core.widget_config import (
    CONTACT_KIND,
    WidgetConfig,
    WidgetKind,
    default_config,
    kind_from_stored,
)
from app.models import WidgetRecord


def kind_or_default(stored: str) -> WidgetKind:
    try:
        return kind_from_stored(stored)
    except ValueError:
        return CONTACT_KIND


@dataclass(frozen=True)
class Widget:
    id: int
    name: str
    kind: WidgetKind
    config: WidgetConfig


@dataclass(frozen=True)
class OwnedWidget:
    widget: Widget
    tenant_id: int


@dataclass(frozen=True)
class WidgetPage:
    widgets: list[Widget]
    next_after_id: int | None


@dataclass(frozen=True)
class WidgetChanges:
    name: str | None
    kind: WidgetKind | None
    config: WidgetConfig | None


def config_from_stored(stored: object) -> WidgetConfig:
    if not isinstance(stored, dict):
        return default_config()
    try:
        return WidgetConfig.model_validate(stored)
    except ValidationError:
        return default_config()


class WidgetRepository(Protocol):
    def create(
        self,
        *,
        identity: Identity,
        name: str,
        kind: WidgetKind,
        config: WidgetConfig,
    ) -> Widget: ...

    def get_for_tenant(
        self,
        *,
        identity: Identity,
        widget_id: int,
    ) -> Widget | None: ...

    def list_for_tenant(
        self,
        *,
        identity: Identity,
        limit: int,
        after_id: int | None,
    ) -> WidgetPage: ...

    def update_for_tenant(
        self,
        *,
        identity: Identity,
        widget_id: int,
        changes: WidgetChanges,
    ) -> Widget | None: ...

    def delete_for_tenant(self, *, identity: Identity, widget_id: int) -> bool: ...

    def get_public_with_ownership(
        self,
        *,
        widget_id: int,
    ) -> OwnedWidget | None: ...

    def get_public(self, *, widget_id: int) -> Widget | None: ...


class SqlAlchemyWidgetRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create(
        self,
        *,
        identity: Identity,
        name: str,
        kind: WidgetKind,
        config: WidgetConfig,
    ) -> Widget:
        record = WidgetRecord(
            tenant_id=identity.tenant_id,
            name=name,
            kind=kind,
            config=config.model_dump(mode="json"),
        )
        self._session.add(record)
        self._session.commit()
        self._session.refresh(record)
        return self._to_widget(record)

    def get_for_tenant(
        self,
        *,
        identity: Identity,
        widget_id: int,
    ) -> Widget | None:
        record = self._get_record(identity=identity, widget_id=widget_id)
        return self._to_widget(record) if record is not None else None

    def list_for_tenant(
        self,
        *,
        identity: Identity,
        limit: int,
        after_id: int | None,
    ) -> WidgetPage:
        statement = select(WidgetRecord).where(
            WidgetRecord.tenant_id == identity.tenant_id
        )
        if after_id is not None:
            statement = statement.where(WidgetRecord.id < after_id)
        records = list(
            self._session.scalars(
                statement.order_by(WidgetRecord.id.desc()).limit(limit + 1)
            )
        )
        has_next_page = len(records) > limit
        visible = records[:limit]
        next_after_id = visible[-1].id if has_next_page and visible else None
        return WidgetPage(
            widgets=[self._to_widget(record) for record in visible],
            next_after_id=next_after_id,
        )

    def update_for_tenant(
        self,
        *,
        identity: Identity,
        widget_id: int,
        changes: WidgetChanges,
    ) -> Widget | None:
        record = self._get_record(identity=identity, widget_id=widget_id)
        if record is None:
            return None
        if changes.name is not None:
            record.name = changes.name
        if changes.kind is not None:
            record.kind = changes.kind
        if changes.config is not None:
            record.config = changes.config.model_dump(mode="json")
        self._session.commit()
        self._session.refresh(record)
        return self._to_widget(record)

    def delete_for_tenant(self, *, identity: Identity, widget_id: int) -> bool:
        record = self._get_record(identity=identity, widget_id=widget_id)
        if record is None:
            return False
        self._session.delete(record)
        self._session.commit()
        return True

    def _get_record(
        self,
        *,
        identity: Identity,
        widget_id: int,
    ) -> WidgetRecord | None:
        return self._session.scalar(
            select(WidgetRecord).where(
                WidgetRecord.id == widget_id,
                WidgetRecord.tenant_id == identity.tenant_id,
            )
        )

    def get_public_with_ownership(
        self,
        *,
        widget_id: int,
    ) -> OwnedWidget | None:
        record = self._session.scalar(
            select(WidgetRecord).where(WidgetRecord.id == widget_id)
        )
        if record is None:
            return None
        return OwnedWidget(
            widget=self._to_widget(record),
            tenant_id=record.tenant_id,
        )

    def get_public(self, *, widget_id: int) -> Widget | None:
        record = self._session.scalar(
            select(WidgetRecord).where(WidgetRecord.id == widget_id)
        )
        return self._to_widget(record) if record is not None else None

    @staticmethod
    def _to_widget(record: WidgetRecord) -> Widget:
        return Widget(
            id=record.id,
            name=record.name,
            kind=kind_or_default(record.kind),
            config=config_from_stored(record.config),
        )


class InMemoryWidgetRepository:
    def __init__(self) -> None:
        self._widgets: dict[tuple[int, int], Widget] = {}
        self._ids = count(1)

    def create(
        self,
        *,
        identity: Identity,
        name: str,
        kind: WidgetKind,
        config: WidgetConfig,
    ) -> Widget:
        widget = Widget(
            id=next(self._ids),
            name=name,
            kind=kind,
            config=config_from_stored(config.model_dump(mode="json")),
        )
        self._widgets[(identity.tenant_id, widget.id)] = widget
        return widget

    def get_for_tenant(
        self,
        *,
        identity: Identity,
        widget_id: int,
    ) -> Widget | None:
        return self._widgets.get((identity.tenant_id, widget_id))

    def list_for_tenant(
        self,
        *,
        identity: Identity,
        limit: int,
        after_id: int | None,
    ) -> WidgetPage:
        widgets = [
            widget
            for (tenant_id, _), widget in self._widgets.items()
            if tenant_id == identity.tenant_id
            and (after_id is None or widget.id < after_id)
        ]
        widgets.sort(key=lambda widget: widget.id, reverse=True)
        has_next_page = len(widgets) > limit
        visible = widgets[:limit]
        next_after_id = visible[-1].id if has_next_page and visible else None
        return WidgetPage(widgets=visible, next_after_id=next_after_id)

    def update_for_tenant(
        self,
        *,
        identity: Identity,
        widget_id: int,
        changes: WidgetChanges,
    ) -> Widget | None:
        key = (identity.tenant_id, widget_id)
        widget = self._widgets.get(key)
        if widget is None:
            return None
        updated = replace(
            widget,
            name=changes.name if changes.name is not None else widget.name,
            kind=changes.kind if changes.kind is not None else widget.kind,
            config=(
                config_from_stored(changes.config.model_dump(mode="json"))
                if changes.config is not None
                else widget.config
            ),
        )
        self._widgets[key] = updated
        return updated

    def delete_for_tenant(self, *, identity: Identity, widget_id: int) -> bool:
        return self._widgets.pop((identity.tenant_id, widget_id), None) is not None

    def get_public_with_ownership(
        self,
        *,
        widget_id: int,
    ) -> OwnedWidget | None:
        for (tenant_id, stored_id), widget in self._widgets.items():
            if stored_id == widget_id:
                return OwnedWidget(widget=widget, tenant_id=tenant_id)
        return None

    def get_public(self, *, widget_id: int) -> Widget | None:
        for (_, stored_id), widget in self._widgets.items():
            if stored_id == widget_id:
                return widget
        return None
