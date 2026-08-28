from dataclasses import dataclass, replace
from itertools import count
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.identity import Identity
from app.models import WidgetRecord


@dataclass(frozen=True)
class Widget:
    id: int
    name: str
    kind: str


@dataclass(frozen=True)
class WidgetOwnership:
    id: int
    tenant_id: int


@dataclass(frozen=True)
class WidgetPage:
    data: list[Widget]
    next_after_id: int | None


class WidgetRepository(Protocol):
    def create(self, *, identity: Identity, name: str, kind: str) -> Widget: ...

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
        name: str | None,
        kind: str | None,
    ) -> Widget | None: ...

    def delete_for_tenant(self, *, identity: Identity, widget_id: int) -> bool: ...

    def get_ownership(self, *, widget_id: int) -> WidgetOwnership | None: ...

    def get_public(self, *, widget_id: int) -> Widget | None: ...


class SqlAlchemyWidgetRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create(self, *, identity: Identity, name: str, kind: str) -> Widget:
        record = WidgetRecord(
            tenant_id=identity.tenant_id,
            name=name,
            kind=kind,
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
            data=[self._to_widget(record) for record in visible],
            next_after_id=next_after_id,
        )

    def update_for_tenant(
        self,
        *,
        identity: Identity,
        widget_id: int,
        name: str | None,
        kind: str | None,
    ) -> Widget | None:
        record = self._get_record(identity=identity, widget_id=widget_id)
        if record is None:
            return None
        if name is not None:
            record.name = name
        if kind is not None:
            record.kind = kind
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

    def get_ownership(self, *, widget_id: int) -> WidgetOwnership | None:
        row = self._session.execute(
            select(WidgetRecord.id, WidgetRecord.tenant_id).where(
                WidgetRecord.id == widget_id
            )
        ).one_or_none()
        if row is None:
            return None
        return WidgetOwnership(id=row.id, tenant_id=row.tenant_id)

    def get_public(self, *, widget_id: int) -> Widget | None:
        row = self._session.execute(
            select(
                WidgetRecord.id,
                WidgetRecord.name,
                WidgetRecord.kind,
            ).where(WidgetRecord.id == widget_id)
        ).one_or_none()
        if row is None:
            return None
        return Widget(id=row.id, name=row.name, kind=row.kind)

    @staticmethod
    def _to_widget(record: WidgetRecord) -> Widget:
        return Widget(id=record.id, name=record.name, kind=record.kind)


class InMemoryWidgetRepository:
    def __init__(self) -> None:
        self._widgets: dict[tuple[int, int], Widget] = {}
        self._ids = count(1)

    def create(self, *, identity: Identity, name: str, kind: str) -> Widget:
        widget = Widget(id=next(self._ids), name=name, kind=kind)
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
        return WidgetPage(data=visible, next_after_id=next_after_id)

    def update_for_tenant(
        self,
        *,
        identity: Identity,
        widget_id: int,
        name: str | None,
        kind: str | None,
    ) -> Widget | None:
        key = (identity.tenant_id, widget_id)
        widget = self._widgets.get(key)
        if widget is None:
            return None
        updated = replace(
            widget,
            name=name if name is not None else widget.name,
            kind=kind if kind is not None else widget.kind,
        )
        self._widgets[key] = updated
        return updated

    def delete_for_tenant(self, *, identity: Identity, widget_id: int) -> bool:
        return self._widgets.pop((identity.tenant_id, widget_id), None) is not None

    def get_ownership(self, *, widget_id: int) -> WidgetOwnership | None:
        for (tenant_id, stored_id) in self._widgets:
            if stored_id == widget_id:
                return WidgetOwnership(id=widget_id, tenant_id=tenant_id)
        return None

    def get_public(self, *, widget_id: int) -> Widget | None:
        for (_, stored_id), widget in self._widgets.items():
            if stored_id == widget_id:
                return widget
        return None
