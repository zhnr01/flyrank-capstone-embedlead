from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.body_limit import BodySizeLimitMiddleware
from app.api.request_context import RequestContextMiddleware
from app.api.routes import (
    auth,
    dashboard,
    public_submissions,
    public_widgets,
    system,
    widgets,
)
from app.core.config import settings
from app.core.logging_config import configure_logging

configure_logging(settings.log_level)

app = FastAPI(
    title=settings.project_name,
    openapi_url="/api/v1/openapi.json",
)

app.add_middleware(RequestContextMiddleware)

app.add_middleware(
    BodySizeLimitMiddleware,
    max_bytes=settings.max_submission_bytes,
)

if settings.backend_cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.backend_cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type"],
        max_age=600,
    )

app.include_router(system.router, prefix="/api/v1/system", tags=["system"])
app.include_router(widgets.router, prefix="/api/v1")
app.include_router(auth.router, prefix="/api/v1")
app.include_router(public_submissions.router, prefix="/api/v1")
app.include_router(public_widgets.router, prefix="/api/v1")
app.include_router(dashboard.router, prefix="/api/v1")
