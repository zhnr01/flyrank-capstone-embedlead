import fakeredis
import pytest

from app.core.rate_limit import RateLimitDecision, RateLimiter
from app.core.redis_rate_limit import RedisRateLimiter, ResilientRateLimiter

LIMIT = 3
WINDOW = 60


@pytest.fixture
def server() -> fakeredis.FakeServer:
    return fakeredis.FakeServer()


def client(server: fakeredis.FakeServer) -> fakeredis.FakeRedis:
    return fakeredis.FakeRedis(server=server, decode_responses=True)


def limiter(server: fakeredis.FakeServer) -> RedisRateLimiter:
    return RedisRateLimiter(
        redis_client=client(server),
        limit=LIMIT,
        window_seconds=WINDOW,
    )


def test_allows_up_to_the_limit_then_refuses(server: fakeredis.FakeServer) -> None:
    subject = limiter(server)

    for _ in range(LIMIT):
        assert subject.acquire("ip:1.2.3.4").allowed is True

    refused = subject.acquire("ip:1.2.3.4")
    assert refused.allowed is False
    assert refused.retry_after_seconds >= 1


def test_two_replicas_share_one_budget(server: fakeredis.FakeServer) -> None:
    replica_a = limiter(server)
    replica_b = limiter(server)

    assert replica_a.acquire("ip:9.9.9.9").allowed is True
    assert replica_b.acquire("ip:9.9.9.9").allowed is True
    assert replica_a.acquire("ip:9.9.9.9").allowed is True

    assert replica_b.acquire("ip:9.9.9.9").allowed is False


def test_distinct_keys_have_independent_budgets(server: fakeredis.FakeServer) -> None:
    subject = limiter(server)

    for _ in range(LIMIT):
        assert subject.acquire("ip:1.1.1.1").allowed is True

    assert subject.acquire("ip:1.1.1.1").allowed is False
    assert subject.acquire("ip:2.2.2.2").allowed is True


def test_a_refused_request_does_not_consume_a_slot(
    server: fakeredis.FakeServer,
) -> None:
    subject = limiter(server)
    for _ in range(LIMIT):
        subject.acquire("ip:3.3.3.3")

    first_refusal = subject.acquire("ip:3.3.3.3")
    second_refusal = subject.acquire("ip:3.3.3.3")

    assert first_refusal.allowed is False
    assert second_refusal.allowed is False
    assert second_refusal.retry_after_seconds <= first_refusal.retry_after_seconds


def test_the_key_carries_a_namespace_so_scopes_cannot_collide(
    server: fakeredis.FakeServer,
) -> None:
    subject = limiter(server)
    raw = client(server)

    subject.acquire("ip:4.4.4.4")

    assert any(key.startswith("ratelimit:") for key in raw.scan_iter("*"))


def test_keys_expire_so_redis_memory_stays_bounded(
    server: fakeredis.FakeServer,
) -> None:
    subject = limiter(server)
    raw = client(server)

    subject.acquire("ip:5.5.5.5")

    ttls = [raw.pttl(key) for key in raw.scan_iter("ratelimit:*")]
    assert ttls
    for ttl in ttls:
        assert 0 < ttl <= WINDOW * 1000


def test_reset_clears_shared_state(server: fakeredis.FakeServer) -> None:
    subject = limiter(server)
    for _ in range(LIMIT):
        subject.acquire("ip:6.6.6.6")
    assert subject.acquire("ip:6.6.6.6").allowed is False

    subject.reset()

    assert subject.acquire("ip:6.6.6.6").allowed is True


def test_a_bad_limit_is_refused_at_construction(server: fakeredis.FakeServer) -> None:
    for bad in (0, -1):
        with pytest.raises(ValueError, match="limit"):
            RedisRateLimiter(
                redis_client=client(server), limit=bad, window_seconds=WINDOW
            )


def test_a_bad_window_is_refused_at_construction(server: fakeredis.FakeServer) -> None:
    for bad in (0, -5):
        with pytest.raises(ValueError, match="window"):
            RedisRateLimiter(
                redis_client=client(server), limit=LIMIT, window_seconds=bad
            )


class ExplodingLimiter:
    def __init__(self) -> None:
        self.calls = 0

    def acquire(self, key: str) -> RateLimitDecision:
        self.calls += 1
        raise ConnectionError("redis is down")

    def reset(self) -> None:
        raise ConnectionError("redis is down")

    def close(self) -> None:
        raise ConnectionError("redis is down")


def test_a_redis_outage_fails_open_onto_the_in_process_limiter() -> None:
    primary = ExplodingLimiter()
    fallback = RateLimiter(limit=LIMIT, window_seconds=WINDOW)
    subject = ResilientRateLimiter(primary=primary, fallback=fallback)

    for _ in range(LIMIT):
        assert subject.acquire("ip:7.7.7.7").allowed is True

    assert subject.acquire("ip:7.7.7.7").allowed is False
    assert primary.calls > 0


def test_the_fallback_still_enforces_a_limit_rather_than_allowing_everything() -> None:
    fallback = RateLimiter(limit=1, window_seconds=WINDOW)
    subject = ResilientRateLimiter(primary=ExplodingLimiter(), fallback=fallback)

    assert subject.acquire("ip:8.8.8.8").allowed is True
    assert subject.acquire("ip:8.8.8.8").allowed is False


def test_reset_is_survivable_when_redis_is_unreachable() -> None:
    subject = ResilientRateLimiter(
        primary=ExplodingLimiter(),
        fallback=RateLimiter(limit=LIMIT, window_seconds=WINDOW),
    )

    subject.reset()

    assert subject.acquire("ip:1.0.0.1").allowed is True
