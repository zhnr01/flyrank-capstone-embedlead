import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.api.geo_dependencies import GeoChainDep
from app.api.outbox_dependencies import OutboxRepositoryDep, UnitOfWorkDep
from app.api.rate_limit_dependencies import (
    client_address,
    enforce_submission_rate_limits,
)
from app.api.schemas.submissions import SubmissionAccepted
from app.api.submission_dependencies import SubmissionRepositoryDep
from app.api.widget_dependencies import WidgetRepositoryDep
from app.core.geo import GeoLocation, GeoProviderChain
from app.core.metrics import increment
from app.core.outbox import SUBMISSION_CREATED_TOPIC, submission_created_key
from app.core.submission_payload import SubmissionAnswers, validate_against_config
from app.repositories.submissions import NewSubmission, Submission
from app.repositories.widgets import OwnedWidget, Widget

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/public", tags=["public"])


@router.post(
    "/widgets/{widget_id}/submissions",
    response_model=SubmissionAccepted,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(enforce_submission_rate_limits)],
)
def create_submission(
    widget_id: int,
    payload: dict[str, object],
    request: Request,
    widgets: WidgetRepositoryDep,
    submissions: SubmissionRepositoryDep,
    outbox: OutboxRepositoryDep,
    unit_of_work: UnitOfWorkDep,
    geo_chain: GeoChainDep,
) -> SubmissionAccepted:
    ownership = public_widget_or_404(widgets, widget_id)
    answers = validated_answers_or_422(payload, ownership.widget)

    if answers.looks_automated:
        return drop_automated_submission(widget_id)

    location = enrich_without_failing(geo_chain, client_address(request))
    increment("geo_enrichment", "hit" if location else "miss")

    submission = submissions.create(
        NewSubmission(
            widget_id=ownership.widget.id,
            tenant_id=ownership.tenant_id,
            email=answers.email,
            name=answers.name,
            message=answers.message,
            location=location,
            answers=answers.values,
        )
    )
    enqueue_submission_notification(submission, outbox)
    unit_of_work.commit()
    increment("submission_stored", "ok")
    return SubmissionAccepted()


def public_widget_or_404(
    widgets: WidgetRepositoryDep,
    widget_id: int,
) -> OwnedWidget:
    ownership = widgets.get_public_with_ownership(widget_id=widget_id)
    if ownership is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Widget not found",
        )
    return ownership


def validated_answers_or_422(
    payload: dict[str, object],
    widget: Widget,
) -> SubmissionAnswers:
    try:
        return validate_against_config(payload, config=widget.config)
    except ValueError as error:
        increment("submission_rejected", "invalid_payload")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(error),
        ) from None


def drop_automated_submission(widget_id: int) -> SubmissionAccepted:
    increment("submission_dropped", "honeypot")
    logger.warning(
        "honeypot_triggered",
        extra={"fields": {"widget_id": widget_id}},
    )
    return SubmissionAccepted()


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


def enqueue_submission_notification(
    submission: Submission,
    outbox: OutboxRepositoryDep,
) -> None:
    outbox.enqueue(
        topic=SUBMISSION_CREATED_TOPIC,
        idempotency_key=submission_created_key(submission.id),
        payload={
            "submission_id": submission.id,
            "widget_id": submission.widget_id,
            "tenant_id": submission.tenant_id,
        },
    )
