from typing import Annotated

from fastapi import Depends

from app.api.deps import SessionDep
from app.repositories.dashboard import (
    DashboardRepository,
    SqlAlchemyDashboardRepository,
)


def get_dashboard_repository(session: SessionDep) -> DashboardRepository:
    return SqlAlchemyDashboardRepository(session)


DashboardRepositoryDep = Annotated[
    DashboardRepository,
    Depends(get_dashboard_repository),
]
