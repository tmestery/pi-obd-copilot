"""Driving scenarios: time-ordered segments of driver input that feed :class:`VehicleModel`.

Scenarios are plain Python so they are type-checked and easy to compose. ``SCENARIOS`` is the
registry used by ``--scenario``. ``demo_drive`` is the ~3 minute scripted drive that touches
every UI feature and is used for screenshots, the GIF and the e2e tests.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field, replace

from gti_copilot.vehicle.physics import DriverInput


@dataclass(frozen=True, slots=True)
class Segment:
    duration_s: float
    throttle: float = 0.0
    throttle_end: float | None = None  # linear ramp when set
    brake: float = 0.0
    gear: int | None = None
    shift_up_rpm: float = 3000.0
    shift_down_rpm: float = 1400.0
    ignition_on: bool = True
    engine_on: bool = True
    clutch_in: bool = False
    adapter_down: bool = False  # simulate a Bluetooth/USB drop-out for this segment
    label: str = ""
    marker: str | None = None  # named moment used by mock radar / tests (e.g. "radar_ka")

    def input_at(self, elapsed: float) -> DriverInput:
        thr = self.throttle
        if self.throttle_end is not None and self.duration_s > 0:
            f = max(0.0, min(1.0, elapsed / self.duration_s))
            thr = self.throttle + (self.throttle_end - self.throttle) * f
        return DriverInput(
            throttle=thr,
            brake=self.brake,
            gear=self.gear,
            shift_up_rpm=self.shift_up_rpm,
            shift_down_rpm=self.shift_down_rpm,
            ignition_on=self.ignition_on,
            engine_on=self.engine_on,
            clutch_in=self.clutch_in,
        )


@dataclass(frozen=True)
class Scenario:
    name: str
    description: str
    segments: tuple[Segment, ...]
    ambient_c: float = 22.0
    baro_kpa: float = 99.0
    start_coolant_c: float | None = None
    thermostat_offset_c: float = 0.0
    loop: bool = True
    dtcs: tuple[str, ...] = ()  # stored DTCs the simulated ECU reports
    pending_dtcs: tuple[str, ...] = ()
    supported_optional_pids: frozenset[int] = frozenset({0x5C, 0x5E})
    tags: tuple[str, ...] = field(default_factory=tuple)

    @property
    def duration_s(self) -> float:
        return sum(seg.duration_s for seg in self.segments)

    def at(self, t: float) -> tuple[Segment, float]:
        """Segment active at scenario time ``t`` (looping if configured) and elapsed within it."""
        total = self.duration_s
        if total <= 0:
            raise ValueError("scenario has no duration")
        t = t % total if self.loop else min(t, total - 1e-6)
        acc = 0.0
        for seg in self.segments:
            if t < acc + seg.duration_s:
                return seg, t - acc
            acc += seg.duration_s
        return self.segments[-1], self.segments[-1].duration_s

    def markers(self) -> Iterator[tuple[float, str]]:
        acc = 0.0
        for seg in self.segments:
            if seg.marker:
                yield acc, seg.marker
            acc += seg.duration_s


# ----------------------------------------------------------------------------- building blocks
def key_on(duration: float = 5.0) -> Segment:
    return Segment(duration, engine_on=False, label="key on, engine off", marker="key_on")


def idle(duration: float, label: str = "idle") -> Segment:
    return Segment(duration, throttle=0.0, label=label)


def accelerate(
    duration: float, throttle: float, shift_up: float = 3000.0, label: str = ""
) -> Segment:
    return Segment(duration, throttle=throttle, shift_up_rpm=shift_up, label=label or "accelerate")


def cruise(
    duration: float, throttle: float = 0.18, gear: int | None = None, label: str = "cruise"
) -> Segment:
    return Segment(duration, throttle=throttle, gear=gear, shift_up_rpm=2600, label=label)


def brake(duration: float, force: float, label: str = "brake") -> Segment:
    return Segment(duration, throttle=0.0, brake=force, label=label)


def park(duration: float = 8.0) -> Segment:
    return Segment(duration, engine_on=False, ignition_on=False, label="parked", marker="park")


# ----------------------------------------------------------------------------- scenarios
COLD_START_IDLE = Scenario(
    "cold_start_idle",
    "Key on, engine start, idle for 4 minutes from cold (coolant warm-up, IAT soak).",
    (key_on(8), idle(240, "cold idle")),
    ambient_c=6.0,
    start_coolant_c=6.0,
    tags=("phase1",),
)

CITY_DRIVE = Scenario(
    "city_drive",
    "Stop-and-go: short accelerations to ~50 km/h, gentle braking, idle at lights.",
    (
        key_on(3),
        idle(4),
        accelerate(9, 0.35, label="pull away"),
        cruise(10, 0.14, label="cruise 50"),
        brake(5, 0.28, label="brake to light"),
        idle(6, "at light"),
        accelerate(8, 0.4),
        cruise(8, 0.15),
        brake(4, 0.35),
        idle(5),
    ),
    tags=("phase1",),
)

HIGHWAY_CRUISE = Scenario(
    "highway_cruise",
    "Merge to ~110 km/h and hold in 6th; steady MAP, low load.",
    (
        key_on(3),
        idle(3),
        accelerate(14, 0.6, shift_up=4200, label="on-ramp"),
        cruise(120, 0.24, label="cruise 110"),
    ),
    tags=("phase1",),
)

WOT_PULL_3RD = Scenario(
    "wot_pull_3rd_gear",
    "Roll at ~2500 rpm in 3rd, then wide-open throttle to ~6500 rpm; the classic boost pull.",
    (
        key_on(3),
        idle(3),
        accelerate(10, 0.4, shift_up=3200, label="build speed"),
        cruise(4, 0.12, gear=3, label="settle in 3rd"),
        Segment(9.0, throttle=1.0, gear=3, label="WOT 3rd", marker="wot_start"),
        Segment(4.0, throttle=0.0, gear=4, label="lift"),
        brake(6, 0.3),
        idle(4),
    ),
    tags=("phase1", "performance"),
)

LAUNCH_0_60 = Scenario(
    "launch_0_60",
    "Standing start, full throttle through the gears to 100+ km/h, then coast.",
    (
        key_on(3),
        idle(4, "staged"),
        Segment(11.0, throttle=1.0, shift_up_rpm=6500, label="launch", marker="launch"),
        cruise(5, 0.1),
        brake(8, 0.35),
        idle(4),
    ),
    tags=("phase1", "performance"),
)

HARD_BRAKE_FROM_70 = Scenario(
    "hard_brake_from_70",
    "Accelerate to ~70 mph (113 km/h) then brake hard (~0.7 g) to a stop.",
    (
        key_on(3),
        idle(3),
        accelerate(16, 0.75, shift_up=5000, label="to 70 mph"),
        cruise(4, 0.22),
        Segment(6.0, throttle=0.0, brake=0.72, label="hard brake", marker="hard_brake"),
        idle(6),
    ),
    tags=("phase1", "events"),
)

ADAPTER_DROPOUT = Scenario(
    "adapter_dropout",
    "Highway cruise with two Bluetooth drop-outs (5 s and 12 s) to exercise reconnect logic.",
    (
        key_on(3),
        idle(3),
        accelerate(12, 0.6, shift_up=4000),
        cruise(10, 0.22),
        Segment(
            5.0,
            throttle=0.22,
            shift_up_rpm=2600,
            adapter_down=True,
            label="dropout 1",
            marker="dropout",
        ),
        cruise(12, 0.22),
        Segment(12.0, throttle=0.22, shift_up_rpm=2600, adapter_down=True, label="dropout 2"),
        cruise(15, 0.22),
    ),
    tags=("phase1", "robustness"),
)

OVERHEAT_WARNING = Scenario(
    "overheat_warning",
    "Thermostat stuck: coolant climbs past 110 °C during a slow climb; pending P0128/P2181.",
    (
        key_on(3),
        idle(3),
        accelerate(10, 0.5),
        Segment(150.0, throttle=0.55, shift_up_rpm=3500, label="long climb", marker="overheat"),
        idle(10),
    ),
    ambient_c=35.0,
    start_coolant_c=88.0,
    thermostat_offset_c=32.0,
    pending_dtcs=("P2181",),
    tags=("phase1", "warnings"),
)

LONG_MIXED_TRIP = Scenario(
    "long_mixed_trip",
    "~12 minutes mixing city, highway, a spirited pull and a hard stop; for soak/retention tests.",
    (
        key_on(4),
        idle(6),
        *CITY_DRIVE.segments[2:],
        accelerate(14, 0.6, shift_up=4200),
        cruise(150, 0.24),
        Segment(8.0, throttle=1.0, gear=4, label="4th gear pull"),
        cruise(90, 0.22),
        brake(7, 0.55, label="hard-ish stop"),
        idle(8),
        *CITY_DRIVE.segments[2:],
        cruise(120, 0.2),
        brake(6, 0.3),
        idle(10),
        park(10),
    ),
    tags=("phase1", "soak"),
)

DEMO_DRIVE = Scenario(
    "demo_drive",
    "Scripted ~3 minute drive that exercises every screen: cold start, city, 0-60 launch, "
    "3rd-gear WOT pull, highway with a radar alert, hard brake (event clip), park + summary.",
    (
        key_on(4),
        idle(6, "warm-up idle"),
        accelerate(8, 0.38, label="pull away"),
        cruise(8, 0.15, label="city cruise"),
        brake(5, 0.3, label="stop at light"),
        idle(4, "at light"),
        Segment(11.0, throttle=1.0, shift_up_rpm=6500, label="0-60 launch", marker="launch"),
        cruise(6, 0.14, label="settle"),
        Segment(3.0, throttle=0.12, gear=3, label="3rd gear roll", marker="radar_k"),
        Segment(7.0, throttle=1.0, gear=3, label="WOT 3rd", marker="wot_start"),
        Segment(3.0, throttle=0.0, gear=4, label="lift"),
        accelerate(10, 0.55, shift_up=4200, label="merge"),
        Segment(22.0, throttle=0.24, shift_up_rpm=2600, label="highway", marker="radar_ka"),
        Segment(5.0, throttle=0.24, shift_up_rpm=2600, label="highway 2", marker="radar_end"),
        Segment(6.0, throttle=0.0, brake=0.7, label="hard brake", marker="hard_brake"),
        cruise(8, 0.2, label="roll on"),
        brake(5, 0.3, label="exit"),
        idle(5, "arrive"),
        Segment(
            6.0, engine_on=False, ignition_on=True, label="key on, engine off", marker="trip_end"
        ),
        park(6),
    ),
    loop=True,
    pending_dtcs=("P0456",),
    tags=("demo",),
)

SCENARIOS: dict[str, Scenario] = {
    s.name: s
    for s in (
        COLD_START_IDLE,
        CITY_DRIVE,
        HIGHWAY_CRUISE,
        WOT_PULL_3RD,
        LAUNCH_0_60,
        HARD_BRAKE_FROM_70,
        ADAPTER_DROPOUT,
        OVERHEAT_WARNING,
        LONG_MIXED_TRIP,
        DEMO_DRIVE,
    )
}


def get_scenario(name: str) -> Scenario:
    try:
        return SCENARIOS[name]
    except KeyError as exc:
        raise KeyError(f"unknown scenario {name!r}; available: {', '.join(SCENARIOS)}") from exc


def with_loop(scenario: Scenario, loop: bool) -> Scenario:
    return replace(scenario, loop=loop)
