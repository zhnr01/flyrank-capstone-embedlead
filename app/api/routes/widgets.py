from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.exceptions import HTTPException

from app.api.auth_dependencies import get_current_identity
from app.api.schemas.widgets import WidgetCreate, WidgetResponse
from app.api.widget_dependencies import get_widget_repository
from app.core.identity import Identity
from app.repositories.widgets import WidgetRepository

router = APIRouter(prefix="/widgets", tags=["widgets"])
IdentityDep = Annotated[Identity, Depends(get_current_identity)]
WidgetRepositoryDep = Annotated[WidgetRepository, Depends(get_widget_repository)]


@router.post("", response_model=WidgetResponse, status_code=status.HTTP_201_CREATED)
def create_widget(
    payload: WidgetCreate,
    identity: IdentityDep,
    repository: WidgetRepositoryDep,
) -> WidgetResponse:
    widget = repository.create(
        identity=identity,
        name=payload.name,
        kind=payload.kind,
    )
    return WidgetResponse.model_validate(widget)


@router.get("/{widget_id}", response_model=WidgetResponse)
def get_widget(
    widget_id: int,
    identity: IdentityDep,
    repository: WidgetRepositoryDep,
) -> WidgetResponse:
    widget = repository.get_for_tenant(
        identity=identity,
        widget_id=widget_id,
    )
    if widget is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Widget not found",
        )
    return WidgetResponse.model_validate(widget)
