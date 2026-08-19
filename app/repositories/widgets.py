from dataclasses import dataclass
from itertools import count
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import Identity
from app.models import WidgetRecord


@dataclass(frozen=True)
class Widget:
    id: int
    name: str
    kind: str


class WidgetRepository(Protocol):
    def create(self, *, identity: Identity, name: str, kind: str) -> Widget: ...

    def get_for_tenant(
        self,
        *,
        identity: Identity,
        widget_id: int,
    ) -> Widget | None: ...


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
        return Widget(id=record.id, name=record.name, kind=record.kind)

    def get_for_tenant(
        self,
        *,
        identity: Identity,
        widget_id: int,
    ) -> Widget | None:
        statement = select(WidgetRecord).where(
            WidgetRecord.id == widget_id,
            WidgetRecord.tenant_id == identity.tenant_id,
        )
        record = self._session.scalar(statement)
        if record is None:
            return None
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
