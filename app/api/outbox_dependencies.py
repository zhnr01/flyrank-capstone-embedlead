from typing import Annotated, Protocol

from fastapi import Depends

from app.api.deps import SessionDep
from app.core.outbox import NotificationTransport
from app.repositories.outbox import OutboxRepository, SqlAlchemyOutboxRepository
from app.services.notifications import LoggingNotificationTransport


def get_outbox_repository(session: SessionDep) -> OutboxRepository:
    return SqlAlchemyOutboxRepository(session)


def get_notification_transport() -> NotificationTransport:
    return LoggingNotificationTransport()


class UnitOfWork(Protocol):
    def commit(self) -> None: ...


def get_unit_of_work(session: SessionDep) -> UnitOfWork:
    return session


OutboxRepositoryDep = Annotated[OutboxRepository, Depends(get_outbox_repository)]
UnitOfWorkDep = Annotated[UnitOfWork, Depends(get_unit_of_work)]
NotificationTransportDep = Annotated[
    NotificationTransport,
    Depends(get_notification_transport),
]
