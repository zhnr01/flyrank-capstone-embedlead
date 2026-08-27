from typing import Annotated

from fastapi import Depends

from app.api.deps import SessionDep
from app.repositories.memberships import (
    MembershipRepository,
    SqlAlchemyMembershipRepository,
)


def get_membership_repository(session: SessionDep) -> MembershipRepository:
    return SqlAlchemyMembershipRepository(session)


MembershipRepositoryDep = Annotated[
    MembershipRepository,
    Depends(get_membership_repository),
]
