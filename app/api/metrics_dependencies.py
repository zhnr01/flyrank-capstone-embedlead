import secrets
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status

from app.core.config import settings

METRICS_TOKEN_HEADER = "X-Metrics-Token"


def require_metrics_access(
    supplied_token: Annotated[str | None, Header(alias=METRICS_TOKEN_HEADER)] = None,
) -> None:
    expected = settings.metrics_token
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Not Found",
        )
    if supplied_token is None or not secrets.compare_digest(supplied_token, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid metrics token",
        )


MetricsAccess = Depends(require_metrics_access)
