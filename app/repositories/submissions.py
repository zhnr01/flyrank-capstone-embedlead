from dataclasses import dataclass
from itertools import count
from typing import Protocol

from sqlalchemy.orm import Session

from app.core.geo import GeoLocation
from app.models import SubmissionRecord


@dataclass(frozen=True)
class Submission:
    id: int
    widget_id: int
    tenant_id: int
    email: str
    name: str
    message: str | None
    geo_country: str | None = None
    geo_city: str | None = None
    geo_provider: str | None = None


class SubmissionRepository(Protocol):
    def create(
        self,
        *,
        widget_id: int,
        tenant_id: int,
        email: str,
        name: str,
        message: str | None,
        location: GeoLocation | None = None,
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
        location: GeoLocation | None = None,
    ) -> Submission:
        record = SubmissionRecord(
            widget_id=widget_id,
            tenant_id=tenant_id,
            email=email,
            name=name,
            message=message,
            geo_country=location.country if location else None,
            geo_city=location.city if location else None,
            geo_provider=location.provider if location else None,
        )
        self._session.add(record)
        self._session.flush()
        self._session.refresh(record)
        return Submission(
            id=record.id,
            widget_id=record.widget_id,
            tenant_id=record.tenant_id,
            email=record.email,
            name=record.name,
            message=record.message,
            geo_country=record.geo_country,
            geo_city=record.geo_city,
            geo_provider=record.geo_provider,
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
        location: GeoLocation | None = None,
    ) -> Submission:
        submission = Submission(
            id=next(self._ids),
            widget_id=widget_id,
            tenant_id=tenant_id,
            email=email,
            name=name,
            message=message,
            geo_country=location.country if location else None,
            geo_city=location.city if location else None,
            geo_provider=location.provider if location else None,
        )
        self._submissions.append(submission)
        return submission

    def all_for_tenant(self, tenant_id: int) -> list[Submission]:
        return [
            submission
            for submission in self._submissions
            if submission.tenant_id == tenant_id
        ]
