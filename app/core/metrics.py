from prometheus_client import CollectorRegistry

from app.core.config import settings
from app.core.prometheus_metrics import (
    LATENCY_BUCKETS_SECONDS,
    OVERFLOW_LABEL,
    STATUS_CLASSES,
    PrometheusMetrics,
    build_collectors,
    render_exposition,
    status_class,
)

__all__ = [
    "LATENCY_BUCKETS_SECONDS",
    "OVERFLOW_LABEL",
    "STATUS_CLASSES",
    "PrometheusMetrics",
    "increment",
    "observe_request",
    "registry",
    "render_exposition",
    "reset_metrics",
    "status_class",
]

registry = CollectorRegistry()
collectors = build_collectors(registry, max_routes=settings.metrics_max_routes)


def observe_request(
    *,
    method: str,
    route: str,
    status_code: int,
    duration_seconds: float,
) -> None:
    collectors.observe_request(
        method=method,
        route=route,
        status_code=status_code,
        duration_seconds=duration_seconds,
    )


def increment(name: str, outcome: str) -> None:
    collectors.increment(name, outcome)


def reset_metrics() -> None:
    global registry, collectors
    registry = CollectorRegistry()
    collectors = build_collectors(registry, max_routes=settings.metrics_max_routes)


def exposition() -> str:
    return render_exposition(registry)
