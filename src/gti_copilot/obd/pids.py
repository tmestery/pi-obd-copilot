"""SAE J1979 Mode 01 PID table: decoding, encoding (for the simulator), units, ranges, tiers.

Formulas follow SAE J1979 / ISO 15031-5. ``encode`` is the inverse of ``decode`` and is used by
the simulator so that the exact same decode path is exercised in CI as on the car.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum

from gti_copilot.errors import DecodeError


class Tier(str, Enum):
    FAST = "fast"
    MEDIUM = "medium"
    SLOW = "slow"


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _u8(v: float) -> bytes:
    return bytes([round(_clamp(v, 0, 255))])


def _u16(v: float) -> bytes:
    iv = round(_clamp(v, 0, 65535))
    return bytes([iv >> 8, iv & 0xFF])


@dataclass(frozen=True)
class PidDef:
    pid: int
    key: str
    name: str
    unit: str
    length: int
    decode: Callable[[bytes], float]
    encode: Callable[[float], bytes]
    min: float
    max: float
    tier: Tier
    resolution: float = 1.0
    optional: bool = False  # only enabled when the ECU reports support

    @property
    def hex(self) -> str:
        return f"{self.pid:02X}"


def _pid(
    pid: int,
    key: str,
    name: str,
    unit: str,
    length: int,
    decode: Callable[[bytes], float],
    encode: Callable[[float], bytes],
    lo: float,
    hi: float,
    tier: Tier,
    resolution: float = 1.0,
    optional: bool = False,
) -> PidDef:
    return PidDef(pid, key, name, unit, length, decode, encode, lo, hi, tier, resolution, optional)


# Common formulas
def _percent_a(d: bytes) -> float:
    return d[0] * 100.0 / 255.0


def _percent_a_enc(v: float) -> bytes:
    return _u8(v * 255.0 / 100.0)


def _temp_a(d: bytes) -> float:
    return float(d[0] - 40)


def _temp_a_enc(v: float) -> bytes:
    return _u8(v + 40)


def _trim_a(d: bytes) -> float:
    return (d[0] - 128) * 100.0 / 128.0


def _trim_a_enc(v: float) -> bytes:
    return _u8(v * 128.0 / 100.0 + 128)


def _raw_a(d: bytes) -> float:
    return float(d[0])


def _raw_a_enc(v: float) -> bytes:
    return _u8(v)


def _rpm(d: bytes) -> float:
    return (d[0] * 256 + d[1]) / 4.0


def _rpm_enc(v: float) -> bytes:
    return _u16(v * 4.0)


def _timing(d: bytes) -> float:
    return d[0] / 2.0 - 64.0


def _timing_enc(v: float) -> bytes:
    return _u8((v + 64.0) * 2.0)


def _maf(d: bytes) -> float:
    return (d[0] * 256 + d[1]) / 100.0


def _maf_enc(v: float) -> bytes:
    return _u16(v * 100.0)


def _fuel_pressure(d: bytes) -> float:
    return d[0] * 3.0


def _fuel_pressure_enc(v: float) -> bytes:
    return _u8(v / 3.0)


def _voltage(d: bytes) -> float:
    return (d[0] * 256 + d[1]) / 1000.0


def _voltage_enc(v: float) -> bytes:
    return _u16(v * 1000.0)


def _fuel_rate(d: bytes) -> float:
    return (d[0] * 256 + d[1]) / 20.0


def _fuel_rate_enc(v: float) -> bytes:
    return _u16(v * 20.0)


def _turbo_inlet(d: bytes) -> float:
    # PID 6F: A = supported turbos bitmap, B = turbo A inlet pressure (kPa), C = turbo B.
    return float(d[1])


def _turbo_inlet_enc(v: float) -> bytes:
    return b"\x01" + _u8(v) + b"\x00"


def _boost_control(d: bytes) -> float:
    # PID 70 (10 bytes): A bitmap, B-C commanded boost A (kPa /32), D-E actual boost A (kPa /32),
    # F-G commanded B, H-I actual B, J status. We expose *actual* turbo A boost pressure.
    return (d[3] * 256 + d[4]) / 32.0


def _boost_control_enc(v: float) -> bytes:
    actual = _u16(v * 32.0)
    return b"\x01" + actual + actual + b"\x00\x00\x00\x00\x00"


PIDS: tuple[PidDef, ...] = (
    _pid(0x04, "load_pct", "Calculated engine load", "%", 1, _percent_a, _percent_a_enc, 0, 100, Tier.MEDIUM, 100 / 255),
    _pid(0x05, "coolant_c", "Engine coolant temperature", "°C", 1, _temp_a, _temp_a_enc, -40, 215, Tier.SLOW),
    _pid(0x06, "stft_b1_pct", "Short term fuel trim B1", "%", 1, _trim_a, _trim_a_enc, -100, 99.2, Tier.SLOW, 100 / 128),
    _pid(0x07, "ltft_b1_pct", "Long term fuel trim B1", "%", 1, _trim_a, _trim_a_enc, -100, 99.2, Tier.SLOW, 100 / 128),
    _pid(0x0A, "fuel_pressure_kpa", "Fuel pressure (gauge)", "kPa", 1, _fuel_pressure, _fuel_pressure_enc, 0, 765, Tier.SLOW, 3, optional=True),
    _pid(0x0B, "map_kpa", "Intake manifold absolute pressure", "kPa", 1, _raw_a, _raw_a_enc, 0, 255, Tier.FAST),
    _pid(0x0C, "rpm", "Engine RPM", "rpm", 2, _rpm, _rpm_enc, 0, 16383.75, Tier.FAST, 0.25),
    _pid(0x0D, "speed_kph", "Vehicle speed", "km/h", 1, _raw_a, _raw_a_enc, 0, 255, Tier.FAST),
    _pid(0x0E, "timing_deg", "Timing advance", "° before TDC", 1, _timing, _timing_enc, -64, 63.5, Tier.MEDIUM, 0.5),
    _pid(0x0F, "iat_c", "Intake air temperature", "°C", 1, _temp_a, _temp_a_enc, -40, 215, Tier.SLOW),
    _pid(0x10, "maf_gps", "Mass air flow rate", "g/s", 2, _maf, _maf_enc, 0, 655.35, Tier.MEDIUM, 0.01),
    _pid(0x11, "throttle_pct", "Throttle position", "%", 1, _percent_a, _percent_a_enc, 0, 100, Tier.FAST, 100 / 255),
    _pid(0x2F, "fuel_level_pct", "Fuel tank level input", "%", 1, _percent_a, _percent_a_enc, 0, 100, Tier.SLOW, 100 / 255),
    _pid(0x33, "baro_kpa", "Absolute barometric pressure", "kPa", 1, _raw_a, _raw_a_enc, 0, 255, Tier.SLOW),
    _pid(0x42, "volt_v", "Control module voltage", "V", 2, _voltage, _voltage_enc, 0, 65.535, Tier.SLOW, 0.001),
    _pid(0x45, "rel_throttle_pct", "Relative throttle position", "%", 1, _percent_a, _percent_a_enc, 0, 100, Tier.MEDIUM, 100 / 255),
    _pid(0x46, "ambient_c", "Ambient air temperature", "°C", 1, _temp_a, _temp_a_enc, -40, 215, Tier.SLOW),
    _pid(0x49, "pedal_d_pct", "Accelerator pedal position D", "%", 1, _percent_a, _percent_a_enc, 0, 100, Tier.MEDIUM, 100 / 255),
    _pid(0x4A, "pedal_e_pct", "Accelerator pedal position E", "%", 1, _percent_a, _percent_a_enc, 0, 100, Tier.MEDIUM, 100 / 255),
    _pid(0x5C, "oil_temp_c", "Engine oil temperature", "°C", 1, _temp_a, _temp_a_enc, -40, 210, Tier.SLOW, optional=True),
    _pid(0x5E, "fuel_rate_lph", "Engine fuel rate", "L/h", 2, _fuel_rate, _fuel_rate_enc, 0, 3276.75, Tier.MEDIUM, 0.05, optional=True),
    _pid(0x6F, "turbo_inlet_kpa", "Turbocharger compressor inlet pressure", "kPa", 3, _turbo_inlet, _turbo_inlet_enc, 0, 255, Tier.SLOW, optional=True),
    _pid(0x70, "turbo_boost_kpa", "Boost pressure control (actual, turbo A)", "kPa", 10, _boost_control, _boost_control_enc, 0, 2047.97, Tier.MEDIUM, 1 / 32, optional=True),
)  # fmt: skip

BY_PID: dict[int, PidDef] = {p.pid: p for p in PIDS}
BY_KEY: dict[str, PidDef] = {p.key: p for p in PIDS}

SUPPORT_BITMAP_PIDS: tuple[int, ...] = (0x00, 0x20, 0x40, 0x60, 0x80, 0xA0, 0xC0)


def get(pid: int) -> PidDef:
    try:
        return BY_PID[pid]
    except KeyError as exc:
        raise DecodeError(f"unknown PID 0x{pid:02X}") from exc


def decode(pid: int, data: bytes) -> float:
    """Decode a Mode 01 payload (bytes after the PID echo) into engineering units."""
    pdef = get(pid)
    if len(data) < pdef.length:
        raise DecodeError(
            f"PID 0x{pid:02X} expects {pdef.length} bytes, got {len(data)}: {data.hex()}"
        )
    return pdef.decode(data[: pdef.length])


def encode(pid: int, value: float) -> bytes:
    pdef = get(pid)
    return pdef.encode(value)


def decode_support_bitmap(base_pid: int, data: bytes) -> set[int]:
    """Decode a PID 0x00/0x20/... support bitmap into the set of supported PID numbers.

    Bit 7 of byte A corresponds to ``base_pid + 1``; bit 0 of byte D to ``base_pid + 32``.
    """
    if len(data) < 4:
        raise DecodeError(f"support bitmap for 0x{base_pid:02X} needs 4 bytes, got {len(data)}")
    supported: set[int] = set()
    bits = int.from_bytes(data[:4], "big")
    for i in range(32):
        if bits & (1 << (31 - i)):
            supported.add(base_pid + 1 + i)
    return supported


def encode_support_bitmap(base_pid: int, supported: set[int]) -> bytes:
    bits = 0
    for pid in supported:
        offset = pid - base_pid - 1
        if 0 <= offset < 32:
            bits |= 1 << (31 - offset)
    return bits.to_bytes(4, "big")


def in_range(pid: int, value: float) -> bool:
    pdef = get(pid)
    return pdef.min - 1e-9 <= value <= pdef.max + 1e-9


def keys_for_tier(tier: Tier) -> list[str]:
    return [p.key for p in PIDS if p.tier is tier]
