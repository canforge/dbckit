"""Tests for structural frame decoding and log-reader discovery."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

import dbckit
import dbckit.operations.log as log_module

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def simple_db():
    return dbckit.load(FIXTURES / "simple.dbc")


@pytest.fixture
def complex_db():
    return dbckit.load(FIXTURES / "complex.dbc")


@pytest.fixture(autouse=True)
def isolated_reader_state(monkeypatch):
    monkeypatch.setattr(log_module, "_REGISTERED_READERS", {})
    monkeypatch.setattr(log_module, "_ENTRY_POINTS", None)
    monkeypatch.setattr(log_module, "_ENTRY_POINT_READERS", {})


@dataclass
class ForeignFrame:
    timestamp: float
    arbitration_id: int
    data: bytes


@dataclass
class MetadataFrame:
    timestamp: float
    arbitration_id: int
    data: bytes
    channel: int | None
    is_extended_frame: bool


class StaticReader:
    def __init__(self, frames):
        self.frames = frames

    def read(self, path: Path):
        yield from self.frames


class FakeEntryPoint:
    def __init__(self, name: str, value: str, loaded: Any):
        self.name = name
        self.value = value
        self.loaded = loaded
        self.load_count = 0

    def load(self):
        self.load_count += 1
        if isinstance(self.loaded, Exception):
            raise self.loaded
        return self.loaded


def _engine_frame(timestamp: float = 1.25) -> ForeignFrame:
    return ForeignFrame(
        timestamp=timestamp,
        arbitration_id=500,
        data=bytes([0xE8, 0x03, 0, 0, 0, 0, 0, 0]),
    )


def test_decode_frames_accepts_plain_dataclass(simple_db):
    decoded = list(dbckit.decode_frames(simple_db, [_engine_frame()]))

    assert len(decoded) == 1
    assert decoded[0].signals["EngineSpeed"] == pytest.approx(100.0)
    assert decoded[0].channel is None
    assert decoded[0].is_extended_frame is False


def test_decode_frames_skips_unknown_ids(simple_db):
    unknown = ForeignFrame(timestamp=0.0, arbitration_id=0x7FF, data=b"\x00")

    assert list(dbckit.decode_frames(simple_db, [unknown])) == []


def test_decode_frames_filters_mux_variants(complex_db):
    payload = dbckit.encode_frame(
        complex_db,
        200,
        {"MuxSelector": 1.0, "DoorStatus": 42.0},
    )
    frame = ForeignFrame(timestamp=0.5, arbitration_id=200, data=payload)

    decoded = list(dbckit.decode_frames(complex_db, [frame]))[0]

    assert decoded.signals["DoorStatus"] == pytest.approx(42.0)
    assert "LightStatus" not in decoded.signals
    assert "WindowStatus" not in decoded.signals


def test_decode_frames_resolves_value_tables(simple_db):
    frame = ForeignFrame(
        timestamp=0.5,
        arbitration_id=500,
        data=b"\x00\x00\x00\x01" + b"\x00" * 4,
    )

    decoded = list(dbckit.decode_frames(simple_db, [frame]))[0]

    assert decoded.signals["IgnitionStatus"] == "On"


def test_decode_frames_preserves_optional_metadata(simple_db):
    source = _engine_frame()
    frame = MetadataFrame(
        timestamp=source.timestamp,
        arbitration_id=source.arbitration_id,
        data=source.data,
        channel=3,
        is_extended_frame=True,
    )

    decoded = list(dbckit.decode_frames(simple_db, [frame]))[0]

    assert decoded.channel == 3
    assert decoded.is_extended_frame is True


def test_asc_reader_preserves_channel_and_extended_flag(tmp_path):
    path = tmp_path / "trace.asc"
    path.write_text(
        "0.001000 2  1ABCDEFX  Rx   d 2 01 02\n",
        encoding="utf-8",
    )

    frame = list(dbckit.AscReader().read(path))[0]

    assert frame.channel == 2
    assert frame.is_extended_frame is True
    assert frame.arbitration_id == 0x1ABCDEF


def test_unknown_extension_lists_available_readers(simple_db, monkeypatch, tmp_path):
    entry_point = FakeEntryPoint("trc", "logkit:trc_reader", lambda: StaticReader([]))
    monkeypatch.setattr(
        log_module.metadata,
        "entry_points",
        lambda *, group: [entry_point],
    )
    dbckit.register_reader("custom", StaticReader([]))

    with pytest.raises(ValueError) as exc_info:
        dbckit.decode_log(simple_db, tmp_path / "trace.unknown")

    message = str(exc_info.value)
    assert ".asc" in message
    assert ".custom" in message
    assert ".trc" in message


def test_format_override_ignores_path_suffix(simple_db, monkeypatch, tmp_path):
    entry_point = FakeEntryPoint(
        "trc",
        "logkit:trc_reader",
        lambda: StaticReader([_engine_frame()]),
    )
    monkeypatch.setattr(
        log_module.metadata,
        "entry_points",
        lambda *, group: [entry_point],
    )

    decoded = list(
        dbckit.decode_log(simple_db, tmp_path / "trace.bin", format="TRC")
    )

    assert decoded[0].signals["EngineSpeed"] == pytest.approx(100.0)


def test_entry_points_are_discovered_once_and_selected_reader_is_cached(
    simple_db,
    monkeypatch,
    tmp_path,
):
    trc_factory_calls = 0

    def trc_factory():
        nonlocal trc_factory_calls
        trc_factory_calls += 1
        return StaticReader([_engine_frame()])

    trc = FakeEntryPoint("trc", "logkit:trc_reader", trc_factory)
    blf = FakeEntryPoint("blf", "logkit:blf_reader", lambda: StaticReader([]))
    discovery_calls = 0

    def fake_entry_points(*, group):
        nonlocal discovery_calls
        assert group == "dbckit.readers"
        discovery_calls += 1
        return [trc, blf]

    monkeypatch.setattr(log_module.metadata, "entry_points", fake_entry_points)

    list(dbckit.decode_log(simple_db, tmp_path / "one.trc"))
    list(dbckit.decode_log(simple_db, tmp_path / "two.trc"))

    assert discovery_calls == 1
    assert trc.load_count == 1
    assert trc_factory_calls == 1
    assert blf.load_count == 0


def test_explicit_registration_precedes_entry_point(simple_db, monkeypatch, tmp_path):
    entry_point = FakeEntryPoint(
        "trc",
        "broken:reader",
        ImportError("must not load"),
    )
    monkeypatch.setattr(
        log_module.metadata,
        "entry_points",
        lambda *, group: [entry_point],
    )
    dbckit.register_reader("trc", StaticReader([_engine_frame()]))

    decoded = list(dbckit.decode_log(simple_db, tmp_path / "trace.trc"))

    assert len(decoded) == 1
    assert entry_point.load_count == 0


def test_duplicate_entry_points_fail_clearly(simple_db, monkeypatch, tmp_path):
    entry_points = [
        FakeEntryPoint("trc", "first:reader", lambda: StaticReader([])),
        FakeEntryPoint("TRC", "second:reader", lambda: StaticReader([])),
    ]
    monkeypatch.setattr(
        log_module.metadata,
        "entry_points",
        lambda *, group: entry_points,
    )

    with pytest.raises(ValueError, match="Multiple dbckit.readers.*'.trc'"):
        dbckit.decode_log(simple_db, tmp_path / "trace.trc")


def test_broken_selected_entry_point_fails_clearly(simple_db, monkeypatch, tmp_path):
    entry_point = FakeEntryPoint("trc", "broken:reader", ImportError("missing"))
    monkeypatch.setattr(
        log_module.metadata,
        "entry_points",
        lambda *, group: [entry_point],
    )

    with pytest.raises(RuntimeError, match="Failed to load dbckit reader for '.trc'"):
        dbckit.decode_log(simple_db, tmp_path / "trace.trc")
