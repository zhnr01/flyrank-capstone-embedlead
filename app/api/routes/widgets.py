from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status
from fastapi.exceptions import HTTPException

from app.api.auth_dependencies import get_current_identity
from app.api.schemas.widgets import (
    WidgetCreate,
    WidgetListResponse,
    WidgetResponse,
    WidgetUpdate,
)
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


@router.get("", response_model=WidgetListResponse)
def list_widgets(
    identity: IdentityDep,
    repository: WidgetRepositoryDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    after_id: Annotated[int | None, Query(gt=0)] = None,
) -> WidgetListResponse:
    page = repository.list_for_tenant(
        identity=identity,
        limit=limit,
        after_id=after_id,
    )
    return WidgetListResponse(
        data=[WidgetResponse.model_validate(widget) for widget in page.data],
        next_after_id=page.next_after_id,
    )


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


@router.patch("/{widget_id}", response_model=WidgetResponse)
def update_widget(
    widget_id: int,
    payload: WidgetUpdate,
    identity: IdentityDep,
    repository: WidgetRepositoryDep,
) -> WidgetResponse:
    if not payload.model_fields_set:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="At least one widget field is required",
        )
    widget = repository.update_for_tenant(
        identity=identity,
        widget_id=widget_id,
        name=payload.name if "name" in payload.model_fields_set else None,
        kind=payload.kind if "kind" in payload.model_fields_set else None,
    )
    if widget is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Widget not found",
        )
    return WidgetResponse.model_validate(widget)


@router.delete("/{widget_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_widget(
    widget_id: int,
    identity: IdentityDep,
    repository: WidgetRepositoryDep,
) -> Response:
    deleted = repository.delete_for_tenant(
        identity=identity,
        widget_id=widget_id,
    )
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Widget not found",
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
