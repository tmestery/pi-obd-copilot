from __future__ import annotations

from pathlib import Path

import pytest

from gti_copilot.config import (
    AppConfig,
    config_json_schema,
    default_config_dir,
    dump_config,
    env_overrides,
    load_config,
)
from gti_copilot.errors import ConfigError


def test_defaults_are_sim_and_local_only() -> None:
    cfg = AppConfig()
    assert cfg.mode == "sim"
    assert cfg.api.host == "127.0.0.1"
    assert cfg.obd.transport == "sim"
    assert cfg.power.dry_run is True
    assert cfg.units.resolved()["pressure"] == "psi"


def test_example_config_loads_and_roundtrips(example_config_path: Path) -> None:
    cfg = load_config(example_config_path, env={})
    assert cfg.mode == "sim"
    assert cfg.ui.thresholds.shift_redline_rpm == 6500
    dumped = dump_config(cfg)
    assert "shift_redline_rpm: 6500" in dumped
    assert cfg.resolve_vehicle_path().exists()


def test_env_overrides_nested_and_typed() -> None:
    env = {
        "GTI_OBD__DEVICE": "/dev/ttyUSB0",
        "GTI_API__PORT": "9000",
        "GTI_SIM__TIME_SCALE": "2.5",
        "GTI_POWER__DRY_RUN": "false",
        "GTI_API__CORS_ORIGINS": "[http://a, http://b]",
        "GTI_": "ignored",
        "OTHER": "ignored",
    }
    assert env_overrides(env) == {
        "obd": {"device": "/dev/ttyUSB0"},
        "api": {"port": 9000, "cors_origins": ["http://a", "http://b"]},
        "sim": {"time_scale": 2.5},
        "power": {"dry_run": False},
    }
    cfg = load_config(None, env=env)
    assert cfg.obd.device == "/dev/ttyUSB0"
    assert cfg.api.port == 9000
    assert cfg.power.dry_run is False


def test_precedence_file_lt_env_lt_overrides(tmp_path: Path) -> None:
    f = tmp_path / "c.yaml"
    f.write_text("api:\n  port: 1000\nobd:\n  device: /dev/file\n")
    cfg = load_config(f, env={"GTI_API__PORT": "2000"}, overrides={"api": {"port": 3000}})
    assert cfg.api.port == 3000
    assert cfg.obd.device == "/dev/file"


def test_invalid_values_raise_config_error(tmp_path: Path) -> None:
    f = tmp_path / "bad.yaml"
    f.write_text("api:\n  port: 99999\nunknown_key: 1\n")
    with pytest.raises(ConfigError) as exc:
        load_config(f, env={})
    msg = str(exc.value)
    assert "api.port" in msg
    assert "unknown_key" in msg


def test_redline_must_exceed_warn() -> None:
    with pytest.raises(ConfigError):
        load_config(
            None,
            env={},
            overrides={"ui": {"thresholds": {"shift_warn_rpm": 6500, "shift_redline_rpm": 6000}}},
        )


def test_missing_file_and_bad_yaml(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="not found"):
        load_config(tmp_path / "nope.yaml")
    bad = tmp_path / "bad.yaml"
    bad.write_text("a: [unclosed")
    with pytest.raises(ConfigError, match="invalid YAML"):
        load_config(bad)
    lst = tmp_path / "list.yaml"
    lst.write_text("- 1\n- 2\n")
    with pytest.raises(ConfigError, match="mapping"):
        load_config(lst)


def test_schema_and_metric_units() -> None:
    schema = config_json_schema()
    assert schema["title"] == "AppConfig"
    assert "obd" in schema["properties"]
    cfg = AppConfig(units={"system": "metric", "speed": "mph"})
    assert cfg.units.resolved() == {
        "pressure": "bar",
        "speed": "mph",
        "temperature": "c",
        "distance": "km",
    }
    assert default_config_dir().is_dir()
