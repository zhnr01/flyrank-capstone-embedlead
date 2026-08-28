from collections.abc import Generator

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.outbox import submission_created_key
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

TENANT_ID = 10
TOPIC = "submission.created"


@pytest.fixture
def session() -> Generator[Session]:
    engine = create_engine(
        settings.database_url,
        connect_args={"connect_timeout": settings.database_connect_timeout_seconds},
    )
    try:
        with engine.connect() as probe:
            probe.execute(text("SELECT 1"))
    except OperationalError:
        pytest.skip("PostgreSQL unreachable; JSONB and SAVEPOINT need the real engine")

    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with Session(engine) as open_session:
        open_session.add(TenantRecord(id=TENANT_ID, name="Acme"))
        open_session.add(
            WidgetRecord(id=1, tenant_id=TENANT_ID, name="Contact", kind="contact")
        )
        open_session.commit()
        yield open_session
    Base.metadata.drop_all(engine)


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
    return list(session.execute(select(SubmissionRecord.email)).scalars().all())


def test_duplicate_key_does_not_destroy_the_uncommitted_submission(
    session: Session,
) -> None:
    outbox = SqlAlchemyOutboxRepository(session)
    submission_id = store_lead(session, "lostlead@example.com")
    key = submission_created_key(submission_id)

    session.add(
        OutboxMessageRecord(
            topic=TOPIC,
            idempotency_key=key,
            payload={},
            status="pending",
            attempts=0,
        )
    )
    session.flush()

    duplicate = outbox.enqueue(topic=TOPIC, idempotency_key=key, payload={})
    session.commit()

    assert duplicate is None
    assert stored_emails(session) == ["lostlead@example.com"]


def test_duplicate_key_leaves_exactly_one_outbox_row(session: Session) -> None:
    outbox = SqlAlchemyOutboxRepository(session)
    submission_id = store_lead(session, "once@example.com")
    key = submission_created_key(submission_id)

    first = outbox.enqueue(topic=TOPIC, idempotency_key=key, payload={"n": 1})
    second = outbox.enqueue(topic=TOPIC, idempotency_key=key, payload={"n": 2})
    session.commit()

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
    outbox.enqueue(topic=TOPIC, idempotency_key=key, payload={})
    outbox.enqueue(topic=TOPIC, idempotency_key=key, payload={})

    second_id = store_lead(session, "second@example.com")
    outbox.enqueue(
        topic=TOPIC,
        idempotency_key=submission_created_key(second_id),
        payload={},
    )
    session.commit()

    assert sorted(stored_emails(session)) == [
        "first@example.com",
        "second@example.com",
    ]
    keys = session.execute(select(OutboxMessageRecord.idempotency_key)).scalars().all()
    assert len(set(keys)) == 2


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

    sql_first = sql_outbox.enqueue(topic=TOPIC, idempotency_key=key, payload={})
    sql_second = sql_outbox.enqueue(topic=TOPIC, idempotency_key=key, payload={})
    memory_first = memory_outbox.enqueue(topic=TOPIC, idempotency_key=key, payload={})
    memory_second = memory_outbox.enqueue(topic=TOPIC, idempotency_key=key, payload={})
    session.commit()

    assert (sql_first is None) == (memory_first is None)
    assert sql_second is None and memory_second is None
    assert len(stored_emails(session)) == 1
    assert len(memory_submissions.all_for_tenant(TENANT_ID)) == 1
