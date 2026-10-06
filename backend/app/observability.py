"""Per-request timing: where did this request's time go?

Every request gets an ID and a small metrics dict (in a ContextVar) that the
database layer, outbound HTTP calls and password hashing add to. At the end
the middleware logs one structured line and returns:

  X-Request-ID:   to correlate a user's report with the server log
  Server-Timing:  app / db / ext / hash durations, readable in browser
                  devtools and by curl, so production latency can be measured
                  from outside without log access.

Query *counts* are only logged, never sent to the client: per-request counts
could distinguish code paths (e.g. existing vs unknown account) more reliably
than wall-clock timing does.

Nothing sensitive is logged: no bodies, headers, cookies, tokens or emails —
just method, route path, status and timings.
"""
from __future__ import annotations

import logging
import time
import uuid
from contextlib import asynccontextmanager
from contextvars import ContextVar

from fastapi import Request

logger = logging.getLogger("tgl.perf")

_metrics: ContextVar[dict | None] = ContextVar("tgl_request_metrics", default=None)

# A request slower than this is logged at WARNING, above CRITICAL_MS at ERROR.
SLOW_MS = 800
CRITICAL_MS = 2500


def _new_metrics() -> dict:
    return {"db_ms": 0.0, "db_count": 0, "ext_ms": 0.0, "ext_count": 0, "hash_ms": 0.0}


def add(kind: str, ms: float) -> None:
    """Attribute `ms` of the current request to db / ext / hash."""
    m = _metrics.get()
    if m is None:
        return
    m[f"{kind}_ms"] += ms
    if f"{kind}_count" in m:
        m[f"{kind}_count"] += 1


@asynccontextmanager
async def timed(kind: str):
    start = time.perf_counter()
    try:
        yield
    finally:
        add(kind, (time.perf_counter() - start) * 1000)


def install_db_timing(engine) -> None:
    """Time every statement the engine executes (all tables, all endpoints)."""
    from sqlalchemy import event

    @event.listens_for(engine.sync_engine, "before_cursor_execute")
    def _before(conn, cursor, statement, parameters, context, executemany):  # pragma: no cover - hook
        conn.info.setdefault("tgl_t0", []).append(time.perf_counter())

    @event.listens_for(engine.sync_engine, "after_cursor_execute")
    def _after(conn, cursor, statement, parameters, context, executemany):  # pragma: no cover - hook
        stack = conn.info.get("tgl_t0")
        if stack:
            add("db", (time.perf_counter() - stack.pop()) * 1000)


async def timing_middleware(request: Request, call_next):
    request_id = request.headers.get("x-request-id", "")[:64] or uuid.uuid4().hex[:12]
    metrics = _new_metrics()
    token = _metrics.set(metrics)
    start = time.perf_counter()
    status = 500
    try:
        response = await call_next(request)
        status = response.status_code
    finally:
        total = (time.perf_counter() - start) * 1000
        _metrics.reset(token)
        path = request.url.path
        if path.startswith("/api"):
            line = (
                "request_id=%s method=%s path=%s status=%s total_ms=%.0f db_ms=%.0f db_queries=%d "
                "ext_ms=%.0f ext_calls=%d hash_ms=%.0f"
            )
            args = (
                request_id, request.method, path, status, total, metrics["db_ms"], metrics["db_count"],
                metrics["ext_ms"], metrics["ext_count"], metrics["hash_ms"],
            )
            level = logging.ERROR if total > CRITICAL_MS else logging.WARNING if total > SLOW_MS else logging.INFO
            logger.log(level, ("SLOW " if level > logging.INFO else "") + line, *args)
    response.headers["X-Request-ID"] = request_id
    if path.startswith("/api"):
        app_ms = max(0.0, total - metrics["db_ms"] - metrics["ext_ms"] - metrics["hash_ms"])
        response.headers["Server-Timing"] = (
            f"total;dur={total:.0f}, db;dur={metrics['db_ms']:.0f}, ext;dur={metrics['ext_ms']:.0f}, "
            f"hash;dur={metrics['hash_ms']:.0f}, app;dur={app_ms:.0f}"
        )
    return response
