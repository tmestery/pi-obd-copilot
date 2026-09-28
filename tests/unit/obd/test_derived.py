from __future__ import annotations

import math

import pytest
from hypothesis import given
from hypothesis import strategies as st

from gti_copilot.obd.derived import (
    STANDARD_BARO_KPA,
    Accelerometer,
    BaroEstimator,
    BoostReading,
    Ema,
    PeakHold,
    TripFuelAccumulator,
    boost_kpa,
    estimate_gear,
    fuel_rate_lph_from_maf,
    shift_state,
)
from gti_copilot.vehicle.model import VehicleSpec


# --------------------------------------------------------------------------- boost
def test_boost_positive_and_vacuum() -> None:
    assert boost_kpa(162.3, 101.0) == pytest.approx(61.3)
    r = BoostReading(boost_kpa(40.0, 100.0))
    assert r.is_vacuum
    assert r.vacuum_inhg == pytest.approx(60 / 3.386389, rel=1e-4)
    assert BoostReading(103.4).psi == pytest.approx(15.0, abs=0.01)
    assert BoostReading(100.0).bar == pytest.approx(1.0)
    assert BoostReading(10.0).vacuum_inhg == 0.0


def test_baro_estimator_prefers_pid() -> None:
    b = BaroEstimator()
    assert b.value() == STANDARD_BARO_KPA
    assert b.source == "standard"
    b.observe_baro_pid(98.0)
    assert b.value() == 98.0
    assert b.source == "pid"
    b.observe_baro_pid(300.0)  # implausible, ignored
    assert b.value() == 98.0


def test_baro_estimator_uses_engine_off_map_median_and_freezes() -> None:
    b = BaroEstimator(min_samples=3)
    for m in (99.0, 100.0, 101.0, 250.0):  # 250 is out of plausible range
        b.observe_map(m, rpm=0)
    assert b.source == "map_engine_off"
    assert b.value() == 100.0
    b.observe_map(160.0, rpm=3000)  # engine running: freeze
    b.observe_map(30.0, rpm=0)  # a later engine-off sample must not change the frozen value
    assert b.value() == 100.0


def test_baro_estimator_insufficient_samples_falls_back_to_standard() -> None:
    b = BaroEstimator(min_samples=3)
    b.observe_map(99.0, rpm=0)
    assert b.value() == STANDARD_BARO_KPA


# --------------------------------------------------------------------------- ema / peak hold
def test_ema_converges_and_handles_time_jumps() -> None:
    e = Ema(tau_s=1.0)
    assert e.update(10.0, 0.0) == 10.0
    v = e.update(20.0, 1.0)
    assert 10 < v < 20
    assert v == pytest.approx(10 + (1 - math.exp(-1)) * 10)
    e.update(5.0, 0.5)  # time went backwards: resets to the sample
    assert e.value == 5.0
    with pytest.raises(ValueError, match="tau_s"):
        Ema(0)


def test_peak_hold_holds_then_decays() -> None:
    p = PeakHold(hold_s=1.0, decay_per_s=10.0, floor=0.0)
    p.update(50.0, 0.0)
    assert p.update(10.0, 0.5) == 50.0  # within hold window
    assert p.update(10.0, 1.5) == pytest.approx(45.0)  # decay only counts time past the hold
    assert p.update(10.0, 2.5) == pytest.approx(35.0)
    assert p.update(60.0, 3.0) == 60.0
    assert p.session_max == 60.0
    p.reset()
    assert p.peak == 0.0


def test_peak_hold_without_decay_is_session_max() -> None:
    p = PeakHold()
    for t, x in enumerate([1.0, 5.0, 3.0, 2.0]):
        p.update(x, float(t))
    assert p.peak == 5.0


# --------------------------------------------------------------------------- fuel
def test_fuel_rate_from_maf_matches_hand_calc() -> None:
    # 20 g/s air -> 1.36 g/s fuel -> 4898 g/h -> 6.62 L/h at 0.74 kg/L
    assert fuel_rate_lph_from_maf(20.0) == pytest.approx(20 / 14.7 * 3600 / 740, rel=1e-6)
    assert fuel_rate_lph_from_maf(0.0) == 0.0
    assert fuel_rate_lph_from_maf(-3.0) == 0.0


def test_trip_fuel_accumulator_average() -> None:
    acc = TripFuelAccumulator()
    assert acc.avg_mpg is None
    # 100 km/h for 1 hour at 8 L/h -> 8 L/100km
    acc.update(8.0, 100.0, 0.0)
    acc.update(8.0, 100.0, 3600.0)
    assert acc.distance_m == pytest.approx(100_000.0)
    assert acc.fuel_l == pytest.approx(8.0)
    assert acc.avg_l_per_100km == pytest.approx(8.0)
    assert acc.avg_mpg == pytest.approx(29.4, abs=0.1)


# --------------------------------------------------------------------------- gear
@pytest.fixture
def spec(vehicle_spec: VehicleSpec) -> VehicleSpec:
    return vehicle_spec


def test_estimate_gear_recovers_each_gear(spec: VehicleSpec) -> None:
    for gear in spec.gear_numbers:
        speed = spec.speed_kph_for(3000.0, gear)
        assert estimate_gear(3000.0, speed, spec) == gear


def test_estimate_gear_none_when_stationary_or_clutch_in(spec: VehicleSpec) -> None:
    assert estimate_gear(800.0, 0.0, spec) is None
    assert estimate_gear(300.0, 50.0, spec) is None  # rpm below idle
    # Mismatch far outside any ratio (clutch slipping)
    assert estimate_gear(6500.0, 5.0, spec) is None


@given(st.integers(min_value=1, max_value=6), st.floats(min_value=1500, max_value=6500))
def test_estimate_gear_property(gear: int, rpm: float) -> None:
    from tests.conftest import load_default_vehicle

    spec = load_default_vehicle()
    speed = spec.speed_kph_for(rpm, gear)
    if speed >= 3.0:
        assert estimate_gear(rpm, speed, spec) == gear


def test_shift_state() -> None:
    assert shift_state(3000, 6000, 6500) == "none"
    assert shift_state(6000, 6000, 6500) == "warn"
    assert shift_state(6600, 6000, 6500) == "shift"


# --------------------------------------------------------------------------- acceleration
def test_accelerometer_constant_accel() -> None:
    a = Accelerometer(tau_s=0.01)
    # 0 -> 96.56 km/h (60 mph) in 5 s ~= 0.547 g
    t = 0.0
    while t <= 5.0:
        a.update(96.56 * t / 5.0, t)
        t += 0.1
    assert a.g == pytest.approx(0.547, abs=0.02)


def test_accelerometer_braking_negative_and_resets_after_gap() -> None:
    a = Accelerometer(tau_s=0.01)
    a.update(100.0, 0.0)
    a.update(80.0, 1.0)
    assert a.g < -0.5
    a.update(80.0, 10.0)  # big gap: reset
    assert a.g == 0.0
    a.reset()
    assert a.g == 0.0
