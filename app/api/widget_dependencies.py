from typing import Annotated

from fastapi import Depends

from app.api.deps import SessionDep
from app.repositories.widgets import SqlAlchemyWidgetRepository, WidgetRepository


def get_widget_repository(session: SessionDep) -> WidgetRepository:
    return SqlAlchemyWidgetRepository(session)


WidgetRepositoryDep = Annotated[WidgetRepository, Depends(get_widget_repository)]
