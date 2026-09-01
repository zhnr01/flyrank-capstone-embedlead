from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status
from fastapi.exceptions import HTTPException

from app.api.auth_dependencies import get_current_identity
from app.api.schemas.widgets import (
    WidgetCreate,
    WidgetEmbedResponse,
    WidgetListResponse,
    WidgetResponse,
    WidgetUpdate,
)
from app.api.widget_dependencies import get_widget_repository
from app.core.config import settings
from app.core.identity import Identity
from app.core.widget_config import default_config
from app.repositories.widgets import WidgetChanges, WidgetRepository

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
        config=payload.config if payload.config is not None else default_config(),
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
        data=[WidgetResponse.model_validate(widget) for widget in page.widgets],
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
        changes=WidgetChanges(
            name=payload.name,
            kind=payload.kind,
            config=payload.config,
        ),
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


@router.get("/{widget_id}/embed", response_model=WidgetEmbedResponse)
def widget_embed_snippet(
    widget_id: int,
    identity: IdentityDep,
    repository: WidgetRepositoryDep,
) -> WidgetEmbedResponse:
    widget = repository.get_for_tenant(identity=identity, widget_id=widget_id)
    if widget is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Widget not found",
        )
    version = settings.widget_bundle_version
    base = settings.public_base_url.rstrip("/")
    bundle_url = f"{base}/api/v1/public/widgets/bundle/{version}/widget.js"
    snippet = (
        f'<script src="{bundle_url}" '
        f'data-widget-id="{widget.id}" async></script>'
    )
    return WidgetEmbedResponse(
        widget_id=widget.id,
        bundle_version=version,
        bundle_url=bundle_url,
        snippet=snippet,
    )
