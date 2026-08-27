import logging

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.rate_limit_dependencies import enforce_submission_rate_limits
from app.api.request_limits import enforce_submission_size_limit
from app.api.schemas.submissions import SubmissionAccepted, SubmissionCreate
from app.api.submission_dependencies import SubmissionRepositoryDep
from app.api.widget_dependencies import WidgetRepositoryDep

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/public", tags=["public"])


@router.post(
    "/widgets/{widget_id}/submissions",
    response_model=SubmissionAccepted,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[
        Depends(enforce_submission_size_limit),
        Depends(enforce_submission_rate_limits),
    ],
)
def create_submission(
    widget_id: int,
    payload: SubmissionCreate,
    widgets: WidgetRepositoryDep,
    submissions: SubmissionRepositoryDep,
) -> SubmissionAccepted:
    ownership = widgets.get_ownership(widget_id=widget_id)
    if ownership is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Widget not found",
        )

    if payload.looks_automated:
        logger.warning("honeypot triggered for widget %s", widget_id)
        return SubmissionAccepted()

    submissions.create(
        widget_id=ownership.id,
        tenant_id=ownership.tenant_id,
        email=str(payload.email),
        name=payload.name,
        message=payload.message,
    )
    return SubmissionAccepted()
