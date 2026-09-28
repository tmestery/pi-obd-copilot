"""Deterministic, seedable longitudinal vehicle + engine model for the simulator.

It is intentionally simple (a few first-order lags and a torque curve) but produces PID values
that look right on a gauge: turbo spool lag, MAP that sits in vacuum at idle and climbs to
~15 psi at wide-open throttle, coolant warm-up from cold, IAT heat soak, voltage that steps
from 12.4 V (engine off) to ~14 V (running), MAF that scales with air density and RPM.

Everything is in SI internally; the sim transport encodes to OBD bytes via ``pids.encode``.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from gti_copilot.vehicle.model import VehicleSpec

AIR_GAS_CONSTANT = 287.05  # J/(kg*K)
G = 9.80665
RHO_AIR = 1.2


@dataclass(slots=True)
class DriverInput:
    """What the scenario tells the car to do at a given instant."""

    throttle: float = 0.0  # 0..1
    brake: float = 0.0  # 0..1
    gear: int | None = None  # explicit gear; None = automatic shifting policy
    shift_up_rpm: float = 3000.0
    shift_down_rpm: float = 1400.0
    ignition_on: bool = True
    engine_on: bool = True
    clutch_in: bool = False


@dataclass(slots=True)
class VehicleState:
    t: float = 0.0
    ignition_on: bool = False
    engine_on: bool = False
    speed_ms: float = 0.0
    accel_ms2: float = 0.0
    rpm: float = 0.0
    gear: int = 0  # 0 = neutral
    throttle: float = 0.0
    brake: float = 0.0
    map_kpa: float = 101.0
    baro_kpa: float = 101.0
    boost_kpa: float = 0.0  # gauge (MAP - baro), may be negative
    coolant_c: float = 20.0
    oil_c: float = 20.0
    iat_c: float = 20.0
    ambient_c: float = 20.0
    volt_v: float = 12.4
    maf_gps: float = 0.0
    load_pct: float = 0.0
    timing_deg: float = 0.0
    stft_pct: float = 0.0
    ltft_pct: float = 2.3
    fuel_level_pct: float = 62.0
    fuel_rate_lph: float = 0.0
    fuel_used_l: float = 0.0
    odometer_m: float = 0.0
    shifting_until: float = -1.0

    @property
    def speed_kph(self) -> float:
        return self.speed_ms * 3.6

    @property
    def accel_g(self) -> float:
        return self.accel_ms2 / G


@dataclass
class VehicleModel:
    spec: VehicleSpec
    seed: int = 42
    ambient_c: float = 22.0
    baro_kpa: float = 99.0
    start_coolant_c: float | None = None
    thermostat_offset_c: float = 0.0  # e.g. +28 for an overheat scenario
    noise: bool = True
    state: VehicleState = field(init=False)
    _rng: random.Random = field(init=False, repr=False)
    _boost_state: float = field(init=False, default=0.0)
    _launch_slip_rpm: float = field(init=False, default=2200.0)

    def __post_init__(self) -> None:
        self._rng = random.Random(self.seed)
        cold = self.ambient_c if self.start_coolant_c is None else self.start_coolant_c
        self.state = VehicleState(
            coolant_c=cold,
            oil_c=cold,
            iat_c=self.ambient_c,
            ambient_c=self.ambient_c,
            baro_kpa=self.baro_kpa,
            map_kpa=self.baro_kpa,
        )

    # ------------------------------------------------------------------ helpers
    def _n(self, sigma: float) -> float:
        return self._rng.gauss(0.0, sigma) if self.noise and sigma > 0 else 0.0

    def _wheel_radius(self) -> float:
        return self.spec.tire.diameter_m / 2.0

    def _auto_gear(self, s: VehicleState, inp: DriverInput) -> int:
        gears = self.spec.gear_numbers
        if s.speed_ms < 0.3:
            return gears[0] if inp.throttle > 0.02 else s.gear or gears[0]
        gear = s.gear or gears[0]
        rpm_now = self.spec.rpm_for(s.speed_kph, gear)
        if rpm_now > inp.shift_up_rpm and gear < gears[-1]:
            return gear + 1
        if rpm_now < inp.shift_down_rpm and gear > gears[0]:
            return gear - 1
        return gear

    # ------------------------------------------------------------------ main step
    def step(self, dt: float, inp: DriverInput) -> VehicleState:
        s = self.state
        spec = self.spec
        eng = spec.engine
        s.t += dt
        s.ignition_on = inp.ignition_on
        s.engine_on = inp.engine_on and inp.ignition_on
        s.brake = max(0.0, min(1.0, inp.brake))

        # -------------------------------------------------- gear selection / shifting
        target_gear = inp.gear if inp.gear is not None else self._auto_gear(s, inp)
        if inp.clutch_in or not s.engine_on:
            target_gear = 0 if inp.clutch_in else target_gear
        if target_gear != s.gear and s.speed_ms > 0.3 and s.engine_on and s.gear != 0:
            s.shifting_until = s.t + spec.transmission.shift_time_s
        s.gear = target_gear
        shifting = s.t < s.shifting_until
        throttle = 0.0 if shifting else max(0.0, min(1.0, inp.throttle))
        if not s.engine_on:
            throttle = 0.0
        s.throttle = throttle

        # -------------------------------------------------- engine speed
        in_gear = s.gear > 0 and not shifting and not inp.clutch_in and s.engine_on
        if not s.engine_on:
            s.rpm = max(0.0, s.rpm - 3000.0 * dt)
        elif in_gear:
            road_rpm = spec.rpm_for(s.speed_kph, s.gear)
            if s.gear == spec.gear_numbers[0] and road_rpm < self._launch_slip_rpm:
                # clutch slip / torque converter behaviour on launch
                s.rpm = max(eng.idle_rpm, self._launch_slip_rpm * max(throttle, 0.35))
            else:
                s.rpm = max(eng.idle_rpm * 0.95, road_rpm)
        else:
            free_target = eng.idle_rpm + throttle * (eng.redline_rpm - eng.idle_rpm)
            s.rpm += (free_target - s.rpm) * min(1.0, dt / 0.35)
        s.rpm = min(s.rpm, eng.max_rpm)

        # -------------------------------------------------- boost / MAP
        if s.engine_on:
            spool = _smoothstep((s.rpm - 1400.0) / 1300.0)  # 0 @1400 -> 1 @2700
            taper = 1.0 - 0.35 * _smoothstep((s.rpm - 4800.0) / 1800.0)
            throttle_factor = _smoothstep((throttle - 0.25) / 0.6)
            boost_target = eng.peak_boost_kpa * spool * taper * throttle_factor
            if not in_gear:
                boost_target *= 0.25  # free-revving builds little boost
        else:
            boost_target = 0.0
        tau = eng.turbo_spool_tau_s if boost_target > self._boost_state else 0.25
        self._boost_state += (boost_target - self._boost_state) * min(1.0, dt / tau)
        if s.engine_on:
            vacuum_map = 32.0 + 45.0 * throttle  # closed throttle ~32 kPa, part throttle rises
            map_kpa = max(vacuum_map, s.baro_kpa * throttle_factor_naive(throttle))
            map_kpa = min(s.baro_kpa, map_kpa) + self._boost_state
        else:
            map_kpa = s.baro_kpa
        s.map_kpa = map_kpa + self._n(0.6)
        s.boost_kpa = s.map_kpa - s.baro_kpa

        # -------------------------------------------------- torque, forces, motion
        torque_available = eng.torque_at(s.rpm) if s.engine_on else 0.0
        boost_ratio = max(0.0, s.map_kpa) / (s.baro_kpa + eng.peak_boost_kpa)
        torque = torque_available * throttle * (0.45 + 0.55 * boost_ratio)
        if s.engine_on and throttle < 0.03 and in_gear:
            torque = -0.08 * eng.torque_at(s.rpm)  # engine braking
        f_wheel = 0.0
        if in_gear:
            overall = spec.gear_spec(s.gear).overall
            f_wheel = torque * overall * spec.drivetrain_efficiency / self._wheel_radius()
            # traction limit ~1.1 g
            f_wheel = max(-1.1 * spec.mass_kg * G, min(1.1 * spec.mass_kg * G, f_wheel))
        v = s.speed_ms
        f_drag = 0.5 * RHO_AIR * spec.drag_cd * spec.frontal_area_m2 * v * v
        f_roll = spec.rolling_resistance * spec.mass_kg * G if v > 0.05 else 0.0
        f_brake = s.brake * 1.05 * spec.mass_kg * G
        f_net = f_wheel - f_drag - f_roll - f_brake
        a = f_net / spec.mass_kg
        v_new = v + a * dt
        if v_new < 0.0:
            v_new = 0.0
            a = (v_new - v) / dt if dt > 0 else 0.0
        s.accel_ms2 = a
        s.speed_ms = v_new
        s.odometer_m += v_new * dt

        # -------------------------------------------------- air, load, fuel
        if s.engine_on:
            density = s.map_kpa * 1000.0 / (AIR_GAS_CONSTANT * (s.iat_c + 273.15))
            ve = 0.86
            maf = (s.rpm / 120.0) * (eng.displacement_l / 1000.0) * density * ve * 1000.0
            s.maf_gps = max(0.5, maf + self._n(0.3))
            s.load_pct = max(3.0, min(100.0, 100.0 * s.map_kpa / (s.baro_kpa + eng.peak_boost_kpa)))
            s.timing_deg = max(-5.0, min(35.0, 8.0 + s.rpm / 300.0 - max(0.0, s.boost_kpa) * 0.12))
            fuel_gps = s.maf_gps / 14.7
            s.fuel_rate_lph = fuel_gps * 3600.0 / 740.0
            s.stft_pct = 0.9 * s.stft_pct + self._n(1.2)
            s.ltft_pct = 2.3 + self._n(0.05)
        else:
            s.maf_gps = 0.0
            s.load_pct = 0.0
            s.timing_deg = 0.0
            s.fuel_rate_lph = 0.0
        s.fuel_used_l += s.fuel_rate_lph * dt / 3600.0
        s.fuel_level_pct = max(0.0, 62.0 - s.fuel_used_l / 50.0 * 100.0)

        # -------------------------------------------------- thermals
        thermostat = eng.thermostat_c + self.thermostat_offset_c
        if s.engine_on:
            heat = 1.0 + 0.6 * (s.load_pct / 100.0)
            target = thermostat + 6.0 * (s.load_pct / 100.0) * (1.0 if v < 5 else 0.3)
            s.coolant_c += (target - s.coolant_c) * min(1.0, dt * heat / eng.warmup_tau_s)
            s.oil_c += (thermostat + 8.0 - s.oil_c) * min(1.0, dt / (eng.warmup_tau_s * 1.6))
            soak = 12.0 if v < 3.0 else 4.0
            iat_target = s.ambient_c + soak + max(0.0, s.boost_kpa) * 0.18
            s.iat_c += (iat_target - s.iat_c) * min(1.0, dt / 20.0)
        else:
            s.coolant_c += (s.ambient_c - s.coolant_c) * min(1.0, dt / 2400.0)
            s.oil_c += (s.ambient_c - s.oil_c) * min(1.0, dt / 2400.0)
            s.iat_c += (s.ambient_c + 6.0 - s.iat_c) * min(1.0, dt / 120.0)

        # -------------------------------------------------- electrical
        if s.engine_on:
            volt_target = 14.15 - 0.25 * (s.load_pct / 100.0)
        else:
            volt_target = 12.45 if s.ignition_on else 12.6
        s.volt_v += (volt_target - s.volt_v) * min(1.0, dt / 0.8)
        s.volt_v += self._n(0.01)
        return s


def throttle_factor_naive(throttle: float) -> float:
    """Fraction of barometric pressure reached in the manifold for a throttle opening."""
    return 0.32 + 0.68 * _smoothstep(throttle / 0.7)


def _smoothstep(x: float) -> float:
    x = max(0.0, min(1.0, x))
    return x * x * (3.0 - 2.0 * x)


def kph(ms: float) -> float:
    return ms * 3.6


def ms(kph_value: float) -> float:
    return kph_value / 3.6


def energy_check(model: VehicleModel) -> float:
    """Kinetic energy (J) - handy in tests to assert braking dissipates energy."""
    return 0.5 * model.spec.mass_kg * model.state.speed_ms**2


__all__ = [
    "DriverInput",
    "VehicleModel",
    "VehicleState",
    "energy_check",
    "kph",
    "ms",
]
