import json
import logging
import re
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.api.metrics_dependencies import METRICS_TOKEN_HEADER
from app.api.request_context import (
    REQUEST_ID_HEADER,
    UNMATCHED_ROUTE,
    safe_request_id,
)
from app.core.config import settings
from app.core.logging_config import JsonFormatter, RequestIdFilter, redact
from app.core.metrics import (
    OVERFLOW_LABEL,
    render_exposition,
    reset_metrics,
    status_class,
)
from app.core.prometheus_metrics import build_collectors
from app.main import app

client = TestClient(app)
METRICS_URL = "/api/v1/system/metrics"
LIVE_URL = "/api/v1/system/health/live"
LIVE_ROUTE = "/api/v1/system/health/live"
BUNDLE_ROUTE = "/api/v1/public/widgets/bundle/{version}/widget.js"


@pytest.fixture(autouse=True)
def clean_registry() -> None:
    reset_metrics()


@pytest.fixture
def metrics_token(monkeypatch: pytest.MonkeyPatch) -> str:
    token = "operator-token-value"
    monkeypatch.setattr(settings, "metrics_token", token)
    return token


def read_metrics(token: str) -> str:
    response = client.get(METRICS_URL, headers={METRICS_TOKEN_HEADER: token})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    body: str = response.text
    return body


def sample_labels(text: str, metric: str) -> list[dict[str, str]]:
    rows = []
    for line in text.splitlines():
        if line.startswith("#") or not line.startswith(f"{metric}{{"):
            continue
        inner = line[line.index("{") + 1 : line.rindex("}")]
        pairs = dict(
            part.split("=", 1) for part in re.findall(r'[a-z_]+="[^"]*"', inner)
        )
        rows.append({key: value.strip('"') for key, value in pairs.items()})
    return rows


def sample_value(text: str, metric: str, **labels: str) -> float:
    for line in text.splitlines():
        if line.startswith("#") or not line.startswith(f"{metric}{{"):
            continue
        if all(f'{key}="{value}"' in line for key, value in labels.items()):
            return float(line.rsplit(" ", 1)[1])
    raise AssertionError(f"no sample for {metric} {labels}")


def routes_in(text: str) -> set[str]:
    return {row["route"] for row in sample_labels(text, "embedlead_requests_total")}


def format_record(
    message: str,
    fields: dict[str, object] | None = None,
) -> dict[str, Any]:
    record = logging.LogRecord(
        name="app.test",
        level=logging.WARNING,
        pathname=__file__,
        lineno=1,
        msg=message,
        args=(),
        exc_info=None,
    )
    if fields is not None:
        record.fields = fields
    RequestIdFilter().filter(record)
    payload: dict[str, Any] = json.loads(JsonFormatter().format(record))
    return payload


def test_metrics_endpoint_is_absent_when_no_token_is_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "metrics_token", "")

    response = client.get(METRICS_URL)

    assert response.status_code == 404
    assert "requests" not in response.text


def test_metrics_endpoint_rejects_a_missing_token(metrics_token: str) -> None:
    response = client.get(METRICS_URL)

    assert response.status_code == 401
    assert "requests" not in response.text


def test_metrics_endpoint_rejects_a_wrong_token(metrics_token: str) -> None:
    response = client.get(
        METRICS_URL,
        headers={METRICS_TOKEN_HEADER: metrics_token + "x"},
    )

    assert response.status_code == 401


def test_metrics_endpoint_never_leaks_the_expected_token(metrics_token: str) -> None:
    response = client.get(METRICS_URL, headers={METRICS_TOKEN_HEADER: "wrong"})

    assert metrics_token not in response.text


def test_metrics_reports_red_signals_with_bounded_status_labels(
    metrics_token: str,
) -> None:
    client.get(LIVE_URL)

    text = read_metrics(metrics_token)

    assert LIVE_ROUTE in routes_in(text)
    for row in sample_labels(text, "embedlead_requests_total"):
        assert row["status_class"] in {"1xx", "2xx", "3xx", "4xx", "5xx"}


def test_latency_histogram_exposes_cumulative_buckets(metrics_token: str) -> None:
    client.get(LIVE_URL)

    text = read_metrics(metrics_token)
    infinity = sample_value(
        text,
        "embedlead_request_duration_seconds_bucket",
        method="GET",
        route=LIVE_ROUTE,
        le="+Inf",
    )
    count = sample_value(
        text,
        "embedlead_request_duration_seconds_count",
        method="GET",
        route=LIVE_ROUTE,
    )

    assert infinity == count


def test_exposition_declares_help_and_type_for_every_metric(
    metrics_token: str,
) -> None:
    client.get(LIVE_URL)

    text = read_metrics(metrics_token)

    for metric in (
        "embedlead_requests",
        "embedlead_request_duration_seconds",
        "embedlead_events",
    ):
        assert f"# HELP {metric}" in text
        assert f"# TYPE {metric}" in text


def test_route_labels_use_templates_not_raw_path_values(metrics_token: str) -> None:
    client.get("/api/v1/public/widgets/bundle/v42/widget.js")

    routes = routes_in(read_metrics(metrics_token))

    assert BUNDLE_ROUTE in routes
    assert not any("v42" in route for route in routes)


def test_unmatched_paths_collapse_to_a_single_series(metrics_token: str) -> None:
    for suffix in range(5):
        client.get(f"/api/v1/does-not-exist-{suffix}")

    text = read_metrics(metrics_token)
    unmatched = [
        row
        for row in sample_labels(text, "embedlead_requests_total")
        if row["route"] == UNMATCHED_ROUTE
    ]

    assert len(unmatched) == 1
    assert unmatched[0]["status_class"] == "4xx"
    assert (
        sample_value(
            text,
            "embedlead_requests_total",
            method="GET",
            route=UNMATCHED_ROUTE,
            status_class="4xx",
        )
        == 5
    )


