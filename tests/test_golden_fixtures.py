"""Golden tests against fixtures sourced from established CAN projects."""
from __future__ import annotations

from pathlib import Path

import pytest

import dbckit

GOLDEN = Path(__file__).parent / "fixtures" / "golden"


def test_opendbc_fixture_semantic_roundtrip():
    original = dbckit.load(GOLDEN / "opendbc_comma_body.dbc")
    reparsed = dbckit.parse(dbckit.dump(original))

    assert len(original.messages) == 14
    assert reparsed.version == original.version
    assert reparsed.messages == original.messages


def test_python_can_real_asc_trace():
    frames = list(dbckit.AscReader().read(GOLDEN / "python_can_logfile.asc"))

    assert len(frames) == 10
    assert [frame.arbitration_id for frame in frames[:4]] == [0x18EBFF00] * 4
    assert [frame.arbitration_id for frame in frames[4:6]] == [0x6F9, 0x6F8]
    assert [frame.arbitration_id for frame in frames[6:]] == [0x18EBFF00] * 4
    assert frames[4].timestamp == pytest.approx(17.876708)
    assert frames[4].data == bytes.fromhex("05 0C 00 00 00 00 00 00")
    assert frames[5].data == bytes.fromhex("FF 00 0C FE 00 00 00 00")
