import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.api.geo_dependencies import GeoChainDep
from app.api.outbox_dependencies import OutboxRepositoryDep, UnitOfWorkDep
from app.api.rate_limit_dependencies import (
    client_address,
    enforce_submission_rate_limits,
)
from app.api.schemas.submissions import SubmissionAccepted, SubmissionCreate
from app.api.submission_dependencies import SubmissionRepositoryDep
from app.api.widget_dependencies import WidgetRepositoryDep
from app.core.geo import GeoLocation, GeoProviderChain
from app.core.metrics import increment
from app.core.outbox import submission_created_key

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/public", tags=["public"])


def enrich_without_failing(
    chain: GeoProviderChain,
    ip_address: str,
) -> GeoLocation | None:
    try:
        return chain.lookup(ip_address)
    except Exception:
        increment("geo_enrichment", "error")
        logger.warning("geo_enrichment_failed", exc_info=True)
        return None


@router.post(
    "/widgets/{widget_id}/submissions",
    response_model=SubmissionAccepted,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[
        Depends(enforce_submission_rate_limits),
    ],
)
def create_submission(
    widget_id: int,
    payload: SubmissionCreate,
    request: Request,
    widgets: WidgetRepositoryDep,
    submissions: SubmissionRepositoryDep,
    outbox: OutboxRepositoryDep,
    unit_of_work: UnitOfWorkDep,
    geo_chain: GeoChainDep,
) -> SubmissionAccepted:
    ownership = widgets.get_ownership(widget_id=widget_id)
    if ownership is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Widget not found",
        )

    if payload.looks_automated:
        increment("submission_dropped", "honeypot")
        logger.warning(
            "honeypot_triggered",
            extra={"fields": {"widget_id": widget_id}},
        )
        return SubmissionAccepted()

    location = enrich_without_failing(geo_chain, client_address(request))
    increment("geo_enrichment", "hit" if location else "miss")

    submission = submissions.create(
        widget_id=ownership.id,
        tenant_id=ownership.tenant_id,
        email=str(payload.email),
        name=payload.name,
        message=payload.message,
        location=location,
    )
    outbox.enqueue(
        topic="submission.created",
        idempotency_key=submission_created_key(submission.id),
        payload={
            "submission_id": submission.id,
            "widget_id": submission.widget_id,
            "tenant_id": submission.tenant_id,
        },
    )
    unit_of_work.commit()
    increment("submission_stored", "ok")
    return SubmissionAccepted()
