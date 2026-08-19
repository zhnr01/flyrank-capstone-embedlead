from app.api.deps import SessionDep
from app.repositories.widgets import SqlAlchemyWidgetRepository, WidgetRepository


def get_widget_repository(session: SessionDep) -> WidgetRepository:
    return SqlAlchemyWidgetRepository(session)
