from typing import Literal

from fastapi import APIRouter, Response, status
from fastapi.responses import JSONResponse
from prometheus_client import CONTENT_TYPE_LATEST
from pydantic import BaseModel

from app.api.metrics_dependencies import MetricsAccess
from app.core.metrics import exposition
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
    response_class=Response,
    responses={
        status.HTTP_200_OK: {
            "content": {CONTENT_TYPE_LATEST: {}},
            "description": "Prometheus text exposition",
        },
        status.HTTP_401_UNAUTHORIZED: {"description": "Invalid metrics token"},
        status.HTTP_404_NOT_FOUND: {"description": "Metrics endpoint disabled"},
    },
)
async def metrics() -> Response:
    return Response(content=exposition(), media_type=CONTENT_TYPE_LATEST)
