from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from gti_copilot.errors import ForbiddenServiceError, NotConnectedError
from gti_copilot.obd.allowlist import GUARD, ReadOnlyGuard
from gti_copilot.obd.dtc import decode_dtc_pair, decode_dtc_payload, describe, encode_dtc
from gti_copilot.obd.transport import Backoff, BaseTransport, Dtc, RawResponse


class _DummyTransport(BaseTransport):
    def __init__(self, **kw: object) -> None:
        super().__init__(**kw)  # type: ignore[arg-type]
        self.queried: list[tuple[int, int]] = []

    @property
    def name(self) -> str:
        return "dummy"

    async def _do_connect(self) -> None:
        return None

    async def _do_close(self) -> None:
        return None

    async def _do_supported_pids(self) -> set[int]:
        return {0x0C}

    async def _do_query(self, mode: int, pid: int, request: str) -> RawResponse | None:
        self.queried.append((mode, pid))
        return RawResponse(mode, pid, b"\x0c\x00", 0.0)

    async def _do_read_dtcs(self) -> list[Dtc]:
        return []


async def test_transport_requires_connection() -> None:
    t = _DummyTransport()
    assert not t.connected
    with pytest.raises(NotConnectedError):
        await t.query(0x01, 0x0C)
    await t.connect()
    assert t.connected
    assert await t.query(0x01, 0x0C) is not None
    assert t.stats.queries == 1
    await t.close()
    assert not t.connected


async def test_transport_guards_forbidden_service_before_io() -> None:
    t = _DummyTransport()
    await t.connect()
    with pytest.raises(ForbiddenServiceError):
        await t.query(0x04, 0x00)  # clear codes
    assert t.queried == []  # never reached the I/O hook


def test_transport_rejects_custom_guard() -> None:
    with pytest.raises(ForbiddenServiceError):
        _DummyTransport(guard=ReadOnlyGuard())  # a different instance is refused
    # The canonical guard is accepted.
    assert _DummyTransport(guard=GUARD).guard is GUARD


def test_backoff_is_bounded_and_resets() -> None:
    import random

    b = Backoff(min_s=1.0, max_s=8.0, rng=random.Random(0))
    delays = [b.next_delay() for _ in range(10)]
    assert all(0 <= d <= 8.0 for d in delays)
    assert max(delays) <= 8.0
    b.reset()
    assert b.attempt == 0


# --------------------------------------------------------------------------- DTC
def test_decode_dtc_pair_known() -> None:
    assert decode_dtc_pair(0x01, 0x33) == "P0133"
    assert decode_dtc_pair(0x43, 0x00) == "C0300"
    assert decode_dtc_pair(0x83, 0x01) == "U0301"
    assert decode_dtc_pair(0x00, 0x00) is None


def test_decode_payload_strips_can_count_byte() -> None:
    # count byte 0x02 then P0301 (0x0301) and P0420 (0x0420)
    payload = bytes([0x02, 0x03, 0x01, 0x04, 0x20])
    codes = decode_dtc_payload(payload, "stored")
    assert [c.code for c in codes] == ["P0301", "P0420"]
    assert codes[0].description  # non-empty


@given(
    st.sampled_from("PCBU"),
    st.integers(0, 3),
    st.integers(0, 15),
    st.integers(0, 15),
    st.integers(0, 15),
)
def test_encode_decode_dtc_roundtrip(sysc: str, d1: int, d2: int, d3: int, d4: int) -> None:
    code = f"{sysc}{d1}{d2:X}{d3:X}{d4:X}"
    raw = encode_dtc(code)
    assert decode_dtc_pair(raw[0], raw[1]) == code


def test_encode_dtc_validates() -> None:
    with pytest.raises(ValueError, match="invalid DTC"):
        encode_dtc("X0000")
    with pytest.raises(ValueError):
        encode_dtc("P123")


def test_describe_generic_vs_manufacturer() -> None:
    assert "lean" in describe("P0171").lower()
    assert "manufacturer-specific" in describe("P1234")
    assert "generic" in describe("P0999")
    assert describe("U0100").startswith("Lost communication")
