from prometheus_client import CollectorRegistry

from app.core.prometheus_metrics import (
    LATENCY_BUCKETS_SECONDS,
    PrometheusMetrics,
    build_collectors,
    render_exposition,
)


def collectors() -> tuple[CollectorRegistry, PrometheusMetrics]:
    registry = CollectorRegistry()
    return registry, build_collectors(registry)


def test_a_counter_is_exposed_with_the_total_suffix() -> None:
    registry, metrics = collectors()

    metrics.increment("submission_stored", "ok")
    text = render_exposition(registry)

    assert "embedlead_events_total" in text
    assert 'name="submission_stored"' in text
    assert 'outcome="ok"' in text


def test_help_and_type_lines_precede_the_samples() -> None:
    registry, metrics = collectors()

    metrics.increment("submission_stored", "ok")
    lines = render_exposition(registry).splitlines()

    help_index = next(
        index
        for index, line in enumerate(lines)
        if line.startswith("# HELP embedlead_events")
    )
    type_index = next(
        index
        for index, line in enumerate(lines)
        if line.startswith("# TYPE embedlead_events")
    )
    sample_index = next(
        index
        for index, line in enumerate(lines)
        if line.startswith("embedlead_events_total{")
    )

    assert help_index < sample_index
    assert type_index < sample_index


def test_the_histogram_carries_bucket_sum_and_count() -> None:
    registry, metrics = collectors()

    metrics.observe_request(
        method="GET", route="/x", status_code=200, duration_seconds=0.01
    )
    text = render_exposition(registry)

    assert "embedlead_request_duration_seconds_bucket" in text
    assert "embedlead_request_duration_seconds_sum" in text
    assert "embedlead_request_duration_seconds_count" in text


def test_the_histogram_declares_the_mandatory_positive_infinity_bucket() -> None:
    registry, metrics = collectors()

    metrics.observe_request(
        method="GET", route="/x", status_code=200, duration_seconds=0.01
    )
    text = render_exposition(registry)

    assert 'le="+Inf"' in text


def test_buckets_are_cumulative_so_the_infinity_bucket_equals_the_count() -> None:
    registry, metrics = collectors()
    for seconds in (0.001, 0.03, 4.0):
        metrics.observe_request(
            method="GET", route="/x", status_code=200, duration_seconds=seconds
        )

    infinity = registry.get_sample_value(
        "embedlead_request_duration_seconds_bucket",
        {"method": "GET", "route": "/x", "le": "+Inf"},
    )
    count = registry.get_sample_value(
        "embedlead_request_duration_seconds_count",
        {"method": "GET", "route": "/x"},
    )

    assert infinity == count == 3


def test_a_low_bucket_only_counts_observations_at_or_below_its_bound() -> None:
    registry, metrics = collectors()
    for seconds in (0.001, 4.0):
        metrics.observe_request(
            method="GET", route="/y", status_code=200, duration_seconds=seconds
        )

    smallest = registry.get_sample_value(
        "embedlead_request_duration_seconds_bucket",
        {"method": "GET", "route": "/y", "le": str(LATENCY_BUCKETS_SECONDS[0])},
    )

    assert smallest == 1


def test_requests_are_counted_by_status_class_not_by_raw_status() -> None:
    registry, metrics = collectors()

    metrics.observe_request(
        method="GET", route="/z", status_code=404, duration_seconds=0.01
    )
    metrics.observe_request(
        method="GET", route="/z", status_code=422, duration_seconds=0.01
    )

    value = registry.get_sample_value(
        "embedlead_requests_total",
        {"method": "GET", "route": "/z", "status_class": "4xx"},
    )

    assert value == 2


def test_the_exposition_is_scrapeable_text_not_json() -> None:
    registry, metrics = collectors()
    metrics.increment("submission_stored", "ok")

    text = render_exposition(registry)

    assert not text.lstrip().startswith("{")
    assert "\n" in text


def test_no_sample_line_contains_a_bare_infinity_token() -> None:
    registry, metrics = collectors()
    metrics.observe_request(
        method="GET", route="/x", status_code=200, duration_seconds=9.0
    )

    text = render_exposition(registry)

    for line in text.splitlines():
        if line.startswith("#"):
            continue
        assert "Infinity" not in line


def test_cardinality_is_bounded_by_collapsing_unknown_routes() -> None:
    registry, metrics = collectors()

    for index in range(400):
        metrics.observe_request(
            method="GET",
            route=f"/generated/{index}",
            status_code=200,
            duration_seconds=0.01,
        )

    series = {
        sample.labels["route"]
        for metric in registry.collect()
        for sample in metric.samples
        if "route" in sample.labels
    }

    assert len(series) <= metrics.max_routes + 1
