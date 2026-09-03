"""Fork-safe ASGI->WSGI adapter, for pre-forking servers (uWSGI/PythonAnywhere).

a2wsgi's ASGIMiddleware starts a background thread running an asyncio event
loop inside __init__. Pre-forking servers import the WSGI module in the master
process and then fork() their workers -- and threads do not survive fork(), so
each worker inherits a loop object with nobody running it.

The failure mode is nasty precisely because it is silent: every request queues
callbacks onto that dead loop and then blocks forever on a threading.Event
that will never be set. No exception is raised, nothing reaches the error log,
and the request just hangs until the server's watchdog kills the worker.

This wrapper defers building the adapter until the first request *in the
process that actually serves it*, and rebuilds it if the PID changes (i.e.
after a fork). Because the loop is then created once per worker and lives for
that worker's lifetime, SQLAlchemy's pooled connections stay bound to a single
running loop, which is what the pool expects.
"""
from __future__ import annotations

import os
import threading
from typing import Any, Callable, Iterable

from a2wsgi import ASGIMiddleware


class ForkSafeASGIMiddleware:
    """Wraps an ASGI app as a WSGI callable, safely across fork()."""

    def __init__(self, app: Any) -> None:
        self._app = app
        self._adapter: ASGIMiddleware | None = None
        self._pid: int | None = None
        self._lock = threading.Lock()

    def _adapter_for_this_process(self) -> ASGIMiddleware:
        pid = os.getpid()
        # Fast path: already built in this process.
        if self._adapter is not None and self._pid == pid:
            return self._adapter
        with self._lock:
            # Re-check under the lock; another thread may have just built it.
            if self._adapter is None or self._pid != pid:
                self._adapter = ASGIMiddleware(self._app)
                self._pid = pid
        return self._adapter

    def __call__(
        self, environ: dict, start_response: Callable
    ) -> Iterable[bytes]:
        return self._adapter_for_this_process()(environ, start_response)
