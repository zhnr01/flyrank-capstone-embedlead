import threading
from bisect import bisect_left
from dataclasses import dataclass, field
from typing import TypedDict

from app.core.config import settings

LATENCY_BUCKETS_SECONDS = (0.005, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0)
STATUS_CLASSES = ("1xx", "2xx", "3xx", "4xx", "5xx")
OVERFLOW_LABEL = "other"
RESERVED_OVERFLOW_SERIES = len(STATUS_CLASSES) + 2
MINIMUM_MAX_SERIES = RESERVED_OVERFLOW_SERIES + 1


class RequestSeries(TypedDict):
    method: str
    route: str
    status_class: str
    count: int


class LatencyBucket(TypedDict):
    le: float
    count: int


class LatencySeries(TypedDict):
    method: str
    route: str
    count: int
    sum_seconds: float
    p50_seconds: float
    p95_seconds: float
    p99_seconds: float
    buckets: list[LatencyBucket]


class EventSeries(TypedDict):
    name: str
    outcome: str
    count: int


class Cardinality(TypedDict):
    series: int
    max_series: int
    overflowed: bool


class MetricsSnapshot(TypedDict):
    requests: list[RequestSeries]
    latency: list[LatencySeries]
    events: list[EventSeries]
    cardinality: Cardinality


def status_class(status_code: int) -> str:
    bucket = f"{status_code // 100}xx"
    return bucket if bucket in STATUS_CLASSES else OVERFLOW_LABEL


def bucket_upper_bound(index: int) -> float:
    if index < len(LATENCY_BUCKETS_SECONDS):
        return LATENCY_BUCKETS_SECONDS[index]
    return float("inf")


@dataclass
class Histogram:
    counts: list[int] = field(
        default_factory=lambda: [0] * (len(LATENCY_BUCKETS_SECONDS) + 1)
    )
    total: int = 0
    sum_seconds: float = 0.0

    def observe(self, seconds: float) -> None:
        self.counts[bisect_left(LATENCY_BUCKETS_SECONDS, seconds)] += 1
        self.total += 1
        self.sum_seconds += seconds

    def quantile(self, quantile: float) -> float:
        if self.total == 0:
            return 0.0
        target = quantile * self.total
        seen = 0
        for index, count in enumerate(self.counts):
            seen += count
            if seen >= target:
                return bucket_upper_bound(index)
        return float("inf")


class MetricsRegistry:
    def __init__(self, *, max_series: int = 512) -> None:
        if max_series < MINIMUM_MAX_SERIES:
            raise ValueError(f"max_series must be at least {MINIMUM_MAX_SERIES}")
        self._max_series = max_series
        self._label_budget = max_series - RESERVED_OVERFLOW_SERIES
        self._lock = threading.Lock()
        self._requests: dict[tuple[str, str, str], int] = {}
        self._latency: dict[tuple[str, str], Histogram] = {}
        self._counters: dict[tuple[str, str], int] = {}
        self._overflowed = False

    @property
    def series_count(self) -> int:
        with self._lock:
            return self._series_count()

    @property
    def overflowed(self) -> bool:
        with self._lock:
            return self._overflowed

    def _series_count(self) -> int:
        return len(self._requests) + len(self._latency) + len(self._counters)

    def _accepts_new_label(self) -> bool:
        if self._series_count() < self._label_budget:
            return True
        self._overflowed = True
        return False

    def observe_request(
        self,
        *,
        method: str,
        route: str,
        status_code: int,
        duration_seconds: float,
    ) -> None:
        klass = status_class(status_code)
        with self._lock:
            request_key = (method, route, klass)
            if request_key not in self._requests and not self._accepts_new_label():
                request_key = (OVERFLOW_LABEL, OVERFLOW_LABEL, klass)
            self._requests[request_key] = self._requests.get(request_key, 0) + 1

            latency_key = (method, route)
            if latency_key not in self._latency and not self._accepts_new_label():
                latency_key = (OVERFLOW_LABEL, OVERFLOW_LABEL)
            self._latency.setdefault(latency_key, Histogram()).observe(duration_seconds)

    def increment(self, name: str, outcome: str) -> None:
        with self._lock:
            key = (name, outcome)
            if key not in self._counters and not self._accepts_new_label():
                key = (OVERFLOW_LABEL, OVERFLOW_LABEL)
            self._counters[key] = self._counters.get(key, 0) + 1

    def snapshot(self) -> MetricsSnapshot:
        with self._lock:
            requests: list[RequestSeries] = [
                {
                    "method": method,
                    "route": route,
                    "status_class": klass,
                    "count": count,
                }
                for (method, route, klass), count in sorted(self._requests.items())
            ]
            latency: list[LatencySeries] = [
                {
                    "method": method,
                    "route": route,
                    "count": histogram.total,
                    "sum_seconds": round(histogram.sum_seconds, 4),
                    "p50_seconds": histogram.quantile(0.50),
                    "p95_seconds": histogram.quantile(0.95),
                    "p99_seconds": histogram.quantile(0.99),
                    "buckets": [
                        {"le": bucket_upper_bound(index), "count": count}
                        for index, count in enumerate(histogram.counts)
                    ],
                }
                for (method, route), histogram in sorted(self._latency.items())
            ]
            events: list[EventSeries] = [
                {"name": name, "outcome": outcome, "count": count}
                for (name, outcome), count in sorted(self._counters.items())
            ]
            cardinality: Cardinality = {
                "series": self._series_count(),
                "max_series": self._max_series,
                "overflowed": self._overflowed,
            }
        return {
            "requests": requests,
            "latency": latency,
            "events": events,
            "cardinality": cardinality,
        }

    def reset(self) -> None:
        with self._lock:
            self._requests.clear()
            self._latency.clear()
            self._counters.clear()
            self._overflowed = False


registry = MetricsRegistry(max_series=settings.metrics_max_series)


def observe_request(
    *,
    method: str,
    route: str,
    status_code: int,
    duration_seconds: float,
) -> None:
    registry.observe_request(
        method=method,
        route=route,
        status_code=status_code,
        duration_seconds=duration_seconds,
    )


def increment(name: str, outcome: str) -> None:
    registry.increment(name, outcome)
