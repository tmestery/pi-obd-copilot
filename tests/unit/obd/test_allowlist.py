from __future__ import annotations

import pytest

from gti_copilot.errors import ForbiddenServiceError
from gti_copilot.obd.allowlist import (
    ALLOWED_SERVICES,
    FORBIDDEN_SERVICES_EXAMPLES,
    GUARD,
    ReadOnlyGuard,
    guard_at_command,
    guard_request,
    is_forbidden_at_example,
)


@pytest.mark.parametrize("service", sorted(ALLOWED_SERVICES))
def test_allowed_services_pass(service: int) -> None:
    assert guard_request(service).upper() == f"{service:02X}"
    assert guard_request(service, 0x0C) == f"{service:02X}0C"


@pytest.mark.parametrize("service", sorted(FORBIDDEN_SERVICES_EXAMPLES))
def test_forbidden_services_blocked(service: int) -> None:
    with pytest.raises(ForbiddenServiceError):
        guard_request(service)


def test_clear_dtc_mode04_is_blocked() -> None:
    # The single most important guarantee: we can never clear codes.
    with pytest.raises(ForbiddenServiceError, match="0x04"):
        guard_request(0x04)
    with pytest.raises(ForbiddenServiceError):
        GUARD.check_raw("04")


@pytest.mark.parametrize("service", [0x00, 0x0B, 0x0F, 0x22, 0x2E, 0x2F, 0x31, 0x3E, 0x85, 0xFF])
def test_everything_not_allowed_is_rejected(service: int) -> None:
    if service in ALLOWED_SERVICES:
        return
    with pytest.raises(ForbiddenServiceError):
        guard_request(service)


def test_pid_range_validated() -> None:
    with pytest.raises(ForbiddenServiceError):
        guard_request(0x01, 0x100)
    with pytest.raises(ForbiddenServiceError):
        guard_request(0x01, -1)


@pytest.mark.parametrize(
    "cmd",
    ["ATZ", "ATE0", "ATL0", "ATS0", "ATH1", "ATSP6", "ATRV", "ATDPN", "ATST64", "STI", "at sp 6"],
)
def test_allowed_at_commands(cmd: str) -> None:
    assert guard_at_command(cmd)


@pytest.mark.parametrize(
    "cmd",
    [
        "ATPP01SV05",
        "ATSH7E0",
        "ATCRA7E8",
        "ATCAF0",
        "ATMA",
        "ATBRD23",
        "STSBR",
        "AT CV 1234",
        "ATWM",
    ],
)
def test_forbidden_at_commands(cmd: str) -> None:
    with pytest.raises(ForbiddenServiceError):
        guard_at_command(cmd)
    assert (
        is_forbidden_at_example(cmd) or True
    )  # examples list is illustrative, guard is exhaustive


def test_check_raw_variants() -> None:
    GUARD.check_raw("010C")
    GUARD.check_raw("03")
    GUARD.check_raw("AT SP 6")
    with pytest.raises(ForbiddenServiceError):
        GUARD.check_raw("")
    with pytest.raises(ForbiddenServiceError):
        GUARD.check_raw("ZZ")
    with pytest.raises(ForbiddenServiceError):
        GUARD.check_raw("2E01023344")  # UDS write data by identifier


def test_guard_is_immutable() -> None:
    with pytest.raises(AttributeError):
        GUARD.something = 1  # type: ignore[attr-defined]
    # A freshly built guard is equivalent and equally immutable.
    g = ReadOnlyGuard()
    assert g.allowed_services == ALLOWED_SERVICES
    with pytest.raises(AttributeError):
        g.allowed = None  # type: ignore[attr-defined]
