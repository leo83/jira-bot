"""Watchdog that restarts the process when Telegram polling silently stalls.

After a proxy failure the PTB polling task can hang forever: the process stays
alive, the pod stays ``Running``, but no updates are fetched. The watchdog runs
in its own thread (independent of the asyncio loop, so it fires even if the
loop is blocked) and calls ``os._exit(1)`` when no ``getUpdates`` request has
completed for ``timeout`` seconds; Kubernetes then restarts the container.
"""

import logging
import os
import threading
import time
from typing import Any, Callable, Optional

from telegram.request import HTTPXRequest

logger = logging.getLogger(__name__)


def _exit_process() -> None:
    for handler in logging.getLogger().handlers:
        try:
            handler.flush()
        except Exception:
            pass
    os._exit(1)


class PollingWatchdog:
    """Kill the process if ``beat()`` is not called for ``timeout`` seconds.

    Handlers make synchronous Jira/ClickHouse calls on the event loop, so a long
    command (e.g. a big ``/linkmany``) legitimately delays polling. While any
    handler is running (``handler_started``/``handler_finished``) the more lenient
    ``busy_timeout`` applies instead.
    """

    def __init__(
        self,
        timeout: float,
        check_interval: float = 15.0,
        on_stall: Optional[Callable[[], None]] = None,
        clock: Callable[[], float] = time.monotonic,
        busy_timeout: float = 1800.0,
    ):
        self.timeout = timeout
        self.busy_timeout = max(busy_timeout, timeout)
        self.check_interval = check_interval
        self._on_stall = on_stall or _exit_process
        self._clock = clock
        self._last_beat = clock()
        self._busy = 0
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def beat(self) -> None:
        self._last_beat = self._clock()

    def handler_started(self) -> None:
        self._busy += 1

    def handler_finished(self) -> None:
        self._busy = max(0, self._busy - 1)

    def seconds_since_beat(self) -> float:
        return self._clock() - self._last_beat

    def check(self) -> bool:
        """Return True (and trigger ``on_stall``) if polling has stalled."""
        idle = self.seconds_since_beat()
        limit = self.busy_timeout if self._busy > 0 else self.timeout
        if idle <= limit:
            return False
        logger.critical(
            f"No completed getUpdates request for {idle:.0f}s (limit {limit:.0f}s, "
            f"handlers running: {self._busy}): Telegram polling is stuck. Restarting application..."
        )
        self._on_stall()
        return True

    def _run(self) -> None:
        while not self._stop.wait(self.check_interval):
            if self.check():
                return

    def start(self) -> None:
        self.beat()
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run, name="polling-watchdog", daemon=True
        )
        self._thread.start()
        logger.info(f"Polling watchdog started (timeout {self.timeout:.0f}s)")

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=self.check_interval + 1)
            self._thread = None


class HeartbeatHTTPXRequest(HTTPXRequest):
    """``HTTPXRequest`` for getUpdates that reports every completed HTTP round-trip.

    Any HTTP response (even an error status from Telegram) proves the proxy and
    the polling loop are alive; transport errors (proxy down, hung connect)
    raise before ``beat()`` and therefore count as a stall.
    """

    def __init__(self, watchdog: PollingWatchdog, **kwargs: Any):
        super().__init__(**kwargs)
        self._watchdog = watchdog

    async def do_request(self, *args: Any, **kwargs: Any) -> tuple[int, bytes]:
        result = await super().do_request(*args, **kwargs)
        self._watchdog.beat()
        return result
