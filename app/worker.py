import logging
import sys
import time

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import engine
from app.repositories.outbox import SqlAlchemyOutboxRepository
from app.services.notifications import LoggingNotificationTransport
from app.services.outbox_worker import OutboxWorker

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("app.worker")


def run_outbox_worker(*, once: bool) -> int:
    transport = LoggingNotificationTransport()
    delivered_total = 0
    while True:
        with Session(engine) as session:
            repository = SqlAlchemyOutboxRepository(session)
            worker = OutboxWorker(
                repository,
                transport,
                max_attempts=settings.outbox_max_attempts,
                batch_size=settings.outbox_batch_size,
            )
            delivered = worker.run_once()
        delivered_total += delivered
        if delivered:
            logger.info("outbox batch delivered=%s", delivered)
        if once:
            return delivered_total
        time.sleep(settings.outbox_poll_seconds)


def main() -> int:
    once = "--once" in sys.argv
    delivered = run_outbox_worker(once=once)
    logger.info("outbox worker finished delivered=%s", delivered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
