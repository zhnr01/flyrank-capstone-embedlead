from collections.abc import Generator
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import Base, SubmissionRecord, TenantRecord, WidgetRecord
from app.repositories.dashboard import (
    InMemoryDashboardRepository,
    SqlAlchemyDashboardRepository,
    SubmissionRow,
)

TENANT_ID = 10
OTHER_TENANT_ID = 20
WIDGET_ID = 1
OTHER_WIDGET_ID = 2
DAY = (datetime.now(UTC) - timedelta(days=3)).replace(
    hour=0, minute=0, second=0, microsecond=0
)
DAY_LABEL = DAY.date().isoformat()
NEXT_DAY_LABEL = (DAY + timedelta(days=1)).date().isoformat()


@pytest.fixture
def session() -> Generator[Session]:
    engine = create_engine(
        settings.database_url,
        connect_args={"connect_timeout": settings.database_connect_timeout_seconds},
    )
    try:
        connection = engine.connect()
    except Exception:
        pytest.skip("PostgreSQL unreachable; date_trunc needs the real engine")

    Base.metadata.create_all(connection)
    connection.commit()
    transaction = connection.begin()
    with Session(bind=connection, join_transaction_mode="create_savepoint") as scoped:
        scoped.add(TenantRecord(id=TENANT_ID, name="Acme"))
        scoped.add(TenantRecord(id=OTHER_TENANT_ID, name="Rival"))
        scoped.add(
            WidgetRecord(
                id=WIDGET_ID, tenant_id=TENANT_ID, name="Contact", kind="contact"
            )
        )
        scoped.add(
            WidgetRecord(
                id=OTHER_WIDGET_ID,
                tenant_id=OTHER_TENANT_ID,
                name="Rival form",
                kind="contact",
            )
        )
        scoped.flush()
        yield scoped
    transaction.rollback()
    connection.close()


def add_submission(
    session: Session,
    *,
    created_at: datetime,
    tenant_id: int = TENANT_ID,
    widget_id: int = WIDGET_ID,
    email: str = "visitor@example.com",
) -> None:
    session.add(
        SubmissionRecord(
            widget_id=widget_id,
            tenant_id=tenant_id,
            email=email,
            name="Visitor",
            message="hello",
            created_at=created_at,
        )
    )
    session.flush()


def test_daily_counts_group_submissions_by_calendar_day(session: Session) -> None:
    add_submission(session, created_at=DAY)
    add_submission(session, created_at=DAY + timedelta(hours=5))
    add_submission(session, created_at=DAY + timedelta(days=1))
    session.flush()

    daily = SqlAlchemyDashboardRepository(session).daily_counts(
        tenant_id=TENANT_ID, days=30
    )

    counts = {point.day.isoformat(): point.count for point in daily}
    assert counts == {DAY_LABEL: 2, NEXT_DAY_LABEL: 1}


def test_daily_counts_are_ordered_oldest_first(session: Session) -> None:
    add_submission(session, created_at=DAY + timedelta(days=2))
    add_submission(session, created_at=DAY)
    add_submission(session, created_at=DAY + timedelta(days=1))
    session.flush()

    daily = SqlAlchemyDashboardRepository(session).daily_counts(
        tenant_id=TENANT_ID, days=30
    )

    days = [point.day.isoformat() for point in daily]
    assert days == sorted(days)


def test_daily_counts_never_leak_another_tenant(session: Session) -> None:
    add_submission(session, created_at=DAY)
    add_submission(
        session,
        created_at=DAY,
        tenant_id=OTHER_TENANT_ID,
        widget_id=OTHER_WIDGET_ID,
        email="rival@example.com",
    )
    session.flush()

    daily = SqlAlchemyDashboardRepository(session).daily_counts(
        tenant_id=TENANT_ID, days=30
    )

    assert sum(point.count for point in daily) == 1


def test_daily_counts_window_excludes_older_submissions(session: Session) -> None:
    now = datetime.now(UTC)
    add_submission(session, created_at=now - timedelta(days=1))
    add_submission(session, created_at=now - timedelta(days=90))
    session.flush()

    daily = SqlAlchemyDashboardRepository(session).daily_counts(
        tenant_id=TENANT_ID, days=7
    )

    assert sum(point.count for point in daily) == 1


def test_daily_counts_rejects_a_non_positive_window(session: Session) -> None:
    repository = SqlAlchemyDashboardRepository(session)

    with pytest.raises(ValueError):
        repository.daily_counts(tenant_id=TENANT_ID, days=0)


def test_daily_counts_rejects_an_unbounded_window(session: Session) -> None:
    repository = SqlAlchemyDashboardRepository(session)

    with pytest.raises(ValueError):
        repository.daily_counts(tenant_id=TENANT_ID, days=366)


def test_empty_tenant_has_no_daily_points(session: Session) -> None:
    daily = SqlAlchemyDashboardRepository(session).daily_counts(
        tenant_id=TENANT_ID, days=30
    )

    assert daily == []


def test_both_implementations_agree_on_daily_counts(session: Session) -> None:
    memory = InMemoryDashboardRepository()
    entries = ((0, "a@example.com"), (0, "b@example.com"), (1, "c@example.com"))
    for row_id, (offset, email) in enumerate(entries, start=1):
        created = DAY + timedelta(days=offset)
        add_submission(session, created_at=created, email=email)
        memory.add(
            SubmissionRow(
                id=row_id,
                tenant_id=TENANT_ID,
                widget_id=WIDGET_ID,
                email=email,
                name="Visitor",
                message="hello",
                created_at=created,
            )
        )
    session.flush()

    sql_daily = SqlAlchemyDashboardRepository(session).daily_counts(
        tenant_id=TENANT_ID, days=365
    )
    memory_daily = memory.daily_counts(tenant_id=TENANT_ID, days=365)

    assert [(point.day, point.count) for point in sql_daily] == [
        (point.day, point.count) for point in memory_daily
    ]
