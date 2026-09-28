"""Derived metrics computed from raw PID values.

Pure functions and small stateful helpers, all unit-tested. Nothing here touches I/O.
"""

from __future__ import annotations

import math
import statistics
from collections import deque
from dataclasses import dataclass, field
from typing import Literal

from gti_copilot.units import (
    GASOLINE_DENSITY_KG_PER_L,
    STANDARD_AFR_GASOLINE,
    kpa_to_inhg,
    kpa_to_psi,
    kph_to_ms,
    ms2_to_g,
)
from gti_copilot.vehicle.model import VehicleSpec

ShiftState = Literal["none", "warn", "shift"]
STANDARD_BARO_KPA = 101.325


# --------------------------------------------------------------------------- boost
def boost_kpa(map_kpa: float, baro_kpa: float) -> float:
    """Gauge boost (positive) or vacuum (negative) in kPa."""
    return map_kpa - baro_kpa


@dataclass
class BoostReading:
    kpa: float

    @property
    def psi(self) -> float:
        return kpa_to_psi(self.kpa)

    @property
    def bar(self) -> float:
        return self.kpa / 100.0

    @property
    def is_vacuum(self) -> bool:
        return self.kpa < 0

    @property
    def vacuum_inhg(self) -> float:
        """Vacuum as a positive inHg figure (0 when in boost)."""
        return kpa_to_inhg(-self.kpa) if self.kpa < 0 else 0.0


class BaroEstimator:
    """Barometric pressure source.

    Prefers PID 0x33 when the ECU supports it. Otherwise collects MAP samples while the engine
    is off (RPM == 0, key on) and uses their median. Falls back to standard atmosphere until at
    least ``min_samples`` engine-off samples exist. Once the engine is running the estimate is
    frozen for the rest of the drive (MAP is no longer atmospheric).
    """

    def __init__(self, min_samples: int = 3, max_samples: int = 50) -> None:
        self._min = min_samples
        self._samples: deque[float] = deque(maxlen=max_samples)
        self._pid_value: float | None = None
        self._frozen: float | None = None

    def observe_baro_pid(self, baro_kpa: float) -> None:
        if 50.0 <= baro_kpa <= 120.0:
            self._pid_value = baro_kpa

    def observe_map(self, map_kpa: float, rpm: float) -> None:
        if rpm <= 0 and 50.0 <= map_kpa <= 120.0:
            self._samples.append(map_kpa)
        elif rpm > 0 and self._frozen is None and len(self._samples) >= self._min:
            self._frozen = statistics.median(self._samples)

    @property
    def source(self) -> Literal["pid", "map_engine_off", "standard"]:
        if self._pid_value is not None:
            return "pid"
        if self._frozen is not None or len(self._samples) >= self._min:
            return "map_engine_off"
        return "standard"

    def value(self) -> float:
        if self._pid_value is not None:
            return self._pid_value
        if self._frozen is not None:
            return self._frozen
        if len(self._samples) >= self._min:
            return statistics.median(self._samples)
        return STANDARD_BARO_KPA


# --------------------------------------------------------------------------- smoothing / peak hold
class Ema:
    """Exponential moving average with a time constant, robust to irregular sampling."""

    def __init__(self, tau_s: float) -> None:
        if tau_s <= 0:
            raise ValueError("tau_s must be > 0")
        self.tau = tau_s
        self.value: float | None = None
        self._last_t: float | None = None

    def update(self, x: float, t: float) -> float:
        if self.value is None or self._last_t is None or t < self._last_t:
            self.value = x
        else:
            dt = t - self._last_t
            alpha = 1.0 - math.exp(-dt / self.tau) if dt > 0 else 0.0
            self.value += alpha * (x - self.value)
        self._last_t = t
        return self.value

    def reset(self) -> None:
        self.value = None
        self._last_t = None


