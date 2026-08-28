from pydantic import BaseModel


class DashboardSubmission(BaseModel):
    id: int
    widget_id: int
    email: str
    name: str
    message: str | None
    geo_country: str | None
    geo_city: str | None


class DashboardSubmissionList(BaseModel):
    data: list[DashboardSubmission]
    next_after_id: int | None


class CountryCountResponse(BaseModel):
    country: str
    count: int


class WidgetCountResponse(BaseModel):
    widget_id: int
    count: int


class DashboardStatsResponse(BaseModel):
    total_submissions: int
    by_country: list[CountryCountResponse]
    by_widget: list[WidgetCountResponse]
