import threading

import pytest
from clock import Clock

from app.limiter import RateLimiter


def make(capacity=3, window=60.0, max_keys=100):
    clock = Clock()
    return RateLimiter(capacity, window, max_keys, clock), clock


def test_burst_up_to_capacity_then_first_rejection_with_retry_after():
    limiter, clock = make(capacity=3, window=60)  # one token every 20 s
    assert [limiter.hit("k").allowed for _ in range(3)] == [True, True, True]
    denied = limiter.hit("k")
    assert not denied.allowed and denied.retry_after == 20 and denied.reason is None


def test_recovery_happens_exactly_when_a_token_has_refilled():
    limiter, clock = make(capacity=3, window=60)
    for _ in range(3):
        limiter.hit("k")
    clock.advance(19.9)
    assert not limiter.hit("k").allowed
    clock.advance(0.1)
    assert limiter.hit("k").allowed and not limiter.hit("k").allowed


def test_retry_after_is_rounded_up_to_whole_seconds_and_never_zero():
    limiter, clock = make(capacity=1, window=10)
    limiter.hit("k")
    clock.advance(9.2)
    assert limiter.hit("k").retry_after == 1  # 0.8 s left -> 1
    clock.advance(0.0)
    tiny, tclock = make(capacity=1, window=0.5)
    tiny.hit("k")
    assert tiny.hit("k").retry_after == 1


def test_rejected_requests_do_not_lengthen_the_wait():
    limiter, clock = make(capacity=2, window=60)
    limiter.hit("k"), limiter.hit("k")
    first = limiter.hit("k").retry_after
    for _ in range(50):
        assert limiter.hit("k").retry_after == first
    clock.advance(first)
    assert limiter.hit("k").allowed


def test_idle_time_never_banks_more_than_capacity():
    limiter, clock = make(capacity=3, window=60)
    limiter.hit("k")
    clock.advance(10_000)
    assert [limiter.hit("k").allowed for _ in range(4)] == [True, True, True, False]


def test_keys_are_independent():
    limiter, _ = make(capacity=1)
    assert limiter.hit("a").allowed and not limiter.hit("a").allowed
    assert limiter.hit("b").allowed


def test_no_window_boundary_double_burst():
    limiter, clock = make(capacity=4, window=60)
    for _ in range(4):
        limiter.hit("k")
    clock.advance(1)  # just after the "window" a fixed counter would have reset for 4 more
    assert sum(limiter.hit("k").allowed for _ in range(4)) == 0


def test_concurrent_hits_never_exceed_the_budget():
    limiter, _ = make(capacity=50, window=60)
    results, barrier = [], threading.Barrier(40)

    def worker():
        barrier.wait()
        results.extend(limiter.hit("shared").allowed for _ in range(10))

    threads = [threading.Thread(target=worker) for _ in range(40)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert len(results) == 400 and sum(results) == 50


def test_full_idle_buckets_are_evicted_to_make_room():
    limiter, clock = make(capacity=2, window=60, max_keys=3)
    for key in "abc":
        limiter.hit(key)
    assert limiter.size() == 3
    clock.advance(60)  # every bucket has fully refilled, i.e. is equivalent to absent
    assert limiter.hit("d").allowed
    assert limiter.size() <= 3


def test_at_capacity_new_keys_are_refused_and_exhausted_budgets_are_not_erased():
    limiter, clock = make(capacity=1, window=60, max_keys=3)
    for key in "abc":
        assert limiter.hit(key).allowed
    refused = limiter.hit("d")
    assert not refused.allowed and refused.reason == "capacity" and refused.retry_after >= 1
    for key in "abc":  # nothing was evicted: all three are still exhausted
        assert not limiter.hit(key).allowed
    assert limiter.size() == 3
    clock.advance(60)
    assert limiter.hit("d").allowed


def test_capacity_sweep_walks_the_table_at_most_once_per_second():
    class CountingDict(dict):
        scans = 0

        def items(self):
            CountingDict.scans += 1
            return super().items()

    limiter, clock = make(capacity=1, window=3600, max_keys=2)
    limiter.hit("a"), limiter.hit("b")
    limiter._buckets = CountingDict(limiter._buckets)
    for _ in range(100):
        assert not limiter.hit("new").allowed
    assert CountingDict.scans == 1
    clock.advance(1.0)
    assert not limiter.hit("new").allowed
    assert CountingDict.scans == 2


@pytest.mark.parametrize("args", [(0, 60, 10), (1, 0, 10), (1, 60, 0)])
def test_invalid_construction_is_rejected(args):
    with pytest.raises(ValueError):
        RateLimiter(*args)


def test_an_empty_limiter_is_truthy():
    limiter, _ = make()
    assert limiter.size() == 0 and bool(limiter)  # `if limiter:` must not mean "has keys"
