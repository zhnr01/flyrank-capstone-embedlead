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
    answers: dict[str, str | None] | None = None


@dataclass(frozen=True)
class NewSubmission:
    widget_id: int
    tenant_id: int
    email: str
    name: str
    message: str | None
    location: GeoLocation | None = None
    answers: dict[str, str | None] | None = None


class SubmissionRepository(Protocol):
    def create(self, new_submission: NewSubmission) -> Submission: ...


class SqlAlchemySubmissionRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create(self, new_submission: NewSubmission) -> Submission:
        location = new_submission.location
        record = SubmissionRecord(
            widget_id=new_submission.widget_id,
            tenant_id=new_submission.tenant_id,
            email=new_submission.email,
            name=new_submission.name,
            message=new_submission.message,
            geo_country=location.country if location else None,
            geo_city=location.city if location else None,
            geo_provider=location.provider if location else None,
            answers=new_submission.answers,
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
            answers=(dict(record.answers) if record.answers is not None else None),
        )


class InMemorySubmissionRepository:
    def __init__(self) -> None:
        self._submissions: list[Submission] = []
        self._ids = count(1)

    def create(self, new_submission: NewSubmission) -> Submission:
        location = new_submission.location
        submission = Submission(
            id=next(self._ids),
            widget_id=new_submission.widget_id,
            tenant_id=new_submission.tenant_id,
            email=new_submission.email,
            name=new_submission.name,
            message=new_submission.message,
            geo_country=location.country if location else None,
            geo_city=location.city if location else None,
            geo_provider=location.provider if location else None,
            answers=new_submission.answers,
        )
        self._submissions.append(submission)
        return submission

    def all_for_tenant(self, tenant_id: int) -> list[Submission]:
        return [
            submission
            for submission in self._submissions
            if submission.tenant_id == tenant_id
        ]
