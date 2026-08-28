import logging

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.auth import get_password_hash
from app.core.db import engine
from app.core.widget_config import CONTACT_KIND, default_config
from app.models import MembershipRecord, TenantRecord, UserRecord, WidgetRecord

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("app.seed")

DEMO_PASSWORD = "local-demo-password"

DEMO_TENANTS = [(10, "Acme Coffee"), (20, "Globex Tools")]
DEMO_USERS = [(7, "owner@acme.example", 10), (8, "owner@globex.example", 20)]
DEMO_WIDGETS = [
    (1, 10, "Acme contact form", CONTACT_KIND),
    (2, 20, "Globex contact form", CONTACT_KIND),
]


def seed() -> None:
    with Session(engine) as session:
        for tenant_id, name in DEMO_TENANTS:
            if session.get(TenantRecord, tenant_id) is None:
                session.add(TenantRecord(id=tenant_id, name=name))
        session.flush()

        for user_id, email, tenant_id in DEMO_USERS:
            existing = session.execute(
                select(UserRecord).where(UserRecord.email == email)
            ).scalar_one_or_none()
            if existing is None:
                session.add(
                    UserRecord(
                        id=user_id,
                        email=email,
                        password_hash=get_password_hash(DEMO_PASSWORD),
                    )
                )
            membership = session.get(MembershipRecord, (user_id, tenant_id))
            if membership is None:
                session.add(
                    MembershipRecord(
                        user_id=user_id,
                        tenant_id=tenant_id,
                        role="owner",
                    )
                )
        session.flush()

        for widget_id, tenant_id, name, kind in DEMO_WIDGETS:
            if session.get(WidgetRecord, widget_id) is None:
                session.add(
                    WidgetRecord(
                        id=widget_id,
                        tenant_id=tenant_id,
                        name=name,
                        kind=kind,
                        config=default_config().model_dump(mode="json"),
                    )
                )
        session.commit()

        for table in ("tenants", "users", "widgets"):
            session.execute(
                text(
                    f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), "
                    f"GREATEST((SELECT COALESCE(MAX(id), 1) FROM {table}), 1))"
                )
            )
        session.commit()

    logger.info(
        "seed complete: tenants=%s widgets=%s",
        len(DEMO_TENANTS),
        len(DEMO_WIDGETS),
    )
    logger.info("demo login: owner@acme.example / widget id 1")


if __name__ == "__main__":
    seed()
