from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Protocol

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import SubmissionRecord

MAX_TIMESERIES_DAYS = 365


@dataclass(frozen=True)
class SubmissionRow:
    id: int
    tenant_id: int
    widget_id: int
    email: str
    name: str
    message: str | None
    geo_country: str | None = None
    geo_city: str | None = None
    created_at: datetime | None = None


@dataclass(frozen=True)
class SubmissionPage:
    rows: list[SubmissionRow]
    next_after_id: int | None


@dataclass(frozen=True)
class CountryCount:
    country: str
    count: int


@dataclass(frozen=True)
class WidgetCount:
    widget_id: int
    count: int


@dataclass(frozen=True)
class DailyCount:
    day: date
    count: int


@dataclass(frozen=True)
class DashboardStats:
    total_submissions: int
    by_country: list[CountryCount]
    by_widget: list[WidgetCount]


def window_start(days: int) -> datetime:
    if days < 1:
        raise ValueError("days must be at least 1")
    if days > MAX_TIMESERIES_DAYS:
        raise ValueError(f"days must not exceed {MAX_TIMESERIES_DAYS}")
    return datetime.now(UTC) - timedelta(days=days)


class DashboardRepository(Protocol):
    def list_submissions(
        self,
        *,
        tenant_id: int,
        limit: int,
        after_id: int | None = None,
        widget_id: int | None = None,
    ) -> SubmissionPage: ...

    def stats(self, *, tenant_id: int) -> DashboardStats: ...

    def daily_counts(self, *, tenant_id: int, days: int) -> list[DailyCount]: ...


class SqlAlchemyDashboardRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_submissions(
        self,
        *,
        tenant_id: int,
        limit: int,
        after_id: int | None = None,
        widget_id: int | None = None,
    ) -> SubmissionPage:
        statement = (
            select(
                SubmissionRecord.id,
                SubmissionRecord.tenant_id,
                SubmissionRecord.widget_id,
                SubmissionRecord.email,
                SubmissionRecord.name,
                SubmissionRecord.message,
                SubmissionRecord.geo_country,
                SubmissionRecord.geo_city,
            )
            .where(SubmissionRecord.tenant_id == tenant_id)
            .order_by(SubmissionRecord.id.desc())
            .limit(limit + 1)
        )
        if after_id is not None:
            statement = statement.where(SubmissionRecord.id < after_id)
        if widget_id is not None:
            statement = statement.where(SubmissionRecord.widget_id == widget_id)

        records = self._session.execute(statement).all()
        rows = [
            SubmissionRow(
                id=record.id,
                tenant_id=record.tenant_id,
                widget_id=record.widget_id,
                email=record.email,
                name=record.name,
                message=record.message,
                geo_country=record.geo_country,
                geo_city=record.geo_city,
            )
            for record in records[:limit]
        ]
        next_after_id = rows[-1].id if len(records) > limit and rows else None
        return SubmissionPage(rows=rows, next_after_id=next_after_id)

    def stats(self, *, tenant_id: int) -> DashboardStats:
        total = self._session.execute(
            select(func.count())
            .select_from(SubmissionRecord)
            .where(SubmissionRecord.tenant_id == tenant_id)
        ).scalar_one()

        country_rows = self._session.execute(
            select(SubmissionRecord.geo_country, func.count().label("total"))
            .where(SubmissionRecord.tenant_id == tenant_id)
            .where(SubmissionRecord.geo_country.is_not(None))
            .group_by(SubmissionRecord.geo_country)
            .order_by(func.count().desc(), SubmissionRecord.geo_country)
        ).all()

        widget_rows = self._session.execute(
            select(SubmissionRecord.widget_id, func.count().label("total"))
            .where(SubmissionRecord.tenant_id == tenant_id)
            .group_by(SubmissionRecord.widget_id)
            .order_by(func.count().desc(), SubmissionRecord.widget_id)
        ).all()

        return DashboardStats(
            total_submissions=int(total),
            by_country=[
                CountryCount(country=row.geo_country, count=int(row.total))
                for row in country_rows
                if row.geo_country is not None
            ],
            by_widget=[
                WidgetCount(widget_id=row.widget_id, count=int(row.total))
                for row in widget_rows
            ],
        )

    def daily_counts(self, *, tenant_id: int, days: int) -> list[DailyCount]:
        since = window_start(days)
        day_column = func.date_trunc("day", SubmissionRecord.created_at).label("day")
        rows = self._session.execute(
            select(day_column, func.count().label("total"))
            .where(SubmissionRecord.tenant_id == tenant_id)
            .where(SubmissionRecord.created_at >= since)
            .group_by(day_column)
            .order_by(day_column)
        ).all()
        return [
            DailyCount(day=row.day.date(), count=int(row.total)) for row in rows
        ]


class InMemoryDashboardRepository:
    def __init__(self) -> None:
        self._rows: list[SubmissionRow] = []

    def add(self, row: SubmissionRow) -> None:
        self._rows.append(row)

    def list_submissions(
        self,
        *,
        tenant_id: int,
        limit: int,
        after_id: int | None = None,
        widget_id: int | None = None,
    ) -> SubmissionPage:
        matching = [row for row in self._rows if row.tenant_id == tenant_id]
        if after_id is not None:
            matching = [row for row in matching if row.id < after_id]
        if widget_id is not None:
            matching = [row for row in matching if row.widget_id == widget_id]
        matching.sort(key=lambda row: row.id, reverse=True)
        page = matching[:limit]
        next_after_id = page[-1].id if len(matching) > limit and page else None
        return SubmissionPage(rows=page, next_after_id=next_after_id)

    def stats(self, *, tenant_id: int) -> DashboardStats:
        matching = [row for row in self._rows if row.tenant_id == tenant_id]
        countries: dict[str, int] = {}
        widgets: dict[int, int] = {}
        for row in matching:
            if row.geo_country:
                countries[row.geo_country] = countries.get(row.geo_country, 0) + 1
            widgets[row.widget_id] = widgets.get(row.widget_id, 0) + 1
        return DashboardStats(
            total_submissions=len(matching),
            by_country=[
                CountryCount(country=country, count=count)
                for country, count in sorted(
                    countries.items(),
                    key=lambda country_total: (-country_total[1], country_total[0]),
                )
            ],
            by_widget=[
                WidgetCount(widget_id=widget, count=count)
                for widget, count in sorted(
                    widgets.items(),
                    key=lambda widget_total: (-widget_total[1], widget_total[0]),
                )
            ],
        )

    def daily_counts(self, *, tenant_id: int, days: int) -> list[DailyCount]:
        since = window_start(days)
        totals: dict[date, int] = {}
        for row in self._rows:
            if row.tenant_id != tenant_id or row.created_at is None:
                continue
            if row.created_at < since:
                continue
            day = row.created_at.date()
            totals[day] = totals.get(day, 0) + 1
        return [
            DailyCount(day=day, count=totals[day]) for day in sorted(totals)
        ]