def test_failed_dependency_is_recorded_as_a_server_error_not_lost() -> None:
    from prometheus_client import CollectorRegistry

    registry = CollectorRegistry()
    local = build_collectors(registry, max_routes=64)

    local.observe_request(
        method="GET",
        route="/api/v1/system/health/ready",
        status_code=503,
        duration_seconds=0.01,
    )

    assert (
        registry.get_sample_value(
            "embedlead_requests_total",
            {
                "method": "GET",
                "route": "/api/v1/system/health/ready",
                "status_class": "5xx",
            },
        )
        == 1
    )


def test_route_cardinality_is_capped_and_overflow_is_visible() -> None:
    from prometheus_client import CollectorRegistry

    registry = CollectorRegistry()
    local = build_collectors(registry, max_routes=3)

    for index in range(40):
        local.observe_request(
            method="GET",
            route=f"/generated/{index}",
            status_code=200,
            duration_seconds=0.01,
        )

    routes = {
        sample.labels["route"]
        for metric in registry.collect()
        for sample in metric.samples
        if "route" in sample.labels
    }

    assert len(routes) <= local.max_routes + 1
    assert OVERFLOW_LABEL in routes


def test_every_observation_is_counted_even_when_the_route_label_overflows() -> None:
    from prometheus_client import CollectorRegistry

    registry = CollectorRegistry()
    local = build_collectors(registry, max_routes=2)

    for index in range(20):
        local.observe_request(
            method="GET",
            route=f"/generated/{index}",
            status_code=200,
            duration_seconds=0.01,
        )

    total = sum(
        sample.value
        for metric in registry.collect()
        if metric.name == "embedlead_requests"
        for sample in metric.samples
        if sample.name.endswith("_total")
    )

    assert total == 20


def test_a_registry_with_no_observations_still_renders() -> None:
    from prometheus_client import CollectorRegistry

    registry = CollectorRegistry()
    build_collectors(registry, max_routes=8)

    text = render_exposition(registry)

    assert "# TYPE embedlead_requests" in text


def test_rejects_a_route_cap_below_one() -> None:
    from prometheus_client import CollectorRegistry

    with pytest.raises(ValueError, match="max_routes"):
        build_collectors(CollectorRegistry(), max_routes=0)


def test_unknown_status_code_does_not_create_an_unbounded_label() -> None:
    assert status_class(999) == OVERFLOW_LABEL
    assert status_class(42) == OVERFLOW_LABEL


def test_status_class_buckets_are_bounded() -> None:
    assert status_class(200) == "2xx"
    assert status_class(304) == "3xx"
    assert status_class(422) == "4xx"
    assert status_class(503) == "5xx"


def test_response_carries_a_request_id() -> None:
    response = client.get(LIVE_URL)

    assert response.status_code == 200
    assert response.headers[REQUEST_ID_HEADER]


def test_supplied_request_id_is_echoed_for_correlation() -> None:
    response = client.get(
        LIVE_URL,
        headers={REQUEST_ID_HEADER: "trace-abc-123"},
    )

    assert response.headers[REQUEST_ID_HEADER] == "trace-abc-123"


@pytest.mark.parametrize(
    "hostile",
    [
        "z" * 500,
        "",
        "   ",
        "trace\nX-Injected: yes",
        "trace with spaces",
        "<script>alert(1)</script>",
        "trace;drop",
    ],
)
def test_hostile_request_ids_are_replaced_not_reflected(hostile: str) -> None:
    generated = safe_request_id(hostile)

    assert generated != hostile
    assert len(generated) == 36
    assert "\n" not in generated
    assert " " not in generated


def test_request_id_header_cannot_be_used_for_header_injection() -> None:
    response = client.get(LIVE_URL, headers={REQUEST_ID_HEADER: "a" * 200})

    echoed = response.headers[REQUEST_ID_HEADER]
    assert echoed != "a" * 200
    assert "x-injected" not in {name.lower() for name in response.headers}


def test_log_output_is_structured_json_with_stable_event_name() -> None:
    payload = format_record("submission_stored", {"widget_id": 7})

    assert payload["event"] == "submission_stored"
    assert payload["level"] == "WARNING"
    assert payload["logger"] == "app.test"
    assert payload["widget_id"] == 7
    assert "request_id" in payload
    assert "timestamp" in payload


def test_sensitive_fields_are_redacted() -> None:
    payload = format_record(
        "login_attempt",
        {
            "password": "hunter2",
            "webhook_secret": "top-secret",
            "authorization": "Bearer abc.def",
            "email": "person@example.com",
            "widget_id": 3,
        },
    )

    assert payload["password"] == "[redacted]"
    assert payload["webhook_secret"] == "[redacted]"
    assert payload["authorization"] == "[redacted]"
    assert payload["email"] == "[redacted]"
    assert payload["widget_id"] == 3
    serialised = json.dumps(payload)
    assert "hunter2" not in serialised
    assert "top-secret" not in serialised
    assert "person@example.com" not in serialised


def test_redact_is_case_insensitive_and_substring_aware() -> None:
    cleaned = redact({"API_KEY": "x" * 40, "Session-Token": "y" * 40, "count": 2})

    assert cleaned["API_KEY"] == "[redacted]"
    assert cleaned["Session-Token"] == "[redacted]"
    assert cleaned["count"] == 2


def test_metrics_token_is_never_written_to_a_log_line() -> None:
    payload = format_record("metrics_access", {"metrics_token": "operator-secret"})

    assert payload["metrics_token"] == "[redacted]"
    assert "operator-secret" not in json.dumps(payload)
