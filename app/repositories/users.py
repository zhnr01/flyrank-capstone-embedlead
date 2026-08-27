from dataclasses import dataclass
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import UserRecord


@dataclass(frozen=True)
class User:
    id: int
    email: str
    password_hash: str


class UserRepository(Protocol):
    def get_by_email(self, email: str) -> User | None: ...


class SqlAlchemyUserRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_email(self, email: str) -> User | None:
        record = self._session.scalar(
            select(UserRecord).where(UserRecord.email == email)
        )
        if record is None:
            return None
        return User(
            id=record.id,
            email=record.email,
            password_hash=record.password_hash,
        )


class InMemoryUserRepository:
    def __init__(self, users: dict[str, User]) -> None:
        self._users = users

    def get_by_email(self, email: str) -> User | None:
        return self._users.get(email)
