from prometheus_client import CollectorRegistry

from app.core.prometheus_metrics import (
    HTTP_METHODS,
    OVERFLOW_LABEL,
    PrometheusMetrics,
    build_collectors,
)


def collectors() -> tuple[CollectorRegistry, PrometheusMetrics]:
    registry = CollectorRegistry()
    return registry, build_collectors(registry, max_routes=8)


def test_a_known_method_is_kept_verbatim() -> None:
    registry, metrics = collectors()

    metrics.observe_request(
        method="GET", route="/x", status_code=200, duration_seconds=0.01
    )

    assert (
        registry.get_sample_value(
            "embedlead_requests_total",
            {"method": "GET", "route": "/x", "status_class": "2xx"},
        )
        == 1
    )


def test_every_standard_verb_is_recognised() -> None:
    registry, metrics = collectors()

    for verb in HTTP_METHODS:
        metrics.observe_request(
            method=verb, route="/x", status_code=200, duration_seconds=0.01
        )

    labels = {
        sample.labels["method"]
        for metric in registry.collect()
        for sample in metric.samples
        if "method" in sample.labels
    }

    assert labels == set(HTTP_METHODS)


def test_an_unknown_verb_collapses_into_the_overflow_label() -> None:
    registry, metrics = collectors()

    for verb in ("FOOBAR", "AAAA", "BBBB", "CCCC"):
        metrics.observe_request(
            method=verb, route="/x", status_code=200, duration_seconds=0.01
        )

    labels = {
        sample.labels["method"]
        for metric in registry.collect()
        for sample in metric.samples
        if "method" in sample.labels
    }

    assert labels == {OVERFLOW_LABEL}


def test_unknown_verbs_are_still_all_counted() -> None:
    registry, metrics = collectors()

    for verb in ("FOOBAR", "AAAA", "BBBB"):
        metrics.observe_request(
            method=verb, route="/x", status_code=200, duration_seconds=0.01
        )

    assert (
        registry.get_sample_value(
            "embedlead_requests_total",
            {"method": OVERFLOW_LABEL, "route": "/x", "status_class": "2xx"},
        )
        == 3
    )


def test_a_lowercase_verb_is_normalised_not_treated_as_unknown() -> None:
    registry, metrics = collectors()

    metrics.observe_request(
        method="get", route="/x", status_code=200, duration_seconds=0.01
    )

    labels = {
        sample.labels["method"]
        for metric in registry.collect()
        for sample in metric.samples
        if "method" in sample.labels
    }

    assert labels == {"GET"}
