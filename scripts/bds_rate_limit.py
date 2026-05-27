"""Pacing and retries for BDS prefetch (metering rate limits + transient 502s)."""

from __future__ import annotations

import asyncio
import os
import time
from typing import Any

from bds_agent.client import BdsClientError, fetch

DEFAULT_RPM = int(os.environ.get("BDS_RATE_LIMIT_RPM", "200"))
MAX_RETRIES = int(os.environ.get("BDS_FETCH_MAX_RETRIES", "4"))


class BdsRateLimiter:
    """Global min-interval limiter: rpm requests per 60s wall clock."""

    def __init__(self, rpm: int) -> None:
        self._interval = 60.0 / max(rpm, 1)
        self._lock = asyncio.Lock()
        self._next_time = 0.0

    async def acquire(self) -> None:
        async with self._lock:
            now = time.monotonic()
            if now < self._next_time:
                await asyncio.sleep(self._next_time - now)
            self._next_time = time.monotonic() + self._interval


def _retryable(exc: BdsClientError) -> bool:
    msg = str(exc).lower()
    if "429" in msg or "rate limit" in msg:
        return True
    for code in ("502", "503", "504"):
        if code in msg:
            return True
    return "timeout" in msg or "temporarily unavailable" in msg


async def fetch_throttled(
    limiter: BdsRateLimiter,
    base_url: str,
    endpoint: str,
    api_key: str,
    **params: Any,
):
    last_exc: BdsClientError | None = None
    for attempt in range(MAX_RETRIES):
        await limiter.acquire()
        try:
            return await fetch(base_url, endpoint, api_key, **params)
        except BdsClientError as exc:
            last_exc = exc
            if not _retryable(exc) or attempt + 1 >= MAX_RETRIES:
                raise
            wait = min(30.0, 2.0**attempt)
            print(
                f"WARN: retry {attempt + 1}/{MAX_RETRIES - 1} in {wait:.1f}s "
                f"for {endpoint}: {exc}",
            )
            await asyncio.sleep(wait)
    if last_exc is not None:
        raise last_exc
    raise RuntimeError("fetch_throttled: unreachable")
