from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from gti_copilot import units as u


def test_pressure_conversions() -> None:
    assert u.kpa_to_psi(6.894757293168) == pytest.approx(1.0)
    assert u.psi_to_kpa(u.kpa_to_psi(55.0)) == pytest.approx(55.0)
    assert u.kpa_to_bar(100.0) == 1.0
    assert u.bar_to_kpa(1.5) == 150.0
    assert u.kpa_to_inhg(3.386389) == pytest.approx(1.0)
    assert u.convert_pressure(100.0, "kpa") == 100.0
    assert u.convert_pressure(100.0, "bar") == 1.0
    assert u.convert_pressure(100.0, "psi") == pytest.approx(14.5038, abs=1e-3)


def test_speed_and_temperature() -> None:
    assert u.kph_to_mph(160.9344) == pytest.approx(100.0)
    assert u.mph_to_kph(60.0) == pytest.approx(96.56064)
    assert u.kph_to_ms(36.0) == 10.0
    assert u.ms_to_kph(10.0) == 36.0
    assert u.c_to_f(100.0) == 212.0
    assert u.f_to_c(32.0) == 0.0
    assert u.convert_speed(100.0, "kph") == 100.0
    assert u.convert_temperature(0.0, "f") == 32.0
    assert u.convert_temperature(0.0, "c") == 0.0


def test_distance_and_volume() -> None:
    assert u.m_to_mi(1609.344) == pytest.approx(1.0)
    assert u.m_to_km(2500) == 2.5
    assert u.convert_distance(1000.0, "km") == 1.0
    assert u.convert_distance(1609.344, "mi") == pytest.approx(1.0)
    assert u.l_to_gal(3.785411784) == pytest.approx(1.0)
    assert u.gal_to_l(1.0) == pytest.approx(3.785411784)


def test_economy() -> None:
    # 60 mph burning 2 gal/h -> 30 mpg
    mpg = u.mpg_from_kph_lph(96.56064, u.gal_to_l(2.0))
    assert mpg == pytest.approx(30.0)
    assert u.mpg_from_kph_lph(50.0, 0.0) is None
    assert u.l_per_100km_from_kph_lph(100.0, 8.0) == pytest.approx(8.0)
    assert u.l_per_100km_from_kph_lph(0.0, 8.0) is None


def test_acceleration() -> None:
    assert u.ms2_to_g(9.80665) == 1.0
    assert u.g_to_ms2(0.5) == pytest.approx(4.903325)


def test_unit_system_presets_and_formatting() -> None:
    imp = u.UnitSystem.imperial()
    met = u.UnitSystem.metric()
    assert imp.pressure_out(68.94757293168) == (pytest.approx(10.0), "psi")
    assert met.pressure_out(150.0) == (1.5, "bar")
    assert u.UnitSystem(pressure="kpa").pressure_out(12.0) == (12.0, "KPA")
    assert imp.speed_out(160.9344)[1] == "mph"
    assert met.speed_out(50.0) == (50.0, "km/h")
    assert imp.temperature_out(100.0) == (212.0, "°F")
    assert met.temperature_out(90.0) == (90.0, "°C")
    assert imp.distance_out(1609.344) == (pytest.approx(1.0), "mi")
    assert met.distance_out(1000.0) == (1.0, "km")
    assert imp.economy_out(96.56064, u.gal_to_l(2.0)) == (pytest.approx(30.0), "mpg")
    assert met.economy_out(100.0, 8.0) == (pytest.approx(8.0), "L/100km")
    assert u.fmt(None) == "—"
    assert u.fmt(3.14159, 2, "psi") == "3.14 psi"
    assert u.fmt(42.0) == "42"


@given(st.floats(min_value=-500, max_value=500, allow_nan=False))
def test_roundtrips(x: float) -> None:
    assert u.psi_to_kpa(u.kpa_to_psi(x)) == pytest.approx(x, abs=1e-9)
    assert u.mph_to_kph(u.kph_to_mph(x)) == pytest.approx(x, abs=1e-9)
    assert u.f_to_c(u.c_to_f(x)) == pytest.approx(x, abs=1e-9)
    assert u.gal_to_l(u.l_to_gal(x)) == pytest.approx(x, abs=1e-9)
