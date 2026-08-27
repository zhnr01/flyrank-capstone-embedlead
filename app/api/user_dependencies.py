from typing import Annotated

from fastapi import Depends

from app.api.deps import SessionDep
from app.repositories.users import SqlAlchemyUserRepository, UserRepository


def get_user_repository(session: SessionDep) -> UserRepository:
    return SqlAlchemyUserRepository(session)


UserRepositoryDep = Annotated[UserRepository, Depends(get_user_repository)]
