"""One shared outbound HTTP client (Resend, Supabase Storage).

A new httpx.AsyncClient per call paid a fresh TCP + TLS handshake to the
same hosts every time; one long-lived client keeps those connections warm.
Every call is timed into the request's `ext` metric (observability.py).
"""
from __future__ import annotations

import asyncio

import httpx

from .observability import timed

_client: httpx.AsyncClient | None = None
_loop: asyncio.AbstractEventLoop | None = None


def client() -> httpx.AsyncClient:
    """The shared client — one per event loop. A client's pooled connections
    belong to the loop that opened them; reusing them from another loop hangs.
    Production has a single loop, so this is one client for the process."""
    global _client, _loop
    loop = asyncio.get_running_loop()
    if _client is None or _client.is_closed or _loop is not loop:
        _loop = loop
        _client = httpx.AsyncClient(
            timeout=httpx.Timeout(20.0, connect=5.0),
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10, keepalive_expiry=60),
        )
    return _client


async def request(method: str, url: str, **kwargs) -> httpx.Response:
    async with timed("ext"):
        return await client().request(method, url, **kwargs)


async def aclose() -> None:
    global _client
    if _client is not None and _loop is asyncio.get_running_loop():
        await _client.aclose()
    _client = None
