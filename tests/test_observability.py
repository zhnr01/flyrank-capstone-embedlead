import json
import logging
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
    MINIMUM_MAX_SERIES,
    OVERFLOW_LABEL,
    RESERVED_OVERFLOW_SERIES,
    MetricsRegistry,
    MetricsSnapshot,
    registry,
    status_class,
)
from app.main import app

client = TestClient(app)
METRICS_URL = "/api/v1/system/metrics"
LIVE_URL = "/api/v1/system/health/live"
LIVE_ROUTE = "/api/v1/system/health/live"
BUNDLE_ROUTE = "/api/v1/public/widgets/bundle/{version}/widget.js"


@pytest.fixture(autouse=True)
def clean_registry() -> None:
    registry.reset()


@pytest.fixture
def metrics_token(monkeypatch: pytest.MonkeyPatch) -> str:
    token = "operator-token-value"
    monkeypatch.setattr(settings, "metrics_token", token)
    return token


def read_metrics(token: str) -> MetricsSnapshot:
    response = client.get(METRICS_URL, headers={METRICS_TOKEN_HEADER: token})
    assert response.status_code == 200
    payload: MetricsSnapshot = response.json()
    return payload


def routes_in(snapshot: MetricsSnapshot) -> set[str]:
    return {row["route"] for row in snapshot["requests"]}


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

    snapshot = read_metrics(metrics_token)

    assert LIVE_ROUTE in routes_in(snapshot)
    for request_row in snapshot["requests"]:
        assert request_row["status_class"] in {"1xx", "2xx", "3xx", "4xx", "5xx"}
    for latency_row in snapshot["latency"]:
        p50 = latency_row["p50_seconds"]
        p95 = latency_row["p95_seconds"]
        p99 = latency_row["p99_seconds"]
        assert p50 <= p95 <= p99
        buckets = latency_row["buckets"]
        assert sum(bucket["count"] for bucket in buckets) == latency_row["count"]


def test_route_labels_use_templates_not_raw_path_values(metrics_token: str) -> None:
    client.get("/api/v1/public/widgets/bundle/v42/widget.js")

    snapshot = read_metrics(metrics_token)
    routes = routes_in(snapshot)

    assert BUNDLE_ROUTE in routes
    assert not any("v42" in route for route in routes)


def test_unmatched_paths_collapse_to_a_single_series(metrics_token: str) -> None:
    for suffix in range(5):
        client.get(f"/api/v1/does-not-exist-{suffix}")

    snapshot = read_metrics(metrics_token)
    unmatched = [
        row for row in snapshot["requests"] if row["route"] == UNMATCHED_ROUTE
    ]

    assert len(unmatched) == 1
    assert unmatched[0]["count"] == 5
    assert unmatched[0]["status_class"] == "4xx"


def test_failed_dependency_is_recorded_as_a_server_error_not_lost() -> None:
    local = MetricsRegistry(max_series=64)

    local.observe_request(
        method="GET",
        route="/api/v1/public/widgets/{widget_id}/config",
        status_code=500,
        duration_seconds=2.0,
    )
    snapshot = local.snapshot()

    assert snapshot["requests"] == [
        {
            "method": "GET",
            "route": "/api/v1/public/widgets/{widget_id}/config",
            "status_class": "5xx",
            "count": 1,
        }
    ]


def test_series_cardinality_is_capped_and_overflow_is_visible() -> None:
    local = MetricsRegistry(max_series=MINIMUM_MAX_SERIES)

    for index in range(50):
        local.observe_request(
            method="GET",
            route=f"/synthetic/{index}",
            status_code=200,
            duration_seconds=0.01,
        )

    snapshot = local.snapshot()
    cardinality = snapshot["cardinality"]

    assert cardinality["series"] <= MINIMUM_MAX_SERIES
    assert cardinality["overflowed"] is True
    assert any(row["route"] == OVERFLOW_LABEL for row in snapshot["requests"])
    observed = sum(row["count"] for row in snapshot["requests"])
    assert observed == 50


def test_cap_holds_across_every_status_class_and_metric_kind() -> None:
    local = MetricsRegistry(max_series=MINIMUM_MAX_SERIES)

    for index in range(200):
        local.observe_request(
            method="GET",
            route=f"/synthetic/{index}",
            status_code=200 + index % 400,
            duration_seconds=0.01,
        )
        local.increment(f"event-{index}", f"outcome-{index}")

    assert local.series_count <= MINIMUM_MAX_SERIES
    assert local.overflowed is True


def test_event_counter_labels_are_also_capped() -> None:
    local = MetricsRegistry(max_series=MINIMUM_MAX_SERIES)

    for index in range(20):
        local.increment("submission_rate_limited", f"scope-{index}")

    snapshot = local.snapshot()

    assert local.overflowed is True
    assert sum(row["count"] for row in snapshot["events"]) == 20
    assert any(row["outcome"] == OVERFLOW_LABEL for row in snapshot["events"])


def test_empty_registry_reports_zero_not_an_error() -> None:
    local = MetricsRegistry(max_series=MINIMUM_MAX_SERIES)

    snapshot = local.snapshot()

    assert snapshot["requests"] == []
    assert snapshot["latency"] == []
    assert snapshot["events"] == []
    assert snapshot["cardinality"] == {
        "series": 0,
        "max_series": MINIMUM_MAX_SERIES,
        "overflowed": False,
    }


def test_rejects_a_series_cap_too_small_to_hold_its_own_overflow_rows() -> None:
    with pytest.raises(ValueError, match="max_series"):
        MetricsRegistry(max_series=RESERVED_OVERFLOW_SERIES)


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
