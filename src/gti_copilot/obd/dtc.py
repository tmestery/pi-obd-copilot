"""Diagnostic trouble code decoding (read-only) and a compact description table.

Mode 03/07/0A responses carry DTCs as 2-byte pairs. The first two bits select the system
letter (P/C/B/U), the next two bits the first digit, then three hex nibbles.
"""

from __future__ import annotations

from gti_copilot.obd.transport import Dtc, DtcKind

_SYSTEM = ("P", "C", "B", "U")

# Generic (SAE) descriptions for codes plausible on a turbocharged VW. Manufacturer-specific
# meanings (P1xxx, P3xxx) are intentionally left out; unknown codes get a generic string.
DESCRIPTIONS: dict[str, str] = {
    "P0011": "Intake camshaft position timing over-advanced (bank 1)",
    "P0016": "Crankshaft/camshaft position correlation (bank 1 sensor A)",
    "P0087": "Fuel rail/system pressure too low",
    "P0088": "Fuel rail/system pressure too high",
    "P0101": "Mass air flow sensor circuit range/performance",
    "P0106": "Manifold absolute pressure sensor range/performance",
    "P0113": "Intake air temperature sensor circuit high",
    "P0116": "Engine coolant temperature sensor range/performance",
    "P0128": "Coolant thermostat below regulating temperature",
    "P0171": "System too lean (bank 1)",
    "P0172": "System too rich (bank 1)",
    "P0234": "Turbocharger/supercharger overboost condition",
    "P0299": "Turbocharger/supercharger underboost condition",
    "P0300": "Random/multiple cylinder misfire detected",
    "P0301": "Cylinder 1 misfire detected",
    "P0302": "Cylinder 2 misfire detected",
    "P0303": "Cylinder 3 misfire detected",
    "P0304": "Cylinder 4 misfire detected",
    "P0420": "Catalyst system efficiency below threshold (bank 1)",
    "P0441": "Evaporative emission system incorrect purge flow",
    "P0455": "Evaporative emission system leak detected (large leak)",
    "P0456": "Evaporative emission system leak detected (very small leak)",
    "P0500": "Vehicle speed sensor A",
    "P0507": "Idle air control system RPM higher than expected",
    "P0562": "System voltage low",
    "P0563": "System voltage high",
    "P0606": "ECM/PCM processor fault",
    "P2015": "Intake manifold runner position sensor range/performance (bank 1)",
    "P2181": "Cooling system performance",
    "P2187": "System too lean at idle (bank 1)",
    "U0100": "Lost communication with ECM/PCM A",
    "U0121": "Lost communication with ABS control module",
}


def decode_dtc_pair(hi: int, lo: int) -> str | None:
    """Return e.g. ``"P0301"`` or ``None`` for the empty ``00 00`` filler pair."""
    if hi == 0 and lo == 0:
        return None
    system = _SYSTEM[(hi >> 6) & 0x03]
    d1 = (hi >> 4) & 0x03
    d2 = hi & 0x0F
    d3 = (lo >> 4) & 0x0F
    d4 = lo & 0x0F
    return f"{system}{d1}{d2:X}{d3:X}{d4:X}"


def encode_dtc(code: str) -> bytes:
    """Inverse of :func:`decode_dtc_pair`, used by the simulator and tests."""
    code = code.strip().upper()
    if len(code) != 5 or code[0] not in _SYSTEM:
        raise ValueError(f"invalid DTC {code!r}")
    sys_bits = _SYSTEM.index(code[0])
    d1 = int(code[1], 16)
    if d1 > 3:
        raise ValueError(f"invalid DTC first digit in {code!r}")
    hi = (sys_bits << 6) | (d1 << 4) | int(code[2], 16)
    lo = (int(code[3], 16) << 4) | int(code[4], 16)
    return bytes([hi, lo])


def decode_dtc_payload(payload: bytes, kind: DtcKind, can_count_byte: bool = True) -> list[Dtc]:
    """Decode a Mode 03/07/0A response payload (bytes after the service echo).

    On CAN (ISO 15765-4) the first byte is the DTC count; ``can_count_byte`` strips it.
    """
    data = payload
    if can_count_byte and len(data) % 2 == 1:
        data = data[1:]
    codes: list[Dtc] = []
    for i in range(0, len(data) - 1, 2):
        code = decode_dtc_pair(data[i], data[i + 1])
        if code is not None:
            codes.append(Dtc(code=code, kind=kind, description=describe(code)))
    return codes


def describe(code: str) -> str:
    if code in DESCRIPTIONS:
        return DESCRIPTIONS[code]
    prefix = code[:1]
    family = {
        "P": "Powertrain",
        "C": "Chassis",
        "B": "Body",
        "U": "Network/communication",
    }.get(prefix, "Unknown")
    scope = "manufacturer-specific" if code[1:2] in ("1", "3") else "generic"
    return f"{family} code ({scope}); consult a repair manual or scan tool database"
