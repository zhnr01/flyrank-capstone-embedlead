from pytest import MonkeyPatch

from app.api.geo_dependencies import build_geo_chain
from app.core.config import settings


def test_both_providers_are_present_by_default() -> None:
    chain = build_geo_chain()

    assert len(chain.providers) == 2


def test_disabling_provider_a_leaves_the_fallback_in_place(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "geo_provider_a_enabled", False)

    chain = build_geo_chain()

    assert [type(provider).__name__ for provider in chain.providers] == [
        "IpapiCoProvider"
    ]


def test_disabling_provider_b_leaves_the_primary_in_place(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "geo_provider_b_enabled", False)

    chain = build_geo_chain()

    assert [type(provider).__name__ for provider in chain.providers] == [
        "IpApiProvider"
    ]


def test_disabling_both_providers_yields_an_empty_chain(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "geo_provider_a_enabled", False)
    monkeypatch.setattr(settings, "geo_provider_b_enabled", False)

    chain = build_geo_chain()

    assert chain.providers == ()


def test_the_master_switch_still_overrides_both_toggles(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "geo_enrichment_enabled", False)
    monkeypatch.setattr(settings, "geo_provider_a_enabled", True)
    monkeypatch.setattr(settings, "geo_provider_b_enabled", True)

    chain = build_geo_chain()

    assert chain.providers == ()
