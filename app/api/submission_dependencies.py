from typing import Annotated

from fastapi import Depends

from app.api.deps import SessionDep
from app.repositories.submissions import (
    SqlAlchemySubmissionRepository,
    SubmissionRepository,
)


def get_submission_repository(session: SessionDep) -> SubmissionRepository:
    return SqlAlchemySubmissionRepository(session)


SubmissionRepositoryDep = Annotated[
    SubmissionRepository,
    Depends(get_submission_repository),
]
