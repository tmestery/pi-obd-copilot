"""Application configuration: pydantic models, YAML loader, ``GTI_*`` env overrides.

Precedence (lowest to highest): model defaults < YAML file < environment variables < explicit
overrides (CLI flags). Environment variables use a double underscore as the nesting separator,
e.g. ``GTI_OBD__DEVICE=/dev/ttyUSB0`` sets ``obd.device`` and ``GTI_API__PORT=9000`` sets
``api.port``. Values are parsed as YAML scalars so ``true``/``3.5``/``[a, b]`` work.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from gti_copilot.errors import ConfigError

ENV_PREFIX = "GTI_"
ENV_SEP = "__"

PACKAGE_ROOT = Path(__file__).resolve().parent
REPO_ROOT = PACKAGE_ROOT.parent.parent
BUNDLED_CONFIG_DIR = PACKAGE_ROOT / "_bundled" / "config"


def default_config_dir() -> Path:
    """Where the example configs live: repo checkout first, installed wheel second."""
    repo = REPO_ROOT / "config"
    return repo if repo.is_dir() else BUNDLED_CONFIG_DIR


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


# --------------------------------------------------------------------------- sections
class UnitsConfig(_Strict):
    system: Literal["imperial", "metric"] = "imperial"
    pressure: Literal["psi", "bar", "kpa"] | None = None
    speed: Literal["mph", "kph"] | None = None
    temperature: Literal["f", "c"] | None = None
    distance: Literal["mi", "km"] | None = None

    def resolved(self) -> dict[str, str]:
        base: dict[str, str] = (
            {"pressure": "psi", "speed": "mph", "temperature": "f", "distance": "mi"}
            if self.system == "imperial"
            else {"pressure": "bar", "speed": "kph", "temperature": "c", "distance": "km"}
        )
        for key in base:
            override = getattr(self, key)
            if override is not None:
                base[key] = override
        return base


class ObdConfig(_Strict):
    transport: Literal["sim", "elm"] = "sim"
    device: str = "/dev/rfcomm0"
    baud: int = Field(115200, ge=9600, le=2_000_000)
    timeout_s: float = Field(1.0, gt=0, le=10)
    protocol: str = Field("6", description="ELM protocol number; 6 = ISO 15765-4 CAN 11-bit 500k")
    reconnect_min_s: float = Field(1.0, gt=0)
    reconnect_max_s: float = Field(30.0, gt=0)
    dtc_poll_s: float = Field(60.0, gt=0)


class SchedulerConfig(_Strict):
    fast_hz: float = Field(6.0, gt=0, le=20)
    medium_hz: float = Field(1.5, gt=0, le=10)
    slow_hz: float = Field(0.25, gt=0, le=2)
    max_reads_per_s: float = Field(15.0, gt=0, le=200)
    failure_backoff_s: float = Field(5.0, gt=0)


class StorageConfig(_Strict):
    path: Path = Path("data/runtime/gti-copilot.sqlite")
    batch_rows: int = Field(200, ge=1)
    batch_interval_s: float = Field(1.0, gt=0)
    checkpoint_interval_s: float = Field(60.0, gt=0)
    retention_days: int = Field(365, ge=1)
    downsample_after_days: int = Field(30, ge=1)
    downsample_keep_every: int = Field(10, ge=2)
    max_db_mb: int = Field(2048, ge=16)
    trip_end_idle_min: float = Field(5.0, gt=0)
    export_dir: Path = Path("data/runtime/exports")


class PowerConfig(_Strict):
    monitor: Literal["sim", "gpio", "wittypi", "voltage", "none"] = "sim"
    gpio_pin: int = Field(17, ge=0, le=40)
    active_low: bool = False
    debounce_s: float = Field(2.0, ge=0)
    shutdown_delay_s: float = Field(30.0, ge=0)
    low_voltage_v: float = Field(11.6, gt=0)
    low_voltage_hold_s: float = Field(20.0, ge=0)
    shutdown_command: list[str] = Field(default_factory=lambda: ["systemctl", "poweroff"])
    dry_run: bool = True


class GpsConfig(_Strict):
    provider: Literal["sim", "gpsd", "nmea", "none"] = "sim"
    host: str = "127.0.0.1"
    port: int = Field(2947, ge=1, le=65535)
    nmea_path: Path | None = None
    stale_after_s: float = Field(5.0, gt=0)


class RadarConfig(_Strict):
    provider: Literal["mock", "r8link", "serial", "none"] = "mock"
    address: str | None = None
    device: str | None = None
    beep: bool = False
    merge_window_s: float = Field(3.0, ge=0)
    hotspot_radius_m: float = Field(150.0, gt=0)


class CameraConfig(_Strict):
    source: Literal["file", "v4l2", "picamera", "none"] = "file"
    path: Path | None = None
    device: str = "/dev/video0"
    width: int = Field(1280, ge=160)
    height: int = Field(720, ge=120)
    fps: int = Field(30, ge=1, le=120)
    bitrate_kbps: int = Field(4000, ge=200)
    segment_s: int = Field(10, ge=2)
    ring_minutes: int = Field(3, ge=1)
    max_disk_gb: float = Field(20.0, gt=0)
    clips_dir: Path = Path("data/runtime/clips")
    pre_event_s: int = Field(30, ge=0)
    post_event_s: int = Field(15, ge=0)
    overlay: bool = False
    clip_on_radar: bool = False


class PerceptionConfig(_Strict):
    detector: Literal["null", "onnx", "hailo", "coral"] = "null"
    model_path: Path | None = None
    fps: float = Field(5.0, gt=0, le=60)
    conf_threshold: float = Field(0.35, ge=0, le=1)
    nms_iou: float = Field(0.5, ge=0, le=1)
    classes: list[str] = Field(
        default_factory=lambda: [
            "car",
            "truck",
            "bus",
            "motorcycle",
            "bicycle",
            "person",
            "traffic light",
            "stop sign",
        ]
    )
    closing_fast_experimental: bool = False
    sign_ocr_experimental: bool = False


class CopilotPolicyConfig(_Strict):
    moving_speed_kph: float = Field(4.8, ge=0, description="~3 mph")
    push_to_talk_while_moving: bool = False
    summary_on_trip_end: bool = True


class CopilotConfig(_Strict):
    backend: Literal["template", "llama", "ollama"] = "template"
    model: str = "qwen2.5:1.5b-instruct"
    url: str = "http://127.0.0.1:11434"
    max_tokens: int = Field(220, ge=16, le=2048)
    temperature: float = Field(0.3, ge=0, le=2)
    timeout_s: float = Field(30.0, gt=0)
    stt: Literal["null", "whisper", "mock"] = "null"
    tts: Literal["null", "piper"] = "null"
    knowledge_dir: Path | None = None
    policy: CopilotPolicyConfig = Field(default_factory=CopilotPolicyConfig)


class UiThresholds(_Strict):
    shift_warn_rpm: int = Field(6000, ge=1000)
    shift_redline_rpm: int = Field(6500, ge=1000)
    coolant_warn_c: float = 110.0
    iat_warn_c: float = 60.0
    volt_low_v: float = 12.2
    volt_high_v: float = 15.2
    boost_gauge_max_kpa: float = 150.0

    @field_validator("shift_redline_rpm")
    @classmethod
    def _redline_after_warn(cls, v: int, info: Any) -> int:
        warn = info.data.get("shift_warn_rpm")
        if warn is not None and v < warn:
            raise ValueError("shift_redline_rpm must be >= shift_warn_rpm")
        return v


class UiConfig(_Strict):
    theme: Literal["night", "day", "auto"] = "night"
    night_start_hour: int = Field(19, ge=0, le=23)
    night_end_hour: int = Field(6, ge=0, le=23)
    lockout_speed_kph: float = Field(4.8, ge=0)
    ws_hz: float = Field(15.0, gt=0, le=30)
    thresholds: UiThresholds = Field(default_factory=UiThresholds)


class ApiConfig(_Strict):
    host: str = "127.0.0.1"
    port: int = Field(8765, ge=1, le=65535)
    cors_origins: list[str] = Field(default_factory=list)
    serve_web: bool = True


class SimConfig(_Strict):
    scenario: str = "demo_drive"
    seed: int = 42
    time_scale: float = Field(1.0, gt=0, le=100)
    loop: bool = True
    dropout: bool = True


class LogConfig(_Strict):
    level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    json_format: bool = False
    file: Path | None = None


class AppConfig(_Strict):
    mode: Literal["sim", "car"] = "sim"
    units: UnitsConfig = Field(default_factory=UnitsConfig)
    vehicle: Path = Path("config/vehicle/mk7-gti.yaml")
    obd: ObdConfig = Field(default_factory=ObdConfig)
    scheduler: SchedulerConfig = Field(default_factory=SchedulerConfig)
    storage: StorageConfig = Field(default_factory=StorageConfig)
    power: PowerConfig = Field(default_factory=PowerConfig)
    gps: GpsConfig = Field(default_factory=GpsConfig)
    radar: RadarConfig = Field(default_factory=RadarConfig)
    camera: CameraConfig = Field(default_factory=CameraConfig)
    perception: PerceptionConfig = Field(default_factory=PerceptionConfig)
    copilot: CopilotConfig = Field(default_factory=CopilotConfig)
    ui: UiConfig = Field(default_factory=UiConfig)
    api: ApiConfig = Field(default_factory=ApiConfig)
    sim: SimConfig = Field(default_factory=SimConfig)
    log: LogConfig = Field(default_factory=LogConfig)

    def resolve_vehicle_path(self) -> Path:
        """Vehicle YAML path, resolved against the repo/bundled config dir if relative."""
        if self.vehicle.is_absolute() or self.vehicle.exists():
            return self.vehicle
        candidate = default_config_dir().parent / self.vehicle
        if candidate.exists():
            return candidate
        bundled = BUNDLED_CONFIG_DIR / self.vehicle.relative_to("config")
        return bundled if bundled.exists() else self.vehicle


# --------------------------------------------------------------------------- loading
def _deep_merge(base: dict[str, Any], overlay: Mapping[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for key, value in overlay.items():
        if isinstance(value, Mapping) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def _parse_scalar(raw: str) -> Any:
    try:
        return yaml.safe_load(raw)
    except yaml.YAMLError:
        return raw


def env_overrides(env: Mapping[str, str] | None = None, prefix: str = ENV_PREFIX) -> dict[str, Any]:
    """Turn ``GTI_A__B=1`` style variables into ``{"a": {"b": 1}}``."""
    env = os.environ if env is None else env
    out: dict[str, Any] = {}
    for key, raw in env.items():
        if not key.startswith(prefix) or key == prefix:
            continue
        path = [p.lower() for p in key[len(prefix) :].split(ENV_SEP) if p]
        if not path:
            continue
        node = out
        for part in path[:-1]:
            node = node.setdefault(part, {})
            if not isinstance(node, dict):  # pragma: no cover - conflicting env vars
                break
        else:
            node[path[-1]] = _parse_scalar(raw)
    return out


def load_yaml(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
    except FileNotFoundError as exc:
        raise ConfigError(f"config file not found: {path}") from exc
    except yaml.YAMLError as exc:
        raise ConfigError(f"invalid YAML in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigError(f"config root must be a mapping: {path}")
    return data


def load_config(
    path: Path | None = None,
    *,
    env: Mapping[str, str] | None = None,
    overrides: Mapping[str, Any] | None = None,
) -> AppConfig:
    """Build the :class:`AppConfig` from defaults, YAML, environment and explicit overrides."""
    data: dict[str, Any] = {}
    if path is not None:
        data = _deep_merge(data, load_yaml(path))
    data = _deep_merge(data, env_overrides(env))
    if overrides:
        data = _deep_merge(data, overrides)
    try:
        return AppConfig.model_validate(data)
    except ValidationError as exc:
        raise ConfigError(_format_validation_error(exc)) from exc


def _format_validation_error(exc: ValidationError) -> str:
    lines = ["invalid configuration:"]
    for err in exc.errors():
        loc = ".".join(str(p) for p in err["loc"]) or "<root>"
        lines.append(f"  {loc}: {err['msg']}")
    return "\n".join(lines)


def config_json_schema() -> dict[str, Any]:
    return AppConfig.model_json_schema()


def dump_config(cfg: AppConfig) -> str:
    return yaml.safe_dump(cfg.model_dump(mode="json"), sort_keys=False)
