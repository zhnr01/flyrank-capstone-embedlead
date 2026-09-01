from app.core.rate_limit import RateLimiter


class FakeClock:
    def __init__(self) -> None:
        self.now = 1_000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def test_limiter_allows_up_to_the_limit_then_refuses() -> None:
    clock = FakeClock()
    limiter = RateLimiter(limit=3, window_seconds=60, clock=clock)

    assert [limiter.acquire("ip:1").allowed for _ in range(3)] == [True, True, True]

    decision = limiter.acquire("ip:1")
    assert decision.allowed is False
    assert decision.retry_after_seconds == 60


def test_limiter_frees_a_slot_after_the_window() -> None:
    clock = FakeClock()
    limiter = RateLimiter(limit=2, window_seconds=60, clock=clock)
    limiter.acquire("ip:1")
    limiter.acquire("ip:1")
    assert limiter.acquire("ip:1").allowed is False

    clock.advance(61)

    assert limiter.acquire("ip:1").allowed is True


def test_limiter_reports_shrinking_retry_after_as_window_elapses() -> None:
    clock = FakeClock()
    limiter = RateLimiter(limit=1, window_seconds=60, clock=clock)
    limiter.acquire("ip:1")

    clock.advance(20)

    assert limiter.acquire("ip:1").retry_after_seconds == 40


def test_limiter_keys_are_independent() -> None:
    clock = FakeClock()
    limiter = RateLimiter(limit=1, window_seconds=60, clock=clock)
    limiter.acquire("ip:1")

    assert limiter.acquire("ip:1").allowed is False
    assert limiter.acquire("ip:2").allowed is True
    assert limiter.acquire("widget:1").allowed is True


def test_limiter_prunes_expired_keys_instead_of_growing() -> None:
    clock = FakeClock()
    limiter = RateLimiter(limit=5, window_seconds=60, clock=clock)
    for index in range(50):
        limiter.acquire(f"ip:{index}")
    assert limiter.tracked_keys == 50

    clock.advance(61)
    limiter.acquire("ip:fresh")

    assert limiter.tracked_keys == 1


def test_limiter_evicts_when_key_cap_is_reached() -> None:
    clock = FakeClock()
    limiter = RateLimiter(limit=5, window_seconds=60, clock=clock, max_keys=10)

    for index in range(25):
        limiter.acquire(f"ip:{index}")

    assert limiter.tracked_keys <= 10
