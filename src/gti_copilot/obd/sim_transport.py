"""Simulator transport: drives the whole stack from :class:`VehicleModel` with no hardware.

It advances the physics model in real (or scaled) time, encodes the resulting engineering
values back into OBD byte payloads via :func:`gti_copilot.obd.pids.encode`, and answers
``query``/``read_dtcs`` exactly like a real adapter would — so the same decode path runs in CI
as on the car. Occasional dropped responses and scenario-driven ``adapter_down`` windows
exercise the reconnect logic.
"""

from __future__ import annotations

import asyncio
import contextlib
import random
import time

from gti_copilot.errors import NotConnectedError, TransportError
from gti_copilot.obd import pids
from gti_copilot.obd.dtc import encode_dtc
from gti_copilot.obd.transport import BaseTransport, Dtc, RawResponse
from gti_copilot.vehicle.model import VehicleSpec
from gti_copilot.vehicle.physics import VehicleModel
from gti_copilot.vehicle.scenarios import Scenario, get_scenario

# Map PID -> attribute on VehicleState (or a callable) used to synthesise the value.
_PID_SOURCES: dict[int, str] = {
    0x04: "load_pct",
    0x05: "coolant_c",
    0x0B: "map_kpa",
    0x0C: "rpm",
    0x0D: "speed_kph",
    0x0E: "timing_deg",
    0x0F: "iat_c",
    0x10: "maf_gps",
    0x11: "throttle",
    0x2F: "fuel_level_pct",
    0x33: "baro_kpa",
    0x42: "volt_v",
    0x45: "throttle",
    0x46: "ambient_c",
    0x49: "throttle",
    0x4A: "throttle",
    0x5C: "oil_c",
    0x5E: "fuel_rate_lph",
    0x06: "stft_pct",
    0x07: "ltft_pct",
}


class SimTransport(BaseTransport):
    """In-memory transport backed by the physics simulator."""

    def __init__(
        self,
        vehicle: VehicleSpec,
        scenario: Scenario | str = "demo_drive",
        *,
        seed: int = 42,
        time_scale: float = 1.0,
        dropout: bool = True,
        step_dt: float = 0.02,
        drop_probability: float = 0.01,
        connect_delay_s: float = 0.05,
    ) -> None:
        super().__init__()
        self.vehicle = vehicle
        self.scenario = get_scenario(scenario) if isinstance(scenario, str) else scenario
        self.time_scale = time_scale
        self.dropout_enabled = dropout
        self.step_dt = step_dt
        self.drop_probability = drop_probability
        self.connect_delay_s = connect_delay_s
        self._rng = random.Random(seed)
        self._model = VehicleModel(
            spec=vehicle,
            seed=seed,
            ambient_c=self.scenario.ambient_c,
            baro_kpa=self.scenario.baro_kpa,
            start_coolant_c=self.scenario.start_coolant_c,
            thermostat_offset_c=self.scenario.thermostat_offset_c,
        )
        self._supported = self._compute_supported()
        self._task: asyncio.Task[None] | None = None
        self._sim_t = 0.0
        self._wall_start = 0.0
        self._adapter_down = False

    # ----------------------------------------------------------------- properties
    @property
    def name(self) -> str:
        return f"SimTransport[{self.scenario.name}]"

    @property
    def sim_time(self) -> float:
        return self._sim_t

    @property
    def model(self) -> VehicleModel:
        return self._model

    @property
    def adapter_down(self) -> bool:
        return self._adapter_down

    # ----------------------------------------------------------------- support map
    def _compute_supported(self) -> set[int]:
        base = set(self.vehicle.pids.expected) | {p.pid for p in pids.PIDS if not p.optional}
        for opt in self.vehicle.pids.optional:
            if opt in self.scenario.supported_optional_pids:
                base.add(opt)
        return {p for p in base if p in pids.BY_PID}

    # ----------------------------------------------------------------- lifecycle hooks
    async def _do_connect(self) -> None:
        await asyncio.sleep(self.connect_delay_s)
        self._wall_start = time.monotonic() - self._sim_t / max(self.time_scale, 1e-6)
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run())

    async def _do_close(self) -> None:
        task = self._task
        self._task = None
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    async def _run(self) -> None:
        """Advance the physics model in the background at ``step_dt`` resolution."""
        try:
            while True:
                await asyncio.sleep(self.step_dt / max(self.time_scale, 1e-6))
                now = time.monotonic()
                target = (now - self._wall_start) * self.time_scale
                # Catch up in fixed steps (bounded to avoid a spiral after a stall).
                steps = 0
                while self._sim_t < target and steps < 50:
                    seg, _ = self.scenario.at(self._sim_t)
                    self._adapter_down = self.dropout_enabled and seg.adapter_down
                    self._model.step(self.step_dt, seg.input_at(self._sim_t))
                    self._sim_t += self.step_dt
                    steps += 1
        except asyncio.CancelledError:
            raise

    # ----------------------------------------------------------------- query hooks
    async def _do_supported_pids(self) -> set[int]:
        self._maybe_fail()
        return set(self._supported)

    async def _do_query(self, mode: int, pid: int, request: str) -> RawResponse | None:
        self._maybe_fail()
        if pid not in self._supported:
            return None
        value = self._value_for(pid)
        if value is None:
            return None
        data = pids.encode(pid, value)
        return RawResponse(mode=mode, pid=pid, data=data, ts=time.time(), latency_ms=8.0)

    async def _do_read_dtcs(self) -> list[Dtc]:
        self._maybe_fail()
        out: list[Dtc] = []
        for code in self.scenario.dtcs:
            encode_dtc(code)  # validates the code round-trips
            out.append(Dtc(code=code, kind="stored"))
        for code in self.scenario.pending_dtcs:
            encode_dtc(code)
            out.append(Dtc(code=code, kind="pending"))
        return out

    # ----------------------------------------------------------------- helpers
    def _value_for(self, pid: int) -> float | None:
        s = self._model.state
        attr = _PID_SOURCES.get(pid)
        if attr is None:
            return None
        raw = getattr(s, attr, None)
        if raw is None:
            return None
        value = float(raw)
        if pid in (0x11, 0x45, 0x49, 0x4A):  # throttle/pedal stored 0..1 -> %
            value *= 100.0
        pdef = pids.BY_PID[pid]
        return max(pdef.min, min(pdef.max, value))

    def _maybe_fail(self) -> None:
        if self._adapter_down:
            self._mark_disconnected("adapter down (scenario dropout)")
            raise TransportError("simulated adapter drop-out")
        if not self._connected:
            raise NotConnectedError(f"{self.name} is not connected")
        if self.dropout_enabled and self._rng.random() < self.drop_probability:
            self._stats.timeouts += 1
            raise TransportError("simulated dropped response")

    def seek(self, sim_t: float) -> None:
        """Fast-forward the model to ``sim_t`` (used by tests and screenshot capture)."""
        while self._sim_t < sim_t:
            seg, _ = self.scenario.at(self._sim_t)
            self._adapter_down = self.dropout_enabled and seg.adapter_down
            self._model.step(self.step_dt, seg.input_at(self._sim_t))
            self._sim_t += self.step_dt
