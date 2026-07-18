"""Tests for the validator module."""
from __future__ import annotations

from pathlib import Path

import dbckit
from dbckit.model.database import AttributeDefinition, AttributeKind, Database, Issue
from dbckit.model.message import Message
from dbckit.model.signal import ByteOrder, Signal, SignalGroup
from dbckit.validator import validate

FIXTURES = Path(__file__).parent / "fixtures"


def _sig(name, start_bit, length, byte_order=ByteOrder.little_endian) -> Signal:
    return Signal(name=name, start_bit=start_bit, length=length, byte_order=byte_order)


def test_valid_db_no_errors():
    db = dbckit.load(FIXTURES / "simple.dbc")
    errors = [i for i in validate(db) if i.severity == "error"]
    assert errors == []


def test_valid_complex_db_no_errors():
    db = dbckit.load(FIXTURES / "complex.dbc")
    errors = [i for i in validate(db) if i.severity == "error"]
    assert errors == []


def test_signal_exceeds_length():
    sig = _sig("Overflow", start_bit=56, length=16)
    msg = Message(arbitration_id=1, name="M", length=8, signals={"Overflow": sig})
    db = Database(version="", messages={1: msg})
    codes = [i.code for i in validate(db)]
    assert "SIGNAL_EXCEEDS_LENGTH" in codes


def test_signal_overlap():
    sig1 = _sig("S1", 0, 8)
    sig2 = _sig("S2", 4, 8)
    msg = Message(arbitration_id=1, name="M", length=8, signals={"S1": sig1, "S2": sig2})
    db = Database(version="", messages={1: msg})
    codes = [i.code for i in validate(db)]
    assert "SIGNAL_OVERLAP" in codes


def test_no_overlap_adjacent():
    sig1 = _sig("S1", 0, 8)
    sig2 = _sig("S2", 8, 8)
    msg = Message(arbitration_id=1, name="M", length=8, signals={"S1": sig1, "S2": sig2})
    db = Database(version="", messages={1: msg})
    codes = [i.code for i in validate(db)]
    assert "SIGNAL_OVERLAP" not in codes
    assert "SIGNAL_EXCEEDS_LENGTH" not in codes


def test_attr_out_of_range():
    ad = AttributeDefinition(name="X", kind=AttributeKind.INT, object_type="BO_",
                              minimum=0, maximum=100)
    msg = Message(arbitration_id=1, name="M", length=8, attributes={"X": 200})
    db = Database(version="", messages={1: msg}, attributes={"X": ad})
    codes = [i.code for i in validate(db)]
    assert "ATTR_OUT_OF_RANGE" in codes


def test_attr_in_range_no_issue():
    ad = AttributeDefinition(name="X", kind=AttributeKind.INT, object_type="BO_",
                              minimum=0, maximum=100)
    msg = Message(arbitration_id=1, name="M", length=8, attributes={"X": 50})
    db = Database(version="", messages={1: msg}, attributes={"X": ad})
    codes = [i.code for i in validate(db)]
    assert "ATTR_OUT_OF_RANGE" not in codes


def test_attr_undefined():
    msg = Message(arbitration_id=1, name="M", length=8, attributes={"Undefined": 1})
    db = Database(version="", messages={1: msg})
    codes = [i.code for i in validate(db)]
    assert "ATTR_UNDEFINED" in codes


def test_multiple_multiplexers():
    mux1 = Signal(name="Mux1", start_bit=0, length=4, multiplex_indicator="M")
    mux2 = Signal(name="Mux2", start_bit=4, length=4, multiplex_indicator="M")
    msg = Message(arbitration_id=1, name="M", length=8, signals={"Mux1": mux1, "Mux2": mux2})
    db = Database(version="", messages={1: msg})
    codes = [i.code for i in validate(db)]
    assert "MUX_INVALID" in codes


