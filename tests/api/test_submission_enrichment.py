from collections.abc import Generator
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from app.api.geo_dependencies import get_geo_chain
from app.api.membership_dependencies import get_membership_repository
from app.api.rate_limit_dependencies import reset_rate_limiters
from app.api.submission_dependencies import get_submission_repository
from app.api.widget_dependencies import get_widget_repository
from app.core.auth import create_access_token
from app.core.geo import GeoLocation, GeoProviderChain
from app.main import app
from app.repositories.memberships import InMemoryMembershipRepository
from app.repositories.submissions import InMemorySubmissionRepository
from app.repositories.widgets import InMemoryWidgetRepository

ORIGIN = "http://localhost:5500"
PUBLIC_CLIENT = ("8.8.8.8", 5000)
LONDON = GeoLocation(country="GB", city="London")


class StaticProvider:
    def __init__(self, name: str, location: GeoLocation | None) -> None:
        self.name = name
        self._location = location
        self.calls = 0

    def lookup(self, ip_address: str) -> GeoLocation | None:
        self.calls += 1
        return self._location


class FailingProvider:
    def __init__(self, name: str) -> None:
        self.name = name
        self.calls = 0

    def lookup(self, ip_address: str) -> GeoLocation | None:
        self.calls += 1
        raise TimeoutError("provider down")


class ExplodingChain(GeoProviderChain):
    def lookup(self, ip_address: str) -> GeoLocation | None:
        raise RuntimeError("chain itself is broken")


@pytest.fixture
def submissions() -> Generator[InMemorySubmissionRepository]:
    widgets = InMemoryWidgetRepository()
    store = InMemorySubmissionRepository()
    memberships = InMemoryMembershipRepository({7: 10})
    app.dependency_overrides[get_widget_repository] = lambda: widgets
    app.dependency_overrides[get_submission_repository] = lambda: store
    app.dependency_overrides[get_membership_repository] = lambda: memberships
    reset_rate_limiters()
    yield store
    app.dependency_overrides.clear()
    reset_rate_limiters()


def use_chain(chain: GeoProviderChain) -> None:
    app.dependency_overrides[get_geo_chain] = lambda: chain


def post_submission(client: TestClient, widget_id: int, email: str) -> int:
    response = client.post(
        f"/api/v1/public/widgets/{widget_id}/submissions",
        headers={"Origin": ORIGIN},
        json={"email": email, "name": "Visitor"},
    )
    status_code: int = response.status_code
    return status_code


def create_widget(client: TestClient) -> int:
    token = create_access_token("user-7", timedelta(minutes=5))
    response = client.post(
        "/api/v1/widgets",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Geo target", "kind": "contact"},
    )
    return int(response.json()["id"])


def test_first_provider_enriches_the_stored_row(
    submissions: InMemorySubmissionRepository,
) -> None:
    primary = StaticProvider("alpha", LONDON)
    secondary = StaticProvider("beta", GeoLocation(country="DE", city="Berlin"))
    use_chain(GeoProviderChain([primary, secondary]))
    client = TestClient(app, client=PUBLIC_CLIENT)
    widget_id = create_widget(client)

    assert post_submission(client, widget_id, "geo@example.com") == 202

    stored = submissions.all_for_tenant(10)
    assert len(stored) == 1
    assert stored[0].geo_country == "GB"
    assert stored[0].geo_city == "London"
    assert stored[0].geo_provider == "alpha"
    assert secondary.calls == 0


def test_second_provider_enriches_when_first_fails(
    submissions: InMemorySubmissionRepository,
) -> None:
    primary = FailingProvider("alpha")
    secondary = StaticProvider("beta", LONDON)
    use_chain(GeoProviderChain([primary, secondary]))
    client = TestClient(app, client=PUBLIC_CLIENT)
    widget_id = create_widget(client)

    assert post_submission(client, widget_id, "geo@example.com") == 202

    stored = submissions.all_for_tenant(10)
    assert stored[0].geo_provider == "beta"
    assert stored[0].geo_country == "GB"
    assert primary.calls == 1


def test_submission_survives_every_provider_failing(
    submissions: InMemorySubmissionRepository,
) -> None:
    use_chain(GeoProviderChain([FailingProvider("alpha"), FailingProvider("beta")]))
    client = TestClient(app, client=PUBLIC_CLIENT)
    widget_id = create_widget(client)

    assert post_submission(client, widget_id, "degraded@example.com") == 202

    stored = submissions.all_for_tenant(10)
    assert len(stored) == 1
    assert stored[0].email == "degraded@example.com"
    assert stored[0].geo_country is None
    assert stored[0].geo_city is None
    assert stored[0].geo_provider is None


def test_submission_survives_a_broken_chain(
    submissions: InMemorySubmissionRepository,
) -> None:
    use_chain(ExplodingChain([]))
    client = TestClient(app, client=PUBLIC_CLIENT)
    widget_id = create_widget(client)

    assert post_submission(client, widget_id, "broken@example.com") == 202

    stored = submissions.all_for_tenant(10)
    assert len(stored) == 1
    assert stored[0].geo_provider is None


def test_private_client_address_stores_without_geo(
    submissions: InMemorySubmissionRepository,
) -> None:
    provider = StaticProvider("alpha", LONDON)
    use_chain(GeoProviderChain([provider]))
    client = TestClient(app, client=("127.0.0.1", 5000))
    widget_id = create_widget(client)

    assert post_submission(client, widget_id, "local@example.com") == 202

    stored = submissions.all_for_tenant(10)
    assert stored[0].geo_country is None
    assert provider.calls == 0
