from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, Response, status

from app.api.schemas.widgets import WidgetConfigResponse
from app.api.widget_dependencies import WidgetRepositoryDep
from app.core.caching import content_etag, etag_matches
from app.core.config import settings

router = APIRouter(prefix="/public/widgets", tags=["public"])

BUNDLE_DIRECTORY = Path(__file__).resolve().parent.parent.parent / "static"
IMMUTABLE_CACHE_CONTROL = "public, max-age=31536000, immutable"


@router.get(
    "/{widget_id}/config",
    response_model=None,
    responses={
        200: {"model": WidgetConfigResponse},
        304: {"description": "Config unchanged"},
    },
)
def widget_config(
    widget_id: int,
    request: Request,
    response: Response,
    widgets: WidgetRepositoryDep,
) -> Response | WidgetConfigResponse:
    widget = widgets.get_public(widget_id=widget_id)
    if widget is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Widget not found",
        )

    payload: dict[str, object] = {
        "widget_id": widget.id,
        "name": widget.name,
        "kind": widget.kind,
        "version": settings.widget_bundle_version,
    }
    etag = content_etag(payload)
    cache_control = (
        f"public, max-age={settings.widget_config_cache_seconds}, must-revalidate"
    )

    if etag_matches(request.headers.get("if-none-match"), etag):
        return Response(
            status_code=status.HTTP_304_NOT_MODIFIED,
            headers={"ETag": etag, "Cache-Control": cache_control},
        )

    response.headers["ETag"] = etag
    response.headers["Cache-Control"] = cache_control
    return WidgetConfigResponse.model_validate(payload)


@router.get("/bundle/{version}/widget.js")
def widget_bundle(version: str) -> Response:
    bundle_path = BUNDLE_DIRECTORY / f"widget-{version}.js"
    if version != settings.widget_bundle_version or not bundle_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Bundle version not found",
        )
    return Response(
        content=bundle_path.read_text(encoding="utf-8"),
        media_type="application/javascript",
        headers={"Cache-Control": IMMUTABLE_CACHE_CONTROL},
    )
