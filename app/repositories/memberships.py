from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.identity import Identity
from app.models import MembershipRecord


class MembershipRepository(Protocol):
    def get_identity_for_user(self, user_id: int) -> Identity | None: ...


class SqlAlchemyMembershipRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_identity_for_user(self, user_id: int) -> Identity | None:
        statement = (
            select(MembershipRecord.tenant_id)
            .where(MembershipRecord.user_id == user_id)
            .order_by(MembershipRecord.tenant_id)
            .limit(1)
        )
        tenant_id = self._session.scalar(statement)
        if tenant_id is None:
            return None
        return Identity(user_id=user_id, tenant_id=tenant_id)


class InMemoryMembershipRepository:
    def __init__(self, memberships: dict[int, int]) -> None:
        self._memberships = memberships

    def get_identity_for_user(self, user_id: int) -> Identity | None:
        tenant_id = self._memberships.get(user_id)
        if tenant_id is None:
            return None
        return Identity(user_id=user_id, tenant_id=tenant_id)
