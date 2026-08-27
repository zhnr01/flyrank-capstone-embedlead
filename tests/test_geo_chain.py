import pytest

from app.core.geo import GeoLocation, GeoProviderChain


class StaticProvider:
    def __init__(self, name: str, location: GeoLocation | None) -> None:
        self.name = name
        self._location = location
        self.calls = 0

    def lookup(self, ip_address: str) -> GeoLocation | None:
        self.calls += 1
        return self._location


class FailingProvider:
    def __init__(self, name: str, error: Exception | None = None) -> None:
        self.name = name
        self._error = error or TimeoutError("provider unreachable")
        self.calls = 0

    def lookup(self, ip_address: str) -> GeoLocation | None:
        self.calls += 1
        raise self._error


PUBLIC_IP = "8.8.8.8"
LONDON = GeoLocation(country="GB", city="London")
BERLIN = GeoLocation(country="DE", city="Berlin")


def test_first_answer_wins_and_later_providers_are_not_called() -> None:
    first = StaticProvider("alpha", LONDON)
    second = StaticProvider("beta", BERLIN)
    chain = GeoProviderChain([first, second])

    result = chain.lookup(PUBLIC_IP)

    assert result is not None
    assert result.country == "GB"
    assert result.provider == "alpha"
    assert first.calls == 1
    assert second.calls == 0


def test_failing_provider_advances_to_the_next() -> None:
    first = FailingProvider("alpha")
    second = StaticProvider("beta", BERLIN)
    chain = GeoProviderChain([first, second])

    result = chain.lookup(PUBLIC_IP)

    assert result is not None
    assert result.city == "Berlin"
    assert result.provider == "beta"
    assert first.calls == 1
    assert second.calls == 1


def test_empty_answer_advances_to_the_next() -> None:
    first = StaticProvider("alpha", None)
    second = StaticProvider("beta", BERLIN)
    chain = GeoProviderChain([first, second])

    result = chain.lookup(PUBLIC_IP)

    assert result is not None
    assert result.provider == "beta"
    assert first.calls == 1


def test_all_providers_failing_returns_none() -> None:
    first = FailingProvider("alpha")
    second = FailingProvider("beta", ValueError("unexpected payload"))
    chain = GeoProviderChain([first, second])

    assert chain.lookup(PUBLIC_IP) is None
    assert first.calls == 1
    assert second.calls == 1


def test_chain_with_no_providers_returns_none() -> None:
    assert GeoProviderChain([]).lookup(PUBLIC_IP) is None


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",
        "10.0.0.5",
        "192.168.1.20",
        "203.0.113.10",
        "::1",
        "not-an-ip",
        "",
    ],
)
def test_unroutable_or_invalid_addresses_skip_every_provider(address: str) -> None:
    provider = StaticProvider("alpha", LONDON)
    chain = GeoProviderChain([provider])

    assert chain.lookup(address) is None
    assert provider.calls == 0
