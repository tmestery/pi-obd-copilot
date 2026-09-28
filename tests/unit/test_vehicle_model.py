from __future__ import annotations

from pathlib import Path

import pytest

from gti_copilot.errors import ConfigError
from gti_copilot.vehicle.model import EngineSpec, VehicleSpec, load_vehicle


def test_tire_geometry(vehicle_spec: VehicleSpec) -> None:
    # 225/40R18 -> ~637 mm diameter, ~2.0 m circumference
    assert vehicle_spec.tire.diameter_m == pytest.approx(0.6372, abs=1e-3)
    assert vehicle_spec.tire.circumference_m == pytest.approx(2.002, abs=2e-3)


def test_speed_rpm_roundtrip_and_plausibility(vehicle_spec: VehicleSpec) -> None:
    for gear in vehicle_spec.gear_numbers:
        rpm = 3000.0
        speed = vehicle_spec.speed_kph_for(rpm, gear)
        assert vehicle_spec.rpm_for(speed, gear) == pytest.approx(rpm)
    # 3rd gear ~ 22 km/h per 1000 rpm on a MK7 GTI
    assert vehicle_spec.speed_kph_for(1000.0, 3) == pytest.approx(22.4, abs=1.5)
    # 6th gear at 120 km/h ~ 2500-2600 rpm
    assert 2300 < vehicle_spec.rpm_for(120.0, 6) < 2800


def test_unknown_gear_raises(vehicle_spec: VehicleSpec) -> None:
    with pytest.raises(ConfigError):
        vehicle_spec.gear_spec(9)


def test_torque_curve_interpolation() -> None:
    eng = EngineSpec(torque_curve_nm=[(1000, 100), (2000, 300), (3000, 200)])
    assert eng.torque_at(500) == 100
    assert eng.torque_at(1500) == 200
    assert eng.torque_at(2500) == 250
    assert eng.torque_at(9000) == 200


def test_load_errors(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="not found"):
        load_vehicle(tmp_path / "missing.yaml")
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "name: x\ntransmission: {gears: []}\ntire: {width_mm: 1, aspect_pct: 1, rim_in: 1}\n"
    )
    with pytest.raises(ConfigError, match="invalid vehicle spec"):
        load_vehicle(bad)
    dup = tmp_path / "dup.yaml"
    dup.write_text(
        "name: x\ntransmission:\n  gears:\n    - {gear: 1, ratio: 3, final_drive: 3}\n"
        "    - {gear: 1, ratio: 2, final_drive: 3}\n"
        "tire: {width_mm: 225, aspect_pct: 40, rim_in: 18}\n"
    )
    with pytest.raises(ConfigError, match="duplicate"):
        load_vehicle(dup)
    yaml_bad = tmp_path / "y.yaml"
    yaml_bad.write_text("a: [")
    with pytest.raises(ConfigError, match="invalid vehicle YAML"):
        load_vehicle(yaml_bad)
