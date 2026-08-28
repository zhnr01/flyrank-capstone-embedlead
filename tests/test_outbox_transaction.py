from collections.abc import Generator

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.outbox import (
    SUBMISSION_CREATED_TOPIC,
    OutboxStatus,
    submission_created_key,
)
from app.models import (
    Base,
    OutboxMessageRecord,
    SubmissionRecord,
    TenantRecord,
    WidgetRecord,
)
from app.repositories.outbox import (
    InMemoryOutboxRepository,
    SqlAlchemyOutboxRepository,
)
from app.repositories.submissions import (
    InMemorySubmissionRepository,
    SqlAlchemySubmissionRepository,
)

TENANT_ID = 9010
TOPIC = "submission.created"
WIDGET_ID = 9001


@pytest.fixture
def session() -> Generator[Session]:
    engine = create_engine(
        settings.database_url,
        connect_args={"connect_timeout": settings.database_connect_timeout_seconds},
    )
    try:
        connection = engine.connect()
    except Exception:
        pytest.skip("PostgreSQL unreachable; JSONB and SAVEPOINT need the real engine")

    Base.metadata.create_all(connection)
    connection.commit()
    transaction = connection.begin()
    with Session(bind=connection, join_transaction_mode="create_savepoint") as scoped:
        scoped.merge(TenantRecord(id=TENANT_ID, name="Acme"))
        scoped.merge(
            WidgetRecord(
                id=WIDGET_ID, tenant_id=TENANT_ID, name="Contact", kind="contact"
            )
        )
        scoped.flush()
        yield scoped
    transaction.rollback()
    connection.close()


def store_lead(session: Session, email: str) -> int:
    submissions = SqlAlchemySubmissionRepository(session)
    submission = submissions.create(
        widget_id=1,
        tenant_id=TENANT_ID,
        email=email,
        name="Visitor",
        message="hello",
    )
    return submission.id


def stored_emails(session: Session) -> list[str]:
    return list(
        session.execute(
            select(SubmissionRecord.email).where(
                SubmissionRecord.tenant_id == TENANT_ID
            )
        )
        .scalars()
        .all()
    )


def test_duplicate_key_does_not_destroy_the_uncommitted_submission(
    session: Session,
) -> None:
    outbox = SqlAlchemyOutboxRepository(session)
    submission_id = store_lead(session, "lostlead@example.com")
    key = submission_created_key(submission_id)

    session.add(
        OutboxMessageRecord(
            topic=SUBMISSION_CREATED_TOPIC,
            idempotency_key=key,
            payload={},
            status=OutboxStatus.PENDING,
            attempts=0,
        )
    )
    session.flush()

    duplicate = outbox.enqueue(
        topic=SUBMISSION_CREATED_TOPIC,
        idempotency_key=key,
        payload={},
    )
    session.flush()

    assert duplicate is None
    assert stored_emails(session) == ["lostlead@example.com"]


def test_duplicate_key_leaves_exactly_one_outbox_row(session: Session) -> None:
    outbox = SqlAlchemyOutboxRepository(session)
    submission_id = store_lead(session, "once@example.com")
    key = submission_created_key(submission_id)

    first = outbox.enqueue(
        topic=SUBMISSION_CREATED_TOPIC,
        idempotency_key=key,
        payload={"n": 1},
    )
    second = outbox.enqueue(
        topic=SUBMISSION_CREATED_TOPIC,
        idempotency_key=key,
        payload={"n": 2},
    )
    session.flush()

    assert first is not None
    assert second is None
    rows = session.execute(
        select(OutboxMessageRecord).where(OutboxMessageRecord.idempotency_key == key)
    ).scalars().all()
    assert len(rows) == 1
    assert stored_emails(session) == ["once@example.com"]


def test_session_stays_usable_after_a_duplicate(session: Session) -> None:
    outbox = SqlAlchemyOutboxRepository(session)
    first_id = store_lead(session, "first@example.com")
    key = submission_created_key(first_id)
    outbox.enqueue(topic=SUBMISSION_CREATED_TOPIC, idempotency_key=key, payload={})
    outbox.enqueue(topic=SUBMISSION_CREATED_TOPIC, idempotency_key=key, payload={})

    second_id = store_lead(session, "second@example.com")
    outbox.enqueue(
        topic=SUBMISSION_CREATED_TOPIC,
        idempotency_key=submission_created_key(second_id),
        payload={},
    )
    session.flush()

    assert sorted(stored_emails(session)) == [
        "first@example.com",
        "second@example.com",
    ]
    expected = {submission_created_key(first_id), submission_created_key(second_id)}
    keys = (
        session.execute(
            select(OutboxMessageRecord.idempotency_key).where(
                OutboxMessageRecord.idempotency_key.in_(expected)
            )
        )
        .scalars()
        .all()
    )
    assert set(keys) == expected


def test_both_implementations_agree_on_duplicate_enqueue(session: Session) -> None:
    sql_outbox = SqlAlchemyOutboxRepository(session)
    memory_outbox = InMemoryOutboxRepository()
    memory_submissions = InMemorySubmissionRepository()

    sql_id = store_lead(session, "agree@example.com")
    memory_submissions.create(
        widget_id=1,
        tenant_id=TENANT_ID,
        email="agree@example.com",
        name="Visitor",
        message="hello",
    )
    key = submission_created_key(sql_id)

    sql_first = sql_outbox.enqueue(
        topic=SUBMISSION_CREATED_TOPIC,
        idempotency_key=key,
        payload={},
    )
    sql_second = sql_outbox.enqueue(
        topic=SUBMISSION_CREATED_TOPIC,
        idempotency_key=key,
        payload={},
    )
    memory_first = memory_outbox.enqueue(
        topic=SUBMISSION_CREATED_TOPIC,
        idempotency_key=key,
        payload={},
    )
    memory_second = memory_outbox.enqueue(
        topic=SUBMISSION_CREATED_TOPIC,
        idempotency_key=key,
        payload={},
    )
    session.flush()

    assert (sql_first is None) == (memory_first is None)
    assert sql_second is None and memory_second is None
    assert len(stored_emails(session)) == 1
    assert len(memory_submissions.all_for_tenant(TENANT_ID)) == 1
