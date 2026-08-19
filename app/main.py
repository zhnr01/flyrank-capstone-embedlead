from fastapi import FastAPI

from app.api.routes import system, widgets
from app.core.config import settings

app = FastAPI(
    title=settings.project_name,
    openapi_url="/api/v1/openapi.json",
)
app.include_router(system.router, prefix="/api/v1/system", tags=["system"])
app.include_router(widgets.router, prefix="/api/v1")
