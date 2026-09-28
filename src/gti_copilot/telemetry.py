"""Shared data contracts that flow between subsystems (bus payloads, DB rows, WS messages).

Keep these small, serialisable and stable: the storage layer, API schemas, perf detectors,
radar fusion, camera sidecars and the co-pilot facts all consume them.
"""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

ShiftState = Literal["none", "warn", "shift"]
Severity = Literal["info", "warning", "critical"]

EventType = Literal[
    "hard_brake",
    "hard_accel",
    "over_rev",
    "launch",
    "perf_run",
    "coolant_high",
    "iat_high",
    "voltage_low",
    "voltage_high",
    "adapter_disconnected",
    "adapter_connected",
    "dtc_new",
    "radar_alert",
    "manual",
    "power_ignition_off",
    "power_low_voltage",
    "trip_started",
    "trip_ended",
]


@dataclass(slots=True)
class TelemetrySnapshot:
    """Latest fused view of the car. ``None`` means "not available (yet)".

    All fields are SI: km/h, kPa, °C, g/s, V, degrees, g. ``t`` is wall-clock seconds
    (``time.time()``); ``mono`` is a monotonic timestamp for rate calculations.
    """

    t: float
    mono: float = 0.0
    rpm: float | None = None
    speed_kph: float | None = None
    map_kpa: float | None = None
    baro_kpa: float | None = None
    boost_kpa: float | None = None
    throttle_pct: float | None = None
    load_pct: float | None = None
    coolant_c: float | None = None
    iat_c: float | None = None
    ambient_c: float | None = None
    maf_gps: float | None = None
    volt_v: float | None = None
    timing_deg: float | None = None
    fuel_rate_lph: float | None = None
    fuel_level_pct: float | None = None
    oil_temp_c: float | None = None
    stft_pct: float | None = None
    ltft_pct: float | None = None
    pedal_pct: float | None = None
    gear: int | None = None
    shift: ShiftState = "none"
    accel_g: float | None = None
    peak_boost_kpa: float | None = None
    peak_rpm: float | None = None
    peak_speed_kph: float | None = None
    instant_mpg: float | None = None
    lat: float | None = None
    lon: float | None = None
    gps_speed_kph: float | None = None
    heading_deg: float | None = None
    gps_fix: bool = False
    adapter_connected: bool = False
    trip_id: int | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def moving(self) -> bool:
        return (self.speed_kph or 0.0) > 3.0


@dataclass(slots=True)
class DriveEvent:
    """Something notable that happened; persisted to ``events`` and broadcast on the bus."""

    type: EventType
    ts: float
    severity: Severity = "info"
    payload: dict[str, Any] = field(default_factory=dict)
    lat: float | None = None
    lon: float | None = None
    trip_id: int | None = None
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    db_id: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class PerfRun:
    """A completed (or aborted) performance timer run, e.g. 0-60 mph."""

    kind: str  # "0-60", "0-100kph", "60-130", "quarter_mile"
    started_ts: float
    duration_s: float | None
    curve: list[tuple[float, float]]  # (t_rel_s, speed_kph)
    completed: bool
    trip_id: int | None = None
    peak_g: float | None = None
    db_id: int | None = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["curve"] = [list(p) for p in self.curve]
        return d
