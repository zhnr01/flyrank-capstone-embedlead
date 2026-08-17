from typing import Literal

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.services.health import HealthReport, readiness_report

router = APIRouter()


class LivenessResponse(BaseModel):
    status: Literal["healthy"] = "healthy"


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
    if report.status == "unhealthy":
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=report.model_dump(mode="json", exclude_none=True),
        )
    return report
