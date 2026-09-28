"""Unit conversions and display formatting.

All internal values are SI-ish (kPa, km/h, degC, litres, metres, volts). Conversion to the
driver's preferred units happens at the display boundary (UI / summaries).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

KPA_PER_PSI = 6.894757293168
KPA_PER_BAR = 100.0
KPA_PER_INHG = 3.386389
KPH_PER_MPH = 1.609344
METERS_PER_MILE = 1609.344
LITERS_PER_US_GALLON = 3.785411784
GASOLINE_DENSITY_KG_PER_L = 0.74
GASOLINE_DENSITY_LB_PER_GAL = 6.17
STANDARD_AFR_GASOLINE = 14.7
G_MS2 = 9.80665

PressureUnit = Literal["psi", "bar", "kpa"]
SpeedUnit = Literal["mph", "kph"]
TemperatureUnit = Literal["f", "c"]
DistanceUnit = Literal["mi", "km"]
EconomyUnit = Literal["mpg", "l_per_100km"]


# --------------------------------------------------------------------------- pressure
def kpa_to_psi(kpa: float) -> float:
    return kpa / KPA_PER_PSI


def psi_to_kpa(psi: float) -> float:
    return psi * KPA_PER_PSI


def kpa_to_bar(kpa: float) -> float:
    return kpa / KPA_PER_BAR


def bar_to_kpa(bar: float) -> float:
    return bar * KPA_PER_BAR


def kpa_to_inhg(kpa: float) -> float:
    return kpa / KPA_PER_INHG


def convert_pressure(kpa: float, unit: PressureUnit) -> float:
    if unit == "psi":
        return kpa_to_psi(kpa)
    if unit == "bar":
        return kpa_to_bar(kpa)
    return kpa


# --------------------------------------------------------------------------- speed
def kph_to_mph(kph: float) -> float:
    return kph / KPH_PER_MPH


def mph_to_kph(mph: float) -> float:
    return mph * KPH_PER_MPH


def kph_to_ms(kph: float) -> float:
    return kph / 3.6


def ms_to_kph(ms: float) -> float:
    return ms * 3.6


def convert_speed(kph: float, unit: SpeedUnit) -> float:
    return kph_to_mph(kph) if unit == "mph" else kph


# --------------------------------------------------------------------------- temperature
def c_to_f(c: float) -> float:
    return c * 9.0 / 5.0 + 32.0


def f_to_c(f: float) -> float:
    return (f - 32.0) * 5.0 / 9.0


def convert_temperature(c: float, unit: TemperatureUnit) -> float:
    return c_to_f(c) if unit == "f" else c


# --------------------------------------------------------------------------- distance / volume
def m_to_mi(m: float) -> float:
    return m / METERS_PER_MILE


def m_to_km(m: float) -> float:
    return m / 1000.0


def convert_distance(m: float, unit: DistanceUnit) -> float:
    return m_to_mi(m) if unit == "mi" else m_to_km(m)


def l_to_gal(liters: float) -> float:
    return liters / LITERS_PER_US_GALLON


def gal_to_l(gal: float) -> float:
    return gal * LITERS_PER_US_GALLON


# --------------------------------------------------------------------------- economy
def mpg_from_kph_lph(speed_kph: float, fuel_lph: float) -> float | None:
    """US miles per gallon from speed and fuel flow. ``None`` when fuel flow is ~0."""
    if fuel_lph <= 1e-6:
        return None
    miles_per_hour = kph_to_mph(speed_kph)
    gallons_per_hour = l_to_gal(fuel_lph)
    return miles_per_hour / gallons_per_hour


def l_per_100km_from_kph_lph(speed_kph: float, fuel_lph: float) -> float | None:
    """Litres per 100 km. ``None`` when stationary (would be infinite)."""
    if speed_kph <= 0.5:
        return None
    return fuel_lph / speed_kph * 100.0


# --------------------------------------------------------------------------- acceleration
def ms2_to_g(ms2: float) -> float:
    return ms2 / G_MS2


def g_to_ms2(g: float) -> float:
    return g * G_MS2


# --------------------------------------------------------------------------- unit system
@dataclass(frozen=True)
class UnitSystem:
    """Display preferences. ``imperial()`` and ``metric()`` give the two presets."""

    pressure: PressureUnit = "psi"
    speed: SpeedUnit = "mph"
    temperature: TemperatureUnit = "f"
    distance: DistanceUnit = "mi"
    economy: EconomyUnit = "mpg"

    @classmethod
    def imperial(cls) -> UnitSystem:
        return cls()

    @classmethod
    def metric(cls) -> UnitSystem:
        return cls(
            pressure="bar", speed="kph", temperature="c", distance="km", economy="l_per_100km"
        )

    # Formatting helpers return (value, unit_label) tuples to keep UI code declarative.
    def pressure_out(self, kpa: float) -> tuple[float, str]:
        return convert_pressure(kpa, self.pressure), self.pressure.upper() if (
            self.pressure == "kpa"
        ) else self.pressure

    def speed_out(self, kph: float) -> tuple[float, str]:
        return convert_speed(kph, self.speed), "mph" if self.speed == "mph" else "km/h"

    def temperature_out(self, c: float) -> tuple[float, str]:
        return convert_temperature(c, self.temperature), "°F" if self.temperature == "f" else "°C"

    def distance_out(self, m: float) -> tuple[float, str]:
        return convert_distance(m, self.distance), self.distance

    def economy_out(self, speed_kph: float, fuel_lph: float) -> tuple[float | None, str]:
        if self.economy == "mpg":
            return mpg_from_kph_lph(speed_kph, fuel_lph), "mpg"
        return l_per_100km_from_kph_lph(speed_kph, fuel_lph), "L/100km"


def fmt(value: float | None, digits: int = 0, unit: str = "") -> str:
    """Human formatting with a dash for missing values."""
    if value is None:
        return "—"
    text = f"{value:.{digits}f}"
    return f"{text} {unit}".strip() if unit else text
