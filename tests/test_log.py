"""Tests for structural frame decoding and log-reader discovery."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

import dbckit
import dbckit.operations.log as log_module
from dbckit.model.database import AttributeDefinition, AttributeKind, Database
from dbckit.model.message import Message
from dbckit.model.signal import Signal

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


def _j1939_message(
    arbitration_id: int,
    name: str,
    *,
    attributes: dict[str, object] | None = None,
) -> Message:
    return Message(
        arbitration_id=arbitration_id,
        name=name,
        length=8,
        is_extended_frame=True,
        attributes=attributes or {},
        signals={
            "Value": Signal(name="Value", start_bit=0, length=8),
        },
    )


def _j1939_frame(
    arbitration_id: int = 0x0CF004AB,
    *,
    timestamp: float = 2.5,
    channel: int | None = 4,
    is_extended_frame: bool = True,
) -> MetadataFrame:
    return MetadataFrame(
        timestamp=timestamp,
        arbitration_id=arbitration_id,
        data=b"\x2a" + b"\x00" * 7,
        channel=channel,
        is_extended_frame=is_extended_frame,
    )


def test_decode_frames_accepts_plain_dataclass(simple_db):
    decoded = list(dbckit.decode_frames(simple_db, [_engine_frame()]))

    assert len(decoded) == 1
    assert decoded[0].signals["EngineSpeed"] == pytest.approx(100.0)
    assert decoded[0].message_arbitration_id == 500
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


def test_decode_frames_j1939_matches_derived_pgn_and_decodes_resolved_id():
    db = Database(
        messages={
            0x18F00401: _j1939_message(0x18F00401, "EngineData"),
        }
    )

    decoded = list(dbckit.decode_frames(db, [_j1939_frame()], match="j1939"))

    assert len(decoded) == 1
    result = decoded[0]
    assert isinstance(result, dbckit.DecodedFrame)
    assert result.arbitration_id == 0x0CF004AB
    assert result.message_arbitration_id == 0x18F00401
    assert result.signals == {"Value": 42.0}
    assert result.channel == 4
    assert result.is_extended_frame is True


def test_decode_frames_j1939_accepts_29_bit_id_shape_without_optional_metadata():
    db = Database(
        messages={
            0x18F00401: _j1939_message(0x18F00401, "EngineData"),
        }
    )
    frame = ForeignFrame(
        timestamp=1.0,
        arbitration_id=0x0CF004AB,
        data=b"\x2a" + b"\x00" * 7,
    )

    result = list(dbckit.decode_frames(db, [frame], match="j1939"))[0]

    assert isinstance(result, dbckit.DecodedFrame)
    assert result.is_extended_frame is False


def test_decode_frames_j1939_skips_standard_frames_and_messages():
    db = Database(
        messages={
            0x400: Message(
                arbitration_id=0x400,
                name="Standard",
                length=8,
                signals={"Value": Signal(name="Value", start_bit=0, length=8)},
            ),
        }
    )

    assert list(
        dbckit.decode_frames(
            db,
            [ForeignFrame(timestamp=0.0, arbitration_id=0x400, data=b"\x2a")],
            match="j1939",
        )
    ) == []


def test_decode_frames_auto_requires_attribute_marker():
    db = Database(
        messages={
            0x18F00401: _j1939_message(0x18F00401, "EngineData"),
        }
    )

    assert list(dbckit.decode_frames(db, [_j1939_frame()], match="auto")) == []


def test_decode_frames_auto_uses_pgn_attribute_only_as_detection_signal():
    db = Database(
        messages={
            0x18F00401: _j1939_message(
                0x18F00401,
                "EngineData",
                attributes={"PGN": 1},
            ),
        }
    )

    result = list(dbckit.decode_frames(db, [_j1939_frame()], match="auto"))[0]

    assert isinstance(result, dbckit.DecodedFrame)
    assert result.message_arbitration_id == 0x18F00401


@pytest.mark.parametrize(
    ("attribute_values", "message_attributes"),
    [
        ({"ProtocolType": "SAE J1939"}, {}),
        ({}, {"ProtocolType": "J1939PG"}),
    ],
)
def test_decode_frames_auto_accepts_database_or_message_protocol_marker(
    attribute_values,
    message_attributes,
):
    db = Database(
        attribute_values=attribute_values,
        messages={
            0x18F00401: _j1939_message(
                0x18F00401,
                "EngineData",
                attributes=message_attributes,
            ),
        },
    )

    result = list(dbckit.decode_frames(db, [_j1939_frame()], match="auto"))[0]

    assert isinstance(result, dbckit.DecodedFrame)


def test_decode_frames_auto_resolves_numeric_protocol_enum_marker():
    db = Database(
        attributes={
            "ProtocolType": AttributeDefinition(
                name="ProtocolType",
                kind=AttributeKind.ENUM,
                values=["CAN", "J1939"],
            ),
        },
        attribute_values={"ProtocolType": 1},
        messages={
            0x18F00401: _j1939_message(0x18F00401, "EngineData"),
        },
    )

    result = list(dbckit.decode_frames(db, [_j1939_frame()], match="auto"))[0]

    assert isinstance(result, dbckit.DecodedFrame)


def test_decode_frames_auto_rejects_protocol_value_that_does_not_identify_j1939():
    db = Database(
        attribute_values={"ProtocolType": "not-j1939"},
        messages={
            0x18F00401: _j1939_message(0x18F00401, "EngineData"),
        },
    )

    assert list(dbckit.decode_frames(db, [_j1939_frame()], match="auto")) == []


def test_decode_frames_auto_ignores_invalid_pgn_marker():
    db = Database(
        messages={
            0x18F00401: _j1939_message(
                0x18F00401,
                "EngineData",
                attributes={"PGN": 0x40000},
            ),
        }
    )

    assert list(dbckit.decode_frames(db, [_j1939_frame()], match="auto")) == []


def test_decode_frames_auto_does_not_detect_from_vframeformat_marker():
    db = dbckit.load(FIXTURES / "css_electronics_extended.dbc")
    message_id = next(
        arbitration_id
        for arbitration_id, message in db.messages.items()
        if message.is_extended_frame
    )
    source_variant = (message_id & ~0xFF) | ((message_id + 1) & 0xFF)
    frame = _j1939_frame(arbitration_id=source_variant)

    assert list(dbckit.decode_frames(db, [frame], match="auto")) == []


def test_decode_frames_auto_prefers_exact_id_over_ambiguous_pgn():
    db = Database(
        messages={
            0x18F00401: _j1939_message(0x18F00401, "Exact", attributes={"PGN": 1}),
            0x18F00402: _j1939_message(0x18F00402, "Other"),
        }
    )
    frame = _j1939_frame(arbitration_id=0x18F00401)

    result = list(dbckit.decode_frames(db, [frame], match="auto"))[0]

    assert isinstance(result, dbckit.DecodedFrame)
    assert result.message_arbitration_id == 0x18F00401


def test_decode_frames_returns_ordered_ambiguous_j1939_match():
    db = Database(
        messages={
            0x18F00402: _j1939_message(0x18F00402, "First"),
            0x18F00401: _j1939_message(0x18F00401, "Second"),
        }
    )

    results = list(dbckit.decode_frames(db, [_j1939_frame()], match="j1939"))

    assert len(results) == 1
    ambiguous = results[0]
    assert isinstance(ambiguous, dbckit.AmbiguousFrameMatch)
    assert ambiguous.candidate_message_ids == [0x18F00402, 0x18F00401]
    assert ambiguous.timestamp == pytest.approx(2.5)
    assert ambiguous.arbitration_id == 0x0CF004AB
    assert ambiguous.raw == b"\x2a" + b"\x00" * 7
    assert ambiguous.channel == 4
    assert ambiguous.is_extended_frame is True


def test_decode_frames_j1939_skips_unknown_pgn():
    db = Database(
        messages={
            0x18F00401: _j1939_message(0x18F00401, "EngineData"),
        }
    )

    assert list(
        dbckit.decode_frames(
            db,
            [_j1939_frame(arbitration_id=0x18F00501)],
            match="j1939",
        )
    ) == []


def test_decode_frames_rejects_unknown_match_mode(simple_db):
    with pytest.raises(ValueError, match="match must be"):
        dbckit.decode_frames(simple_db, [], match="other")  # type: ignore[arg-type]


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


def test_decode_log_propagates_match_mode(monkeypatch, tmp_path):
    db = Database(
        messages={
            0x18F00401: _j1939_message(0x18F00401, "EngineData"),
        }
    )
    monkeypatch.setitem(
        log_module._REGISTERED_READERS,
        ".j1939",
        StaticReader([_j1939_frame()]),
    )

    result = list(
        dbckit.decode_log(
            db,
            tmp_path / "trace.j1939",
            match="j1939",
        )
    )[0]

    assert isinstance(result, dbckit.DecodedFrame)
    assert result.message_arbitration_id == 0x18F00401


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
