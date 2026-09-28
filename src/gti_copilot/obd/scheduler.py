"""Tiered adaptive PID scheduler.

Real ELM/STN adapters manage ~5-15 single-PID reads per second. The scheduler splits PIDs into
fast / medium / slow tiers, each with a target rate, and issues reads round-robin while
respecting a global ceiling (``max_reads_per_s``). It:

* skips PIDs the ECU does not support,
* backs off PIDs that repeatedly error (exponential, capped) and retries them later,
* measures the achieved per-PID rate (exposed via :meth:`rates` for ``/api/health``),
* shrinks tier rates automatically when the adapter cannot keep up,
* never raises out of :meth:`poll_once`; transport errors are recorded and surfaced as events.

The scheduler is transport-agnostic: give it anything satisfying ``ObdTransport``.
"""

from __future__ import annotations

import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field

from gti_copilot.config import SchedulerConfig
from gti_copilot.errors import TransportError
from gti_copilot.obd import pids
from gti_copilot.obd.pids import Tier
from gti_copilot.obd.transport import ObdTransport, RawResponse


@dataclass
class _PidState:
    pid: int
    tier: Tier
    interval: float
    next_due: float = 0.0
    fail_streak: int = 0
    backoff_until: float = 0.0
    last_ok: float | None = None
    _stamps: deque[float] = field(default_factory=lambda: deque(maxlen=20))

    def record_ok(self, now: float) -> None:
        self.fail_streak = 0
        self.backoff_until = 0.0
        self.last_ok = now
        self._stamps.append(now)

    def record_fail(self, now: float, base_backoff: float) -> None:
        self.fail_streak += 1
        self.backoff_until = now + min(base_backoff * (2 ** (self.fail_streak - 1)), 30.0)

    def rate_hz(self, now: float, window: float = 5.0) -> float:
        recent = [t for t in self._stamps if now - t <= window]
        if len(recent) < 2:
            return 0.0
        span = recent[-1] - recent[0]
        return (len(recent) - 1) / span if span > 0 else 0.0


@dataclass
class SampleResult:
    """One poll cycle's decoded values plus bookkeeping."""

    ts: float
    values: dict[str, float]
    raw: dict[int, RawResponse]
    errors: int = 0


class TieredScheduler:
    def __init__(
        self,
        transport: ObdTransport,
        config: SchedulerConfig,
        supported: set[int],
        *,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self.transport = transport
        self.config = config
        self._clock = clock or time.monotonic
        self._tier_rate = {
            Tier.FAST: config.fast_hz,
            Tier.MEDIUM: config.medium_hz,
            Tier.SLOW: config.slow_hz,
        }
        self._rate_scale = 1.0
        self._states: dict[int, _PidState] = {}
        self._order: list[int] = []
        self._budget_window: deque[float] = deque(maxlen=200)
        self.set_supported(supported)

    # ----------------------------------------------------------------- config
    def set_supported(self, supported: set[int]) -> None:
        now = self._clock()
        states: dict[int, _PidState] = {}
        order: list[int] = []
        for pdef in pids.PIDS:
            if pdef.pid not in supported:
                continue
            interval = self._interval_for(pdef.tier)
            prev = self._states.get(pdef.pid)
            st = prev or _PidState(pid=pdef.pid, tier=pdef.tier, interval=interval, next_due=now)
            st.interval = interval
            states[pdef.pid] = st
            order.append(pdef.pid)
        self._states = states
        self._order = order

    def _interval_for(self, tier: Tier) -> float:
        hz = max(0.01, self._tier_rate[tier] * self._rate_scale)
        return 1.0 / hz

    def _reindex_intervals(self) -> None:
        for st in self._states.values():
            st.interval = self._interval_for(st.tier)

    # ----------------------------------------------------------------- polling
    def due_pids(self, now: float | None = None) -> list[int]:
        now = self._clock() if now is None else now
        due = [
            pid
            for pid, st in self._states.items()
            if now >= st.next_due and now >= st.backoff_until
        ]
        due.sort(key=lambda p: (self._states[p].tier != Tier.FAST, self._states[p].next_due))
        ceiling = max(1, int(self.config.max_reads_per_s * self._rate_scale))
        return due[:ceiling]

    async def poll_once(self) -> SampleResult:
        now = self._clock()
        result = SampleResult(ts=time.time(), values={}, raw={})
        for pid in self.due_pids(now):
            st = self._states[pid]
            st.next_due = now + st.interval
            try:
                resp = await self.transport.query(0x01, pid)
            except TransportError:
                st.record_fail(now, self.config.failure_backoff_s)
                result.errors += 1
                continue
            except Exception:
                st.record_fail(now, self.config.failure_backoff_s)
                result.errors += 1
                continue
            if resp is None:
                st.record_fail(now, self.config.failure_backoff_s)
                continue
            try:
                value = pids.decode(pid, resp.data)
            except Exception:
                st.record_fail(now, self.config.failure_backoff_s)
                result.errors += 1
                continue
            st.record_ok(now)
            self._budget_window.append(now)
            result.values[pids.BY_PID[pid].key] = value
            result.raw[pid] = resp
        self._adapt(now, result)
        return result

    def _adapt(self, now: float, result: SampleResult) -> None:
        """Shrink tier rates if the achieved fast-tier rate lags the target badly."""
        fast_targets = [p for p, s in self._states.items() if s.tier is Tier.FAST]
        if not fast_targets:
            return
        achieved = sum(self._states[p].rate_hz(now) for p in fast_targets) / len(fast_targets)
        target = self._tier_rate[Tier.FAST] * self._rate_scale
        if achieved and achieved < target * 0.6 and self._rate_scale > 0.3:
            self._rate_scale = max(0.3, self._rate_scale * 0.9)
            self._reindex_intervals()
        elif achieved > target * 0.95 and self._rate_scale < 1.0:
            self._rate_scale = min(1.0, self._rate_scale * 1.05)
            self._reindex_intervals()

    # ----------------------------------------------------------------- health
    def rates(self) -> dict[str, float]:
        now = self._clock()
        return {pids.BY_PID[pid].key: round(st.rate_hz(now), 2) for pid, st in self._states.items()}

    def backed_off(self) -> list[str]:
        now = self._clock()
        return [pids.BY_PID[p].key for p, s in self._states.items() if now < s.backoff_until]

    @property
    def rate_scale(self) -> float:
        return self._rate_scale

    @property
    def achieved_read_rate(self) -> float:
        now = self._clock()
        recent = [t for t in self._budget_window if now - t <= 1.0]
        return float(len(recent))
