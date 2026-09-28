"""Read-only safety allowlist for everything that can be sent to the vehicle.

This module is the single choke point between gti-copilot and the ECU. Every transport must
route each outgoing request through :func:`guard_request` (OBD services) and
:func:`guard_at_command` (adapter AT commands). The allowlist cannot be disabled: there is no
flag, environment variable or constructor argument that turns it off, and the guard object is
immutable.

Allowed OBD services (SAE J1979):

* ``0x01`` current data, ``0x02`` freeze frame, ``0x03`` stored DTCs, ``0x07`` pending DTCs,
  ``0x09`` vehicle information (VIN, calibration IDs), ``0x0A`` permanent DTCs.

Explicitly forbidden (non-exhaustive, everything not allowed is rejected anyway):

* ``0x04`` clear DTCs / freeze frame data.
* ``0x05`` O2 monitoring, ``0x06`` on-board monitoring test results, ``0x08`` request control
  of on-board system (actuator tests).
* UDS (ISO 14229) services: ``0x10`` diagnostic session control, ``0x11`` ECU reset, ``0x14``
  clear diagnostic information, ``0x27`` security access, ``0x28`` communication control,
  ``0x2E`` write data by identifier, ``0x2F`` I/O control, ``0x31`` routine control,
  ``0x34``-``0x37`` download/upload/transfer, ``0x3D`` write memory by address, ``0x85``
  control DTC setting, and every other UDS request.
* Any ELM/STN AT command outside the initialisation set (echo/headers/spaces/linefeeds off,
  protocol select, adaptive timing, timeouts, reset, identify, voltage read). Commands that
  change adapter behaviour permanently (``AT PP`` programmable parameters, ``ST SBR`` baud
  writes, ``AT SH`` custom headers used for UDS addressing, ``AT CRA`` filters, monitor modes)
  are rejected.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final

from gti_copilot.errors import ForbiddenServiceError

ALLOWED_SERVICES: Final[frozenset[int]] = frozenset({0x01, 0x02, 0x03, 0x07, 0x09, 0x0A})

# Documented for tests and for humans; the guard rejects anything not in ALLOWED_SERVICES,
# not merely these.
FORBIDDEN_SERVICES_EXAMPLES: Final[frozenset[int]] = frozenset(
    {
        0x04,  # clear DTCs
        0x05,
        0x06,
        0x08,
        0x10,
        0x11,
        0x14,
        0x22,  # UDS read data by identifier (out of scope until validated; treat as forbidden)
        0x23,
        0x27,
        0x28,
        0x2E,
        0x2F,
        0x31,
        0x34,
        0x35,
        0x36,
        0x37,
        0x3D,
        0x3E,
        0x85,
    }
)

# ELM327 / STN AT command allowlist, matched case-insensitively after removing spaces.
_ALLOWED_AT_PATTERNS: Final[tuple[re.Pattern[str], ...]] = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"^ATZ$",  # reset
        r"^ATWS$",  # warm start
        r"^ATD$",  # defaults
        r"^ATI$",  # identify
        r"^AT@1$",  # device description
        r"^ATRV$",  # read voltage
        r"^ATE[01]$",  # echo
        r"^ATL[01]$",  # linefeeds
        r"^ATS[01]$",  # spaces
        r"^ATH[01]$",  # headers
        r"^ATSP[0-9A-C]$",  # set protocol
        r"^ATTP[0-9A-C]$",  # try protocol
        r"^ATDP$",  # describe protocol
        r"^ATDPN$",
        r"^ATAT[012]$",  # adaptive timing
        r"^ATST[0-9A-F]{1,2}$",  # timeout
        r"^ATCAF1$",  # CAN auto formatting ON (default; never OFF)
        r"^ATPC$",  # protocol close
        r"^STI$",  # STN identify
        r"^STDI$",
        r"^STVR$",  # STN voltage
    )
)

_FORBIDDEN_AT_EXAMPLES: Final[tuple[str, ...]] = (
    "AT PP",  # programmable parameters (persistent)
    "AT SH",  # set header (needed for UDS addressing)
    "AT CRA",  # CAN receive address filter
    "AT CAF0",  # raw CAN frames
    "AT MA",  # monitor all
    "AT MT",
    "AT MR",
    "AT FC",  # flow control tweaks
    "AT CP",
    "AT CV",  # calibrate voltage
    "AT SW",  # wakeup messages
    "AT WM",
    "AT IB",  # ISO baud
    "AT BRD",  # baud rate
    "ST SBR",  # STN baud
    "ST P",  # STN protocol tweaks
    "ST FAP",  # STN filters
    "ST FPA",
)


def _norm(cmd: str) -> str:
    return re.sub(r"\s+", "", cmd).upper()


@dataclass(frozen=True, slots=True)
class ReadOnlyGuard:
    """Immutable guard. Instances are interchangeable; :data:`GUARD` is the shared one."""

    def check_service(self, service: int) -> None:
        if service not in ALLOWED_SERVICES:
            raise ForbiddenServiceError(
                f"OBD service 0x{service:02X} is not allowed: gti-copilot is read-only "
                f"(allowed: {sorted(f'0x{s:02X}' for s in ALLOWED_SERVICES)})"
            )

    def check_at_command(self, command: str) -> None:
        norm = _norm(command)
        if not norm.startswith(("AT", "ST")):
            raise ForbiddenServiceError(f"not an AT/ST command: {command!r}")
        if not any(p.match(norm) for p in _ALLOWED_AT_PATTERNS):
            raise ForbiddenServiceError(
                f"adapter command {command!r} is not in the read-only init allowlist"
            )

    def check_raw(self, line: str) -> None:
        """Validate a raw line about to be written to the adapter (hex request or AT)."""
        norm = _norm(line)
        if not norm:
            raise ForbiddenServiceError("empty request")
        if norm.startswith(("AT", "ST")):
            self.check_at_command(norm)
            return
        if not re.fullmatch(r"[0-9A-F]+", norm) or len(norm) < 2:
            raise ForbiddenServiceError(f"malformed request {line!r}")
        self.check_service(int(norm[:2], 16))

    @property
    def allowed_services(self) -> frozenset[int]:
        # frozen=True already makes instances immutable (assignment raises FrozenInstanceError,
        # a subclass of AttributeError); there is intentionally no way to disable the guard.
        return ALLOWED_SERVICES


GUARD: Final[ReadOnlyGuard] = ReadOnlyGuard()


def guard_request(service: int, pid: int | None = None) -> str:
    """Validate and format an OBD request as the hex string sent to the adapter."""
    GUARD.check_service(service)
    if pid is None:
        return f"{service:02X}"
    if not 0 <= pid <= 0xFF:
        raise ForbiddenServiceError(f"PID out of range: {pid}")
    return f"{service:02X}{pid:02X}"


def guard_at_command(command: str) -> str:
    GUARD.check_at_command(command)
    return _norm(command)


def is_forbidden_at_example(command: str) -> bool:
    n = _norm(command)
    return any(n.startswith(_norm(e)) for e in _FORBIDDEN_AT_EXAMPLES)
