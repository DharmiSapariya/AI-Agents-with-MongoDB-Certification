"""In-process token-bucket rate limiter.

Each key owns a bucket holding up to `capacity` tokens that refills continuously at
capacity/window_s tokens per second; a request takes one token. So `capacity` is the largest
burst and the sustained rate is capacity per window (no window-boundary double burst, unlike
a fixed window, and O(1) memory per key, unlike a sliding log). A rejected request takes
nothing, so hammering a limited route does not lengthen the wait.

A bucket that has fully refilled behaves exactly like a missing one, so only those are ever
evicted. At the key cap with nothing evictable, new keys are refused (fail closed) instead of
erasing an exhausted budget. State is per process: it resets on restart and is not shared
between workers or replicas.
"""
import math
import threading
import time
from dataclasses import dataclass
from typing import Callable

SWEEP_INTERVAL_S = 1.0  # at most one full scan per second when the table is full


@dataclass(frozen=True)
class Decision:
    allowed: bool
    retry_after: int = 0  # whole seconds, rounded up, at least 1 when rejected
    reason: str | None = None  # "capacity" when refused because the key table is full


class RateLimiter:
    def __init__(self, capacity: int, window_s: float, max_keys: int,
                 clock: Callable[[], float] = time.monotonic):
        if capacity < 1 or window_s <= 0 or max_keys < 1:
            raise ValueError("capacity, window_s and max_keys must be positive")
        self.capacity = capacity
        self.window_s = window_s
        self.max_keys = max_keys
        self._rate = capacity / window_s
        self._clock = clock
        self._lock = threading.Lock()
        self._buckets: dict[str, tuple[float, float]] = {}  # key -> (tokens, timestamp)
        self._last_sweep = float("-inf")
        self._next_free = 0.0  # earliest time a full-table sweep could free a slot

    def size(self) -> int:
        """Number of tracked keys (not __len__: an empty limiter must stay truthy)."""
        return len(self._buckets)

    def hit(self, key: str) -> Decision:
        """Atomically refill, check and consume one token for `key`."""
        now = self._clock()
        with self._lock:
            entry = self._buckets.get(key)
            if entry is None:
                if len(self._buckets) >= self.max_keys and not self._make_room(now):
                    return Decision(False, max(1, math.ceil(self._next_free - now)), "capacity")
                tokens = float(self.capacity)
            else:
                tokens = min(float(self.capacity), entry[0] + (now - entry[1]) * self._rate)
            if tokens >= 1:
                self._buckets[key] = (tokens - 1, now)
                return Decision(True)
            self._buckets[key] = (tokens, now)  # keep refill accounting current; consume nothing
            return Decision(False, max(1, math.ceil((1 - tokens) / self._rate)))

    def _make_room(self, now: float) -> bool:
        """Drop buckets that have fully refilled. Called with the lock held."""
        if now - self._last_sweep < SWEEP_INTERVAL_S:
            return len(self._buckets) < self.max_keys
        self._last_sweep = now
        soonest = float("inf")
        for key, (tokens, stamp) in list(self._buckets.items()):
            refilled = tokens + (now - stamp) * self._rate
            if refilled >= self.capacity:
                del self._buckets[key]
            else:
                soonest = min(soonest, now + (self.capacity - refilled) / self._rate)
        self._next_free = soonest if soonest != float("inf") else now + 1
        return len(self._buckets) < self.max_keys