class PeakHold:
    """Track a maximum, hold it for ``hold_s`` seconds, then decay linearly at ``decay_per_s``."""

    def __init__(self, hold_s: float = 3.0, decay_per_s: float = 0.0, floor: float = -math.inf):
        self.hold_s = hold_s
        self.decay_per_s = decay_per_s
        self.floor = floor
        self.peak: float = floor
        self.session_max: float = floor
        self._peak_t: float | None = None
        self._last_t: float | None = None

    def update(self, x: float, t: float) -> float:
        if self._last_t is not None and self._peak_t is not None and self.decay_per_s > 0:
            decay_start = max(self._last_t, self._peak_t + self.hold_s)
            if t > decay_start:
                self.peak = max(self.floor, self.peak - self.decay_per_s * (t - decay_start))
        self._last_t = t
        if x >= self.peak:
            self.peak = x
            self._peak_t = t
        self.session_max = max(self.session_max, x)
        return self.peak

    def reset(self) -> None:
        self.peak = self.floor
        self.session_max = self.floor
        self._peak_t = None
        self._last_t = None


# --------------------------------------------------------------------------- fuel
def fuel_rate_lph_from_maf(
    maf_gps: float,
    afr: float = STANDARD_AFR_GASOLINE,
    density_kg_per_l: float = GASOLINE_DENSITY_KG_PER_L,
) -> float:
    """Fuel flow (L/h) from mass air flow assuming stoichiometric combustion."""
    if maf_gps <= 0:
        return 0.0
    fuel_gps = maf_gps / afr
    return fuel_gps * 3600.0 / (density_kg_per_l * 1000.0)


@dataclass
class TripFuelAccumulator:
    """Integrates fuel used and distance so a trip average economy can be computed."""

    fuel_l: float = 0.0
    distance_m: float = 0.0
    _last_t: float | None = field(default=None, repr=False)

    def update(self, fuel_lph: float, speed_kph: float, t: float) -> None:
        if self._last_t is not None and t > self._last_t:
            dt = t - self._last_t
            self.fuel_l += fuel_lph * dt / 3600.0
            self.distance_m += kph_to_ms(speed_kph) * dt
        self._last_t = t

    @property
    def avg_l_per_100km(self) -> float | None:
        if self.distance_m < 100:
            return None
        return self.fuel_l / (self.distance_m / 1000.0) * 100.0

    @property
    def avg_mpg(self) -> float | None:
        if self.fuel_l <= 1e-6 or self.distance_m < 100:
            return None
        miles = self.distance_m / 1609.344
        gallons = self.fuel_l / 3.785411784
        return miles / gallons


# --------------------------------------------------------------------------- gear
def estimate_gear(
    rpm: float,
    speed_kph: float,
    spec: VehicleSpec,
    tolerance: float = 0.12,
    min_speed_kph: float = 3.0,
) -> int | None:
    """Pick the gear whose overall ratio best matches RPM/speed; ``None`` if clutch/neutral."""
    if speed_kph < min_speed_kph or rpm < spec.engine.idle_rpm * 0.8:
        return None
    best: tuple[float, int] | None = None
    for gear in spec.gear_numbers:
        expected_rpm = spec.rpm_for(speed_kph, gear)
        err = abs(expected_rpm - rpm) / expected_rpm
        if best is None or err < best[0]:
            best = (err, gear)
    if best is None or best[0] > tolerance:
        return None
    return best[1]


def shift_state(rpm: float, warn_rpm: float, redline_rpm: float) -> ShiftState:
    if rpm >= redline_rpm:
        return "shift"
    if rpm >= warn_rpm:
        return "warn"
    return "none"


# --------------------------------------------------------------------------- acceleration
class Accelerometer:
    """Longitudinal acceleration (g) from the speed derivative with low-pass filtering."""

    def __init__(self, tau_s: float = 0.4, max_dt_s: float = 2.0) -> None:
        self._ema = Ema(tau_s)
        self._last_speed_ms: float | None = None
        self._last_t: float | None = None
        self._max_dt = max_dt_s
        self.g: float = 0.0

    def update(self, speed_kph: float, t: float) -> float:
        v = kph_to_ms(speed_kph)
        if self._last_t is not None and self._last_speed_ms is not None:
            dt = t - self._last_t
            if 0 < dt <= self._max_dt:
                raw = (v - self._last_speed_ms) / dt
                self.g = ms2_to_g(self._ema.update(raw, t))
            elif dt > self._max_dt:
                self._ema.reset()
                self.g = 0.0
        self._last_speed_ms = v
        self._last_t = t
        return self.g

    def reset(self) -> None:
        self._ema.reset()
        self._last_speed_ms = None
        self._last_t = None
        self.g = 0.0
