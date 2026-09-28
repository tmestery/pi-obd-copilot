"""Shared fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest

from gti_copilot.vehicle.model import VehicleSpec, load_vehicle

REPO_ROOT = Path(__file__).resolve().parent.parent
VEHICLE_YAML = REPO_ROOT / "config" / "vehicle" / "mk7-gti.yaml"
EXAMPLE_CONFIG = REPO_ROOT / "config" / "gti-copilot.example.yaml"


def load_default_vehicle() -> VehicleSpec:
    return load_vehicle(VEHICLE_YAML)


@pytest.fixture(scope="session")
def vehicle_spec() -> VehicleSpec:
    return load_default_vehicle()


@pytest.fixture
def example_config_path() -> Path:
    return EXAMPLE_CONFIG
