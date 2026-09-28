"""OBD transport abstraction shared by the simulator and the real ELM/STN adapter.

Every concrete transport derives from :class:`BaseTransport`, whose ``query`` / ``read_dtcs``
wrappers run the request through the read-only :mod:`gti_copilot.obd.allowlist` before
delegating to the implementation hook. There is no way to construct a transport without the
guard: ``BaseTransport.__init__`` binds the module-level immutable ``GUARD`` and rejects any
attempt to pass a replacement.
"""

from __future__ import annotations

import random
import time
from abc import ABC, abstractmethod
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Literal, Protocol, runtime_checkable

from gti_copilot.errors import ForbiddenServiceError, NotConnectedError
from gti_copilot.obd.allowlist import GUARD, ReadOnlyGuard, guard_request

DtcKind = Literal["stored", "pending", "permanent"]


@dataclass(frozen=True, slots=True)
class RawResponse:
    """Payload bytes of a positive response (after the service+PID echo) and timing info."""

    mode: int
    pid: int
    data: bytes
    ts: float
    latency_ms: float = 0.0


@dataclass(frozen=True, slots=True)
class Dtc:
    code: str
    kind: DtcKind
    description: str = ""


@dataclass(slots=True)
class TransportStats:
    queries: int = 0
    errors: int = 0
    timeouts: int = 0
    reconnects: int = 0
    last_error: str | None = None
    connected_since: float | None = None


@runtime_checkable
class ObdTransport(Protocol):
    """Structural interface used by the scheduler, acquisition service and tests."""

    async def connect(self) -> None: ...
    async def close(self) -> None: ...
    async def supported_pids(self) -> set[int]: ...
    async def query(self, mode: int, pid: int) -> RawResponse | None: ...
    async def read_dtcs(self) -> list[Dtc]: ...
    @property
    def connected(self) -> bool: ...
    @property
    def name(self) -> str: ...
    @property
    def stats(self) -> TransportStats: ...


class BaseTransport(ABC):
    """Guard-enforcing base. Subclasses implement the ``_do_*`` hooks only."""

    def __init__(self, *, guard: ReadOnlyGuard | None = None) -> None:
        # The only accepted value is the canonical immutable guard (or None meaning "default").
        # Passing anything else, including a disabled/mocked guard, is a hard error.
        if guard is not None and guard is not GUARD:
            raise ForbiddenServiceError("custom or disabled allowlist guards are not permitted")
        self._guard: ReadOnlyGuard = GUARD
        self._stats = TransportStats()
        self._connected = False

    # ----------------------------------------------------------------- public API
    @property
    def guard(self) -> ReadOnlyGuard:
        return self._guard

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def stats(self) -> TransportStats:
        return self._stats

    @property
    @abstractmethod
    def name(self) -> str: ...

    async def connect(self) -> None:
        await self._do_connect()
        self._connected = True
        self._stats.connected_since = time.time()

    async def close(self) -> None:
        try:
            await self._do_close()
        finally:
            self._connected = False
            self._stats.connected_since = None

    async def supported_pids(self) -> set[int]:
        self._require_connected()
        # Support bitmaps are Mode 01 PIDs 0x00/0x20/... - guard them like any other request.
        guard_request(0x01, 0x00)
        return await self._do_supported_pids()

    async def query(self, mode: int, pid: int) -> RawResponse | None:
        request = guard_request(mode, pid)  # raises ForbiddenServiceError before any I/O
        self._require_connected()
        self._stats.queries += 1
        return await self._do_query(mode, pid, request)

    async def read_dtcs(self) -> list[Dtc]:
        self._require_connected()
        for mode in (0x03, 0x07, 0x0A):
            guard_request(mode)
        return await self._do_read_dtcs()

    # ----------------------------------------------------------------- hooks
    @abstractmethod
    async def _do_connect(self) -> None: ...

    @abstractmethod
    async def _do_close(self) -> None: ...

    @abstractmethod
    async def _do_supported_pids(self) -> set[int]: ...

    @abstractmethod
    async def _do_query(self, mode: int, pid: int, request: str) -> RawResponse | None: ...

    @abstractmethod
    async def _do_read_dtcs(self) -> list[Dtc]: ...

    # ----------------------------------------------------------------- helpers
    def _require_connected(self) -> None:
        if not self._connected:
            raise NotConnectedError(f"{self.name} is not connected")

    def _mark_disconnected(self, reason: str) -> None:
        self._connected = False
        self._stats.errors += 1
        self._stats.last_error = reason
        self._stats.connected_since = None


@dataclass(slots=True)
class Backoff:
    """Exponential backoff with full jitter, used by every reconnect loop."""

    min_s: float = 1.0
    max_s: float = 30.0
    factor: float = 2.0
    attempt: int = 0
    rng: random.Random = field(default_factory=random.Random)

    def next_delay(self) -> float:
        base = min(self.max_s, self.min_s * (self.factor**self.attempt))
        self.attempt += 1
        return self.rng.uniform(self.min_s * 0.5, base) if base > self.min_s * 0.5 else base

    def reset(self) -> None:
        self.attempt = 0

    def delays(self, n: int) -> Iterator[float]:
        for _ in range(n):
            yield self.next_delay()
