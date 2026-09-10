"""Minimal in-process sliding-window rate limiter.

Deliberately dependency-free. This is correct for a single-process deployment
(the expected shape for this app). If you scale to multiple workers/instances,
swap the backing dict for Redis — the call sites do not change.
"""
from __future__ import annotations

import threading
import time
from collections import deque

from fastapi import HTTPException, Request, status

# key -> (window_seconds, timestamps). The window is stored per key because the
# sweep below has to prune each bucket against its own window.
_buckets: dict[str, tuple[int, deque[float]]] = {}
_lock = threading.Lock()
_last_sweep = 0.0


def client_ip(request: Request) -> str:
    """Client IP, honouring one layer of trusted proxy."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _sweep(now: float) -> None:
    """Drop fully-expired buckets so memory cannot grow unbounded.

    Each bucket is pruned against *its own* window. Sweeping every bucket with
    whichever window happened to trigger the sweep expired entries early for
    keys with a longer window: a login attempt (15 min) would prune hour-old
    registration timestamps, quietly making the hourly registration limit far
    more permissive than configured.
    """
    global _last_sweep
    if now - _last_sweep < 60:
        return
    _last_sweep = now
    for key in list(_buckets.keys()):
        window, bucket = _buckets[key]
        while bucket and now - bucket[0] > window:
            bucket.popleft()
        if not bucket:
            del _buckets[key]


def hit(key: str, limit: int, window_seconds: int) -> bool:
    """Record an attempt. Returns True if allowed, False if the limit is hit."""
    now = time.monotonic()
    with _lock:
        _sweep(now)
        _, bucket = _buckets.get(key, (window_seconds, deque()))
        while bucket and now - bucket[0] > window_seconds:
            bucket.popleft()
        allowed = len(bucket) < limit
        if allowed:
            bucket.append(now)
        _buckets[key] = (window_seconds, bucket)
        return allowed


def enforce(key: str, limit: int, window_seconds: int, message: str) -> None:
    if not hit(key, limit, window_seconds):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=message,
            headers={"Retry-After": str(window_seconds)},
        )


def reset(key: str) -> None:
    with _lock:
        _buckets.pop(key, None)
