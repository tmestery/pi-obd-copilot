"""PID decoding against SAE J1979 byte fixtures + round-trip property tests."""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from gti_copilot.errors import DecodeError
from gti_copilot.obd import pids
from gti_copilot.obd.pids import (
    PIDS,
    Tier,
    decode,
    decode_support_bitmap,
    encode,
    encode_support_bitmap,
    in_range,
    keys_for_tier,
)

# (pid, payload bytes, expected engineering value) taken from the J1979 formulas
FIXTURES = [
    (0x04, bytes([0xFF]), 100.0),
    (0x04, bytes([0x80]), 128 * 100 / 255),
    (0x05, bytes([0x84]), 92.0),  # 0x84 = 132 -> 92 degC
    (0x05, bytes([0x28]), 0.0),
    (0x06, bytes([0x80]), 0.0),
    (0x06, bytes([0x00]), -100.0),
    (0x07, bytes([0x90]), 12.5),
    (0x0A, bytes([0x64]), 300.0),
    (0x0B, bytes([0xA2]), 162.0),
    (0x0C, bytes([0x30, 0xC0]), 3120.0),  # 0x30C0 = 12480 / 4
    (0x0C, bytes([0x00, 0x00]), 0.0),
    (0x0D, bytes([0x58]), 88.0),
    (0x0E, bytes([0x80]), 0.0),
    (0x0E, bytes([0xA0]), 16.0),
    (0x0F, bytes([0x51]), 41.0),
    (0x10, bytes([0x27, 0x10]), 100.0),  # 10000 / 100
    (0x11, bytes([0xBD]), 189 * 100 / 255),
    (0x2F, bytes([0x40]), 64 * 100 / 255),
    (0x33, bytes([0x65]), 101.0),
    (0x42, bytes([0x37, 0x12]), 14.098),  # 0x3712 = 14098 mV
    (0x45, bytes([0x00]), 0.0),
    (0x46, bytes([0x3C]), 20.0),
    (0x49, bytes([0xFF]), 100.0),
    (0x4A, bytes([0x7F]), 127 * 100 / 255),
    (0x5C, bytes([0x96]), 110.0),
    (0x5E, bytes([0x00, 0xC8]), 10.0),  # 200 / 20
    (0x6F, bytes([0x01, 0x64, 0x00]), 100.0),
    (0x70, bytes([0x01, 0x0C, 0x80, 0x0C, 0x80, 0, 0, 0, 0, 0]), 100.0),  # 0x0C80 = 3200 / 32
]


@pytest.mark.parametrize(("pid", "payload", "expected"), FIXTURES)
def test_decode_fixtures(pid: int, payload: bytes, expected: float) -> None:
    assert decode(pid, payload) == pytest.approx(expected, abs=1e-6)


@pytest.mark.parametrize(("pid", "payload", "expected"), FIXTURES)
def test_fixture_values_are_in_declared_range(pid: int, payload: bytes, expected: float) -> None:
    assert in_range(pid, expected)


def test_decode_tolerates_extra_trailing_bytes() -> None:
    assert decode(0x0D, bytes([0x58, 0xFF, 0xFF])) == 88.0


def test_decode_rejects_short_payload() -> None:
    with pytest.raises(DecodeError):
        decode(0x0C, bytes([0x30]))


def test_decode_rejects_unknown_pid() -> None:
    with pytest.raises(DecodeError):
        decode(0xEE, bytes([0, 0]))


def test_table_has_no_duplicate_pids_or_keys() -> None:
    assert len({p.pid for p in PIDS}) == len(PIDS)
    assert len({p.key for p in PIDS}) == len(PIDS)


def test_tiers_cover_required_fast_pids() -> None:
    fast = set(keys_for_tier(Tier.FAST))
    assert {"rpm", "speed_kph", "throttle_pct", "map_kpa"} <= fast


def test_optional_pids_marked() -> None:
    assert pids.get(0x5C).optional
    assert pids.get(0x70).optional
    assert not pids.get(0x0C).optional


@given(st.sampled_from(PIDS), st.data())
@settings(max_examples=400)
def test_encode_decode_roundtrip_within_resolution(pdef: pids.PidDef, data: st.DataObject) -> None:
    value = data.draw(st.floats(min_value=pdef.min, max_value=pdef.max, allow_nan=False))
    raw = encode(pdef.pid, value)
    assert len(raw) == pdef.length
    back = decode(pdef.pid, raw)
    assert abs(back - value) <= pdef.resolution / 2 + 1e-9
    assert in_range(pdef.pid, back)


@given(st.binary(min_size=10, max_size=10), st.sampled_from(PIDS))
def test_decode_never_raises_on_full_length_bytes(raw: bytes, pdef: pids.PidDef) -> None:
    value = decode(pdef.pid, raw)
    assert value == value  # not NaN
    assert in_range(pdef.pid, value)


# --------------------------------------------------------------------------- support bitmaps
def test_support_bitmap_decode_known_vector() -> None:
    # 0xBE1FA813 is a classic example: PIDs 01,02,03,04,05,06,07,0C,0D,0E,0F,10,11,13,15,1C,1F,20
    supported = decode_support_bitmap(0x00, bytes.fromhex("BE1FA813"))
    assert {0x01, 0x03, 0x04, 0x05, 0x06, 0x07, 0x0C, 0x0D, 0x0E, 0x0F, 0x10, 0x11} <= supported
    assert 0x02 not in supported
    assert 0x20 in supported  # bit 0 of byte D -> next-range indicator


def test_support_bitmap_second_range_offsets() -> None:
    supported = decode_support_bitmap(0x20, bytes.fromhex("80000001"))
    assert supported == {0x21, 0x40}


@given(st.sets(st.integers(min_value=1, max_value=32)))
def test_support_bitmap_roundtrip(offsets: set[int]) -> None:
    pid_set = {0x40 + o for o in offsets}
    raw = encode_support_bitmap(0x40, pid_set)
    assert decode_support_bitmap(0x40, raw) == pid_set


def test_support_bitmap_short_payload() -> None:
    with pytest.raises(DecodeError):
        decode_support_bitmap(0x00, b"\x00\x00")
