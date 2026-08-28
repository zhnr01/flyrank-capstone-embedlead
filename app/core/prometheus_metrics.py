from prometheus_client import CollectorRegistry, Counter, Histogram, generate_latest

from app.core.config import settings

LATENCY_BUCKETS_SECONDS = (0.005, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0)
STATUS_CLASSES = ("1xx", "2xx", "3xx", "4xx", "5xx")
OVERFLOW_LABEL = "other"
METRIC_PREFIX = "embedlead"


def status_class(status_code: int) -> str:
    bucket = f"{status_code // 100}xx"
    return bucket if bucket in STATUS_CLASSES else OVERFLOW_LABEL


class PrometheusMetrics:
    def __init__(self, registry: CollectorRegistry, *, max_routes: int) -> None:
        if max_routes < 1:
            raise ValueError("max_routes must be at least 1")
        self.max_routes = max_routes
        self._routes: set[str] = set()
        self._requests = Counter(
            f"{METRIC_PREFIX}_requests",
            "HTTP requests by method, route template and status class.",
            labelnames=("method", "route", "status_class"),
            registry=registry,
        )
        self._latency = Histogram(
            f"{METRIC_PREFIX}_request_duration_seconds",
            "HTTP request duration in seconds by method and route template.",
            labelnames=("method", "route"),
            buckets=LATENCY_BUCKETS_SECONDS,
            registry=registry,
        )
        self._events = Counter(
            f"{METRIC_PREFIX}_events",
            "Domain events by name and outcome.",
            labelnames=("name", "outcome"),
            registry=registry,
        )

    def _bounded_route(self, route: str) -> str:
        if route in self._routes:
            return route
        if len(self._routes) >= self.max_routes:
            return OVERFLOW_LABEL
        self._routes.add(route)
        return route

    def observe_request(
        self,
        *,
        method: str,
        route: str,
        status_code: int,
        duration_seconds: float,
    ) -> None:
        bounded = self._bounded_route(route)
        self._requests.labels(
            method=method, route=bounded, status_class=status_class(status_code)
        ).inc()
        self._latency.labels(method=method, route=bounded).observe(duration_seconds)

    def increment(self, name: str, outcome: str) -> None:
        self._events.labels(name=name, outcome=outcome).inc()


def build_collectors(
    registry: CollectorRegistry, *, max_routes: int | None = None
) -> PrometheusMetrics:
    limit = max_routes if max_routes is not None else settings.metrics_max_routes
    return PrometheusMetrics(registry, max_routes=limit)


def render_exposition(registry: CollectorRegistry) -> str:
    return generate_latest(registry).decode("utf-8")
