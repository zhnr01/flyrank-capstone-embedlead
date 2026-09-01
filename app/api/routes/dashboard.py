from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.auth_dependencies import get_current_identity
from app.api.dashboard_dependencies import DashboardRepositoryDep
from app.api.schemas.dashboard import (
    CountryCountResponse,
    DailyCountResponse,
    DashboardStatsResponse,
    DashboardSubmission,
    DashboardSubmissionList,
    WidgetCountResponse,
)
from app.core.identity import Identity
from app.repositories.dashboard import MAX_TIMESERIES_DAYS

DEFAULT_STATS_DAYS = 30

router = APIRouter(prefix="/dashboard", tags=["dashboard"])
IdentityDep = Annotated[Identity, Depends(get_current_identity)]


@router.get("/submissions", response_model=DashboardSubmissionList)
def list_submissions(
    identity: IdentityDep,
    repository: DashboardRepositoryDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    after_id: Annotated[int | None, Query(ge=1)] = None,
    widget_id: Annotated[int | None, Query(ge=1)] = None,
) -> DashboardSubmissionList:
    page = repository.list_submissions(
        tenant_id=identity.tenant_id,
        limit=limit,
        after_id=after_id,
        widget_id=widget_id,
    )
    return DashboardSubmissionList(
        data=[
            DashboardSubmission(
                id=row.id,
                widget_id=row.widget_id,
                email=row.email,
                name=row.name,
                message=row.message,
                geo_country=row.geo_country,
                geo_city=row.geo_city,
            )
            for row in page.rows
        ],
        next_after_id=page.next_after_id,
    )


@router.get("/stats", response_model=DashboardStatsResponse)
def submission_stats(
    identity: IdentityDep,
    repository: DashboardRepositoryDep,
    days: Annotated[int, Query(ge=1, le=MAX_TIMESERIES_DAYS)] = DEFAULT_STATS_DAYS,
) -> DashboardStatsResponse:
    stats = repository.stats(tenant_id=identity.tenant_id)
    daily = repository.daily_counts(tenant_id=identity.tenant_id, days=days)
    return DashboardStatsResponse(
        total_submissions=stats.total_submissions,
        by_country=[
            CountryCountResponse(
                country=country_count.country,
                count=country_count.count,
            )
            for country_count in stats.by_country
        ],
        by_widget=[
            WidgetCountResponse(
                widget_id=widget_count.widget_id,
                count=widget_count.count,
            )
            for widget_count in stats.by_widget
        ],
        by_day=[
            DailyCountResponse(day=daily_count.day, count=daily_count.count)
            for daily_count in daily
        ],
    )
