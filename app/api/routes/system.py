from typing import Literal

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.api.metrics_dependencies import MetricsAccess
from app.core.metrics import MetricsSnapshot, registry
from app.services.health import HealthReport, HealthStatus, readiness_report

router = APIRouter()


class LivenessResponse(BaseModel):
    status: Literal[HealthStatus.HEALTHY] = HealthStatus.HEALTHY


@router.get("/health/live", response_model=LivenessResponse)
async def liveness() -> LivenessResponse:
    return LivenessResponse()


@router.get(
    "/health/ready",
    response_model=HealthReport,
    responses={status.HTTP_503_SERVICE_UNAVAILABLE: {"model": HealthReport}},
)
async def readiness() -> HealthReport | JSONResponse:
    report = await readiness_report()
    if report.status == HealthStatus.UNHEALTHY:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=report.model_dump(mode="json", exclude_none=True),
        )
    return report


@router.get(
    "/metrics",
    dependencies=[MetricsAccess],
    responses={
        status.HTTP_401_UNAUTHORIZED: {"description": "Invalid metrics token"},
        status.HTTP_404_NOT_FOUND: {"description": "Metrics endpoint disabled"},
    },
)
async def metrics() -> MetricsSnapshot:
    return registry.snapshot()