def test_mux_variant_requires_selector_signal():
    variant = Signal(
        name="Variant", start_bit=8, length=8, multiplex_indicator="m0"
    )
    msg = Message(
        arbitration_id=1, name="M", length=8, signals={"Variant": variant}
    )
    codes = [i.code for i in validate(Database(messages={1: msg}))]
    assert "MUX_MISSING_SELECTOR" in codes


def test_mux_selector_value_must_fit_selector_width():
    mux = Signal(name="Mux", start_bit=0, length=2, multiplex_indicator="M")
    variant = Signal(
        name="Variant", start_bit=8, length=8, multiplex_indicator="m4"
    )
    msg = Message(
        arbitration_id=1,
        name="M",
        length=8,
        signals={"Mux": mux, "Variant": variant},
    )
    codes = [i.code for i in validate(Database(messages={1: msg}))]
    assert "MUX_SELECTOR_OUT_OF_RANGE" in codes


def test_mux_same_selector_overlap_is_error():
    mux = Signal(name="Mux", start_bit=0, length=4, multiplex_indicator="M")
    first = Signal(name="First", start_bit=8, length=8, multiplex_indicator="m1")
    second = Signal(name="Second", start_bit=12, length=8, multiplex_indicator="m1")
    msg = Message(
        arbitration_id=1,
        name="M",
        length=8,
        signals={"Mux": mux, "First": first, "Second": second},
    )
    codes = [i.code for i in validate(Database(messages={1: msg}))]
    assert "MUX_OVERLAP" in codes


def test_mux_different_selector_overlap_is_allowed():
    mux = Signal(name="Mux", start_bit=0, length=4, multiplex_indicator="M")
    first = Signal(name="First", start_bit=8, length=8, multiplex_indicator="m1")
    second = Signal(name="Second", start_bit=8, length=8, multiplex_indicator="m2")
    msg = Message(
        arbitration_id=1,
        name="M",
        length=8,
        signals={"Mux": mux, "First": first, "Second": second},
    )
    codes = [i.code for i in validate(Database(messages={1: msg}))]
    assert "MUX_OVERLAP" not in codes


def test_mux_variant_cannot_overlap_common_signal():
    mux = Signal(name="Mux", start_bit=0, length=4, multiplex_indicator="M")
    common = Signal(name="Common", start_bit=8, length=8)
    variant = Signal(
        name="Variant", start_bit=12, length=8, multiplex_indicator="m1"
    )
    msg = Message(
        arbitration_id=1,
        name="M",
        length=8,
        signals={"Mux": mux, "Common": common, "Variant": variant},
    )
    codes = [i.code for i in validate(Database(messages={1: msg}))]
    assert "MUX_OVERLAP" in codes


def test_missing_sender():
    msg = Message(arbitration_id=1, name="M", length=8, senders=["UnknownECU"])
    db = Database(version="", messages={1: msg})
    codes = [i.code for i in validate(db)]
    assert "MISSING_SENDER" in codes


def test_missing_receiver():
    sig = Signal(name="S", start_bit=0, length=8, receivers=["UnknownNode"])
    msg = Message(arbitration_id=1, name="M", length=8, signals={"S": sig})
    db = Database(version="", messages={1: msg})
    codes = [i.code for i in validate(db)]
    assert "MISSING_RECEIVER" in codes


def test_signal_group_message_must_exist():
    group = SignalGroup(name="Dangling", message_id=0x123, signal_names=["Ghost"])
    db = Database(signal_groups=[group])

    issues = validate(db)

    matching = [i for i in issues if i.code == "SIGNAL_GROUP_MISSING_MESSAGE"]
    assert len(matching) == 1
    assert matching[0].severity == "error"
    assert matching[0].location == "signal-group:0x123:Dangling"
    assert validate(db, strict=True) == issues


