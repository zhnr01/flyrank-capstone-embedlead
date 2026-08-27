from dataclasses import dataclass
from itertools import count
from typing import Protocol

from sqlalchemy.orm import Session

from app.models import SubmissionRecord


@dataclass(frozen=True)
class Submission:
    id: int
    widget_id: int
    tenant_id: int
    email: str
    name: str
    message: str | None


class SubmissionRepository(Protocol):
    def create(
        self,
        *,
        widget_id: int,
        tenant_id: int,
        email: str,
        name: str,
        message: str | None,
    ) -> Submission: ...


class SqlAlchemySubmissionRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create(
        self,
        *,
        widget_id: int,
        tenant_id: int,
        email: str,
        name: str,
        message: str | None,
    ) -> Submission:
        record = SubmissionRecord(
            widget_id=widget_id,
            tenant_id=tenant_id,
            email=email,
            name=name,
            message=message,
        )
        self._session.add(record)
        self._session.commit()
        self._session.refresh(record)
        return Submission(
            id=record.id,
            widget_id=record.widget_id,
            tenant_id=record.tenant_id,
            email=record.email,
            name=record.name,
            message=record.message,
        )


class InMemorySubmissionRepository:
    def __init__(self) -> None:
        self._submissions: list[Submission] = []
        self._ids = count(1)

    def create(
        self,
        *,
        widget_id: int,
        tenant_id: int,
        email: str,
        name: str,
        message: str | None,
    ) -> Submission:
        submission = Submission(
            id=next(self._ids),
            widget_id=widget_id,
            tenant_id=tenant_id,
            email=email,
            name=name,
            message=message,
        )
        self._submissions.append(submission)
        return submission

    def all_for_tenant(self, tenant_id: int) -> list[Submission]:
        return [
            submission
            for submission in self._submissions
            if submission.tenant_id == tenant_id
        ]
