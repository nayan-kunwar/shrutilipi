"""Per-IP rate limiting for the transcript endpoint (v1: in-memory token bucket).

Design notes worth keeping in mind while reading this:

- Tokens are consumed on cache MISS only (see main.py). Cached hits cost no
  upstream quota, so they cost no tokens either. The limiter therefore guards
  the 100 req/month free-tier budget directly, not raw HTTP traffic.
- The client key is the leftmost X-Forwarded-For entry because Render
  terminates TLS and proxies: request.client.host would be Render's internal
  IP and the whole world would share one bucket. XFF is client-spoofable, but
  for a free tool that is an acceptable trade (a spoofed key still gets
  *some* bucket, and rotating keys to dodge the limiter costs the attacker
  more requests, not fewer).
- Buckets are process-local and die on restart (fail-open briefly after
  deploys). Stale buckets are pruned on every consume, so unlike the
  transcript cache this structure cannot grow without bound.
- threading.Lock guards mutation because the FastAPI handlers are plain `def`
  and therefore run in a thread pool.

Env (all optional, all with safe fallbacks):
  RATE_LIMIT_ENABLED         default "true"  ("0"/"false"/"no"/"off" disable)
  RATE_LIMIT_REQUESTS        default "20"    (bucket capacity per window)
  RATE_LIMIT_WINDOW_SECONDS  default "600"   (refill window; 20 per 10 min)
"""

import logging
import os
import threading
import time
from typing import Callable, Optional

from .youtube import env_truthy

logger = logging.getLogger("shrutilipi")

DEFAULT_REQUESTS = 20
DEFAULT_WINDOW_SECONDS = 600


def _env_int(name: str, default: int) -> int:
    """Parse a positive-int env var; any garbage falls back to default."""
    try:
        value = int((os.getenv(name, "") or "").strip())
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


def client_key(x_forwarded_for: Optional[str], client_host: Optional[str]) -> str:
    """Best-effort client identity. Never returns an empty string.

    Leftmost XFF entry wins (original client behind the Render proxy);
    falls back to the direct peer address for local dev; "unknown" only
    when neither exists, so every request still lands in *some* bucket.
    """
    if x_forwarded_for:
        first = x_forwarded_for.split(",")[0].strip()
        if first:
            return first
    if client_host:
        return client_host
    return "unknown"


class RateLimiter:
    """Token bucket keyed by client identity.

    `clock` is injectable (defaults to time.monotonic) so tests can travel
    through refill windows without sleeping.
    """

    def __init__(
        self,
        capacity: int,
        window_seconds: int,
        clock: Callable[[], float] = time.monotonic,
    ):
        self._capacity = max(1, capacity)
        self._window = max(1, window_seconds)
        self._clock = clock
        self._buckets: dict[str, list] = {}  # key -> [tokens: float, last_seen: float]
        self._lock = threading.Lock()

    @property
    def capacity(self) -> int:
        return self._capacity

    @property
    def window_seconds(self) -> int:
        return self._window

    def consume(self, key: str) -> Optional[float]:
        """Take one token for `key`.

        Returns None when allowed, otherwise seconds until at least one
        token has refilled (suitable for a Retry-After header).
        """
        now = self._clock()
        with self._lock:
            # Prune buckets idle for a full window: bounds memory and keeps
            # the steady-state size proportional to active clients, not
            # everyone who ever connected.
            stale = [k for k, (_, seen) in self._buckets.items() if now - seen >= self._window]
            for k in stale:
                del self._buckets[k]

            tokens, last_seen = self._buckets.get(key, (float(self._capacity), now))
            # Refill proportionally to elapsed time, capped at capacity.
            tokens = min(float(self._capacity), tokens + (now - last_seen) * self._capacity / self._window)
            if tokens >= 1.0:
                self._buckets[key] = [tokens - 1.0, now]
                return None
            retry_after = (1.0 - tokens) * self._window / self._capacity
            self._buckets[key] = [tokens, now]
            return retry_after


def build_limiter() -> Optional[RateLimiter]:
    """Factory honoring env. Returns None when disabled (callers skip)."""
    if not env_truthy(os.getenv("RATE_LIMIT_ENABLED"), True):
        logger.info("rate limiting disabled (RATE_LIMIT_ENABLED=%s)", os.getenv("RATE_LIMIT_ENABLED"))
        return None
    limiter = RateLimiter(
        capacity=_env_int("RATE_LIMIT_REQUESTS", DEFAULT_REQUESTS),
        window_seconds=_env_int("RATE_LIMIT_WINDOW_SECONDS", DEFAULT_WINDOW_SECONDS),
    )
    logger.info(
        "rate limiting enabled: %d requests per %ds per client",
        limiter.capacity,
        limiter.window_seconds,
    )
    return limiter