def test_signal_group_members_must_belong_to_message():
    signal = Signal(name="Present", start_bit=0, length=8)
    msg = Message(
        arbitration_id=0x123,
        name="Message",
        length=8,
        signals={"Present": signal},
    )
    group = SignalGroup(
        name="Members",
        message_id=0x123,
        signal_names=["Present", "Ghost"],
    )

    issues = validate(Database(messages={0x123: msg}, signal_groups=[group]))

    matching = [i for i in issues if i.code == "SIGNAL_GROUP_MISSING_SIGNAL"]
    assert len(matching) == 1
    assert matching[0].severity == "error"
    assert "Ghost" in matching[0].message


def test_valid_signal_group_has_no_group_issues():
    signal = Signal(name="Present", start_bit=0, length=8)
    msg = Message(
        arbitration_id=0x123,
        name="Message",
        length=8,
        signals={"Present": signal},
    )
    group = SignalGroup(
        name="Members", message_id=0x123, signal_names=["Present"]
    )

    codes = [
        i.code
        for i in validate(Database(messages={0x123: msg}, signal_groups=[group]))
    ]

    assert "SIGNAL_GROUP_MISSING_MESSAGE" not in codes
    assert "SIGNAL_GROUP_MISSING_SIGNAL" not in codes


def test_issue_is_pydantic_model():
    db = dbckit.load(FIXTURES / "simple.dbc")
    issues = validate(db)
    for iss in issues:
        assert isinstance(iss, Issue)
        assert isinstance(iss.severity, str)
        assert isinstance(iss.code, str)
        assert isinstance(iss.location, str)
        assert isinstance(iss.message, str)


def test_issue_location_format():
    sig = _sig("Overflow", start_bit=56, length=16)
    msg = Message(arbitration_id=0x1F4, name="M", length=8, signals={"Overflow": sig})
    db = Database(version="", messages={0x1F4: msg})
    issues = validate(db)
    relevant = [i for i in issues if i.code == "SIGNAL_EXCEEDS_LENGTH"]
    assert relevant
    assert "0x1f4" in relevant[0].location or "0x1F4" in relevant[0].location.upper()
    assert "Overflow" in relevant[0].location


def test_invalid_id_standard_frame():
    msg = Message(arbitration_id=0x800, name="M", length=8)  # 11-bit max is 0x7FF
    db = Database(version="", messages={0x800: msg})
    codes = [i.code for i in validate(db)]
    assert "INVALID_ID" in codes


def test_invalid_id_extended_frame():
    msg = Message(arbitration_id=0x20000000, name="M", length=8,
                  is_extended_frame=True)  # 29-bit max is 0x1FFFFFFF
    db = Database(version="", messages={0x20000000: msg})
    codes = [i.code for i in validate(db)]
    assert "INVALID_ID" in codes


def test_valid_standard_id_no_issue():
    msg = Message(arbitration_id=0x7FF, name="M", length=8)
    db = Database(version="", messages={0x7FF: msg})
    codes = [i.code for i in validate(db)]
    assert "INVALID_ID" not in codes


def test_valid_extended_id_no_issue():
    msg = Message(arbitration_id=0x1FFFFFFF, name="M", length=8, is_extended_frame=True)
    db = Database(version="", messages={0x1FFFFFFF: msg})
    codes = [i.code for i in validate(db)]
    assert "INVALID_ID" not in codes


def test_extended_fixture_no_errors():
    db = dbckit.load(FIXTURES / "extended.dbc")
    errors = [i for i in validate(db) if i.severity == "error"]
    assert errors == []


def test_strict_mode_warnings_become_errors():
    msg = Message(arbitration_id=1, name="M", length=8, senders=["Ghost"])
    db = Database(version="", messages={1: msg})
    normal = validate(db)
    strict = validate(db, strict=True)
    warnings = [i for i in normal if i.severity == "warning"]
    assert warnings
    strict_errors = [i for i in strict if i.severity == "error"]
    assert len(strict_errors) >= len(warnings)
