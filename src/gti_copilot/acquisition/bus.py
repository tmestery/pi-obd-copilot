"""In-process async event bus.

Topics are plain strings (see :data:`TOPICS`). Handlers may be sync or async. Publishing never
raises because of a handler: exceptions are logged and counted so one misbehaving subscriber
(e.g. the co-pilot) cannot take down acquisition or storage.

Usage::

    bus = EventBus()
    unsub = bus.subscribe("telemetry", lambda ev: print(ev.payload))
    await bus.publish("telemetry", snapshot)
    unsub()
"""

from __future__ import annotations

import asyncio
import contextlib
import inspect
import logging
import time
from collections import defaultdict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

log = logging.getLogger(__name__)

TOPICS: tuple[str, ...] = (
    "telemetry",  # payload: gti_copilot.telemetry.TelemetrySnapshot
    "event",  # payload: gti_copilot.telemetry.DriveEvent
    "adapter",  # payload: {"state": "connected"|"disconnected"|"connecting", "name": str, ...}
    "trip",  # payload: {"state": "started"|"ended", "trip_id": int, ...}
    "dtcs",  # payload: {"codes": [ {code, kind, description}, ... ]}
    "gps",  # payload: gti_copilot.gps.provider.GpsFix
    "radar",  # payload: gti_copilot.radar.provider.RadarAlert
    "power",  # payload: {"state": "on"|"ignition_off"|"low_voltage"|"shutdown", "seconds_left": n}
    "clip",  # payload: {"state": "saved"|"failed", "clip_id": ..., "path": ...}
    "copilot",  # payload: {"kind": "alert"|"summary"|"answer", "text": str, ...}
    "perf",  # payload: {"state": "armed"|"running"|"complete"|"aborted", "kind": "0-60", ...}
    "status",  # payload: free-form status for the UI status bar
)

Handler = Callable[["Event"], Awaitable[None] | None]


@dataclass(frozen=True, slots=True)
class Event:
    topic: str
    payload: Any
    ts: float


@dataclass
class EventBus:
    _handlers: dict[str, list[Handler]] = field(default_factory=lambda: defaultdict(list))
    published: int = 0
    handler_errors: int = 0
    _last: dict[str, Event] = field(default_factory=dict)
    _tasks: set[asyncio.Task[Event]] = field(default_factory=set)

    def subscribe(self, topic: str, handler: Handler) -> Callable[[], None]:
        self._handlers[topic].append(handler)

        def _unsubscribe() -> None:
            with contextlib.suppress(ValueError):
                self._handlers[topic].remove(handler)

        return _unsubscribe

    def subscribers(self, topic: str) -> int:
        return len(self._handlers.get(topic, ()))

    def last(self, topic: str) -> Event | None:
        return self._last.get(topic)

    async def publish(self, topic: str, payload: Any, ts: float | None = None) -> Event:
        ev = Event(topic=topic, payload=payload, ts=time.time() if ts is None else ts)
        self.published += 1
        self._last[topic] = ev
        for handler in list(self._handlers.get(topic, ())):
            try:
                result = handler(ev)
                if inspect.isawaitable(result):
                    await result
            except Exception:
                self.handler_errors += 1
                log.exception("event handler failed", extra={"topic": topic})
        return ev

    def publish_nowait(self, topic: str, payload: Any, ts: float | None = None) -> None:
        """Schedule a publish from sync code running inside the event loop."""
        loop = asyncio.get_running_loop()
        task = loop.create_task(self.publish(topic, payload, ts))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    def clear(self) -> None:
        self._handlers.clear()
        self._last.clear()
