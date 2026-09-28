"""Vehicle specification (gear ratios, tyre size, engine limits) loaded from YAML.

Used by the gear estimator, the shift light and the physics simulator. Numbers in the shipped
``config/vehicle/mk7-gti.yaml`` are approximations, see the note at the top of that file.
"""

from __future__ import annotations

import math
from itertools import pairwise
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

from gti_copilot.errors import ConfigError


class GearSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    gear: int = Field(ge=1, le=10)
    ratio: float = Field(gt=0)
    final_drive: float = Field(gt=0)

    @property
    def overall(self) -> float:
        return self.ratio * self.final_drive


class TransmissionSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["manual", "dsg"] = "manual"
    gears: list[GearSpec]
    shift_time_s: float = Field(0.45, ge=0)

    @field_validator("gears")
    @classmethod
    def _sorted_unique(cls, gears: list[GearSpec]) -> list[GearSpec]:
        if not gears:
            raise ValueError("at least one gear is required")
        numbers = [g.gear for g in gears]
        if len(set(numbers)) != len(numbers):
            raise ValueError("duplicate gear numbers")
        return sorted(gears, key=lambda g: g.gear)


class TireSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    width_mm: float = Field(gt=0)
    aspect_pct: float = Field(gt=0)
    rim_in: float = Field(gt=0)

    @property
    def diameter_m(self) -> float:
        sidewall_mm = self.width_mm * self.aspect_pct / 100.0
        return (self.rim_in * 25.4 + 2 * sidewall_mm) / 1000.0

    @property
    def circumference_m(self) -> float:
        return math.pi * self.diameter_m


class EngineSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str = "EA888 Gen3 2.0 TSI"
    displacement_l: float = Field(2.0, gt=0)
    cylinders: int = Field(4, ge=1)
    idle_rpm: float = Field(800, gt=0)
    redline_rpm: float = Field(6800, gt=0)
    max_rpm: float = Field(7000, gt=0)
    torque_curve_nm: list[tuple[float, float]] = Field(
        default_factory=lambda: [
            (1000.0, 180.0),
            (2000.0, 350.0),
            (4500.0, 350.0),
            (6500.0, 260.0),
            (7000.0, 200.0),
        ]
    )
    peak_boost_kpa: float = Field(105, ge=0)
    turbo_spool_tau_s: float = Field(0.6, gt=0)
    thermostat_c: float = Field(90, gt=0)
    warmup_tau_s: float = Field(240, gt=0)

    def torque_at(self, rpm: float) -> float:
        """Linear interpolation on the torque curve (Nm)."""
        pts = sorted(self.torque_curve_nm)
        if rpm <= pts[0][0]:
            return pts[0][1]
        for (r0, t0), (r1, t1) in pairwise(pts):
            if r0 <= rpm <= r1:
                f = (rpm - r0) / (r1 - r0) if r1 > r0 else 0.0
                return t0 + f * (t1 - t0)
        return pts[-1][1]


class GaugeRange(BaseModel):
    model_config = ConfigDict(extra="allow")
    min: float
    max: float
    warn: float | None = None
    redline: float | None = None
    low: float | None = None
    high: float | None = None


class PidHints(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected: list[int] = Field(default_factory=list)
    optional: list[int] = Field(default_factory=list)


class VehicleSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    engine: EngineSpec = Field(default_factory=EngineSpec)
    transmission: TransmissionSpec
    tire: TireSpec
    mass_kg: float = Field(1400, gt=0)
    drag_cd: float = Field(0.31, gt=0)
    frontal_area_m2: float = Field(2.2, gt=0)
    rolling_resistance: float = Field(0.012, ge=0)
    drivetrain_efficiency: float = Field(0.88, gt=0, le=1)
    gauges: dict[str, GaugeRange] = Field(default_factory=dict)
    pids: PidHints = Field(default_factory=PidHints)

    # --------------------------------------------------------------- kinematics
    def speed_kph_for(self, rpm: float, gear: int) -> float:
        """Road speed for a given engine RPM in a gear (no slip)."""
        g = self.gear_spec(gear)
        wheel_rpm = rpm / g.overall
        return wheel_rpm * self.tire.circumference_m * 60.0 / 1000.0

    def rpm_for(self, speed_kph: float, gear: int) -> float:
        g = self.gear_spec(gear)
        wheel_rpm = speed_kph * 1000.0 / 60.0 / self.tire.circumference_m
        return wheel_rpm * g.overall

    def gear_spec(self, gear: int) -> GearSpec:
        for g in self.transmission.gears:
            if g.gear == gear:
                return g
        raise ConfigError(f"gear {gear} not defined for {self.name}")

    @property
    def gear_numbers(self) -> list[int]:
        return [g.gear for g in self.transmission.gears]


def load_vehicle(path: Path) -> VehicleSpec:
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
    except FileNotFoundError as exc:
        raise ConfigError(f"vehicle file not found: {path}") from exc
    except yaml.YAMLError as exc:
        raise ConfigError(f"invalid vehicle YAML {path}: {exc}") from exc
    try:
        return VehicleSpec.model_validate(data)
    except ValueError as exc:
        raise ConfigError(f"invalid vehicle spec {path}: {exc}") from exc
