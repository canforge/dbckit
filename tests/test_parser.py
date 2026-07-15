"""Tests for the DBC parser."""
from __future__ import annotations

import re
from pathlib import Path

import pytest

import dbckit
from dbckit.model.signal import ByteOrder

FIXTURES = Path(__file__).parent / "fixtures"

MINIMAL_DBC = """\
VERSION ""
NS_ :
BS_ :
BU_ : ECU
BO_ 100 ExistingMessage: 8 ECU
 SG_ ExistingSignal : 0|8@1+ (1,0) [0|255] "" ECU
"""


def test_parse_version():
    db = dbckit.parse('VERSION "1.2.3"\n\nNS_ :\n\nBS_ :\n\nBU_ :\n')
    assert db.version == "1.2.3"


def test_parse_simple_fixture():
    db = dbckit.load(FIXTURES / "simple.dbc")
    assert db.version == "1.0"
    assert "ECU1" in db.nodes
    assert "ECU2" in db.nodes
    assert "GW" in db.nodes


def test_parse_messages():
    db = dbckit.load(FIXTURES / "simple.dbc")
    assert 500 in db.messages
    msg = db.messages[500]
    assert msg.name == "EngineData"
    assert msg.length == 8
    assert "EngineSpeed" in msg.signals
    assert "EngineTemp" in msg.signals
    assert "IgnitionStatus" in msg.signals


def test_parse_signal_properties():
    db = dbckit.load(FIXTURES / "simple.dbc")
    sig = db.messages[500].signals["EngineSpeed"]
    assert sig.start_bit == 0
    assert sig.length == 16
    assert sig.byte_order == ByteOrder.little_endian
    assert sig.is_signed is False
    assert sig.factor == pytest.approx(0.1)
    assert sig.offset == pytest.approx(0.0)
    assert sig.unit == "rpm"
    assert "ECU2" in sig.receivers
    assert "GW" in sig.receivers


def test_parse_signed_signal():
    db = dbckit.load(FIXTURES / "simple.dbc")
    sig = db.messages[768].signals["TransmissionTemp"]
    assert sig.is_signed is True
    assert sig.factor == pytest.approx(0.5)
    assert sig.offset == pytest.approx(-50.0)


def test_parse_comments():
    db = dbckit.load(FIXTURES / "simple.dbc")
    assert db.messages[500].comment == "Engine status message"
    assert db.messages[500].signals["EngineSpeed"].comment == "Current engine speed in RPM"
    assert db.nodes["ECU1"].comment == "Engine control unit"


def test_parse_attributes():
    db = dbckit.load(FIXTURES / "simple.dbc")
    assert "GenMsgCycleTime" in db.attributes
    assert db.messages[500].attributes.get("GenMsgCycleTime") == 100


def test_parse_value_descriptions():
    db = dbckit.load(FIXTURES / "simple.dbc")
    vt = db.messages[500].signals["IgnitionStatus"].value_table
    assert vt is not None
    assert vt.values[0] == "Off"
    assert vt.values[1] == "On"


def test_parse_complex_fixture():
    db = dbckit.load(FIXTURES / "complex.dbc")
    assert db.version == "2.0"
    assert len(db.messages) == 3
    assert 100 in db.messages
    assert 200 in db.messages
    assert 300 in db.messages


def test_parse_multiplexed_signals():
    db = dbckit.load(FIXTURES / "complex.dbc")
    msg = db.messages[200]
    assert msg.signals["MuxSelector"].multiplex_indicator == "M"
    assert msg.signals["LightStatus"].multiplex_indicator == "m0"
    assert msg.signals["DoorStatus"].multiplex_indicator == "m1"


def test_extended_mux_raises():
    dbc = """\
VERSION ""
NS_ :
BS_ :
BU_ : ECU
BO_ 100 ExtendedMux: 8 ECU
 SG_ Selector M : 0|4@1+ (1,0) [0|15] "" ECU
 SG_ Variant m0M : 4|4@1+ (1,0) [0|15] "" ECU
"""
    error = "Extended multiplexing indicator 'm0M'.*not supported"
    with pytest.raises(Exception, match=error):
        dbckit.parse(dbc)


def test_extended_mux_section_raises_clear_error():
    dbc = f"""\
{MINIMAL_DBC}
SG_MUL_VAL_ 100 ExistingSignal ExistingSignal 0-1;
"""
    error = (
        "Unsupported DBC construct 'SG_MUL_VAL_' at line 8: "
        "extended multiplexing ranges are not supported"
    )
    with pytest.raises(ValueError, match=re.escape(error)):
        dbckit.parse(dbc)


@pytest.mark.parametrize(
    ("entry", "error"),
    [
        (
            'CM_ BO_ 999 "comment";',
            "CM_ references unknown message arbitration_id=0x3e7",
        ),
        (
            'CM_ SG_ 100 MissingSignal "comment";',
            "CM_ references unknown signal 'MissingSignal' in message arbitration_id=0x64",
        ),
        (
            'CM_ SG_ 999 MissingSignal "comment";',
            "CM_ references unknown message arbitration_id=0x3e7",
        ),
        (
            'CM_ EV_ MissingEnvvar "comment";',
            "CM_ references unknown environment variable 'MissingEnvvar'",
        ),
        (
            'BA_ "Attr" BO_ 999 1;',
            "BA_ references unknown message arbitration_id=0x3e7",
        ),
        (
            'BA_ "Attr" SG_ 100 MissingSignal 1;',
            "BA_ references unknown signal 'MissingSignal' in message arbitration_id=0x64",
        ),
        (
            'BA_ "Attr" SG_ 999 MissingSignal 1;',
            "BA_ references unknown message arbitration_id=0x3e7",
        ),
        (
            'BA_ "Attr" EV_ MissingEnvvar 1;',
            "BA_ references unknown environment variable 'MissingEnvvar'",
        ),
        (
            'VAL_ 100 MissingSignal 0 "Off";',
            "VAL_ references unknown signal 'MissingSignal' in message arbitration_id=0x64",
        ),
        (
            'VAL_ 999 MissingSignal 0 "Off";',
            "VAL_ references unknown message arbitration_id=0x3e7",
        ),
        (
            "SIG_VALTYPE_ 100 MissingSignal : 1;",
            "SIG_VALTYPE_ references unknown signal 'MissingSignal' in message "
            "arbitration_id=0x64",
        ),
        (
            "SIG_VALTYPE_ 999 MissingSignal : 1;",
            "SIG_VALTYPE_ references unknown message arbitration_id=0x3e7",
        ),
        (
            "ENVVAR_DATA_ MissingEnvvar : 8;",
            "ENVVAR_DATA_ references unknown environment variable 'MissingEnvvar'",
        ),
    ],
)
def test_dangling_reference_raises(entry: str, error: str):
    with pytest.raises(Exception, match=re.escape(error)):
        dbckit.parse(f"{MINIMAL_DBC}\n{entry}\n")


def test_parse_big_endian_signal():
    db = dbckit.load(FIXTURES / "complex.dbc")
    sig = db.messages[300].signals["FuelPressure"]
    assert sig.byte_order == ByteOrder.big_endian


def test_parse_signal_group():
    db = dbckit.load(FIXTURES / "complex.dbc")
    assert len(db.signal_groups) == 1
    sg = db.signal_groups[0]
    assert sg.name == "DynamicsGroup"
    assert "Speed" in sg.signal_names


def test_parse_val_table():
    db = dbckit.load(FIXTURES / "complex.dbc")
    assert "IgnitionStates" in db.value_tables
    vt = db.value_tables["IgnitionStates"]
    assert vt.values[0] == "Off"
    assert vt.values[3] == "Start"


def test_parse_enum_attribute():
    db = dbckit.load(FIXTURES / "complex.dbc")
    ad = db.attributes["GenMsgSendType"]
    assert ad.kind.value == "ENUM"
    assert "Cyclic" in ad.values


def test_parse_attribute_definition_scope():
    db = dbckit.load(FIXTURES / "simple.dbc")
    ad = db.attributes["GenMsgCycleTime"]
    assert ad.object_type == "BO_"
    assert ad.minimum is not None
    assert ad.maximum is not None


def test_parse_db_level_attribute():
    db = dbckit.load(FIXTURES / "complex.dbc")
    assert "DBVersion" in db.attribute_values or "DBVersion" in db.attributes


def test_roundtrip_simple():
    db1 = dbckit.load(FIXTURES / "simple.dbc")
    dbc_str = dbckit.dump(db1)
    db2 = dbckit.parse(dbc_str)
    assert set(db2.messages.keys()) == set(db1.messages.keys())
    for arb_id in db1.messages:
        assert set(db2.messages[arb_id].signals.keys()) == set(db1.messages[arb_id].signals.keys())


def test_roundtrip_complex():
    db1 = dbckit.load(FIXTURES / "complex.dbc")
    dbc_str = dbckit.dump(db1)
    db2 = dbckit.parse(dbc_str)
    assert set(db2.messages.keys()) == set(db1.messages.keys())
    for arb_id in db1.messages:
        m1 = db1.messages[arb_id]
        m2 = db2.messages[arb_id]
        assert m1.name == m2.name
        assert m1.length == m2.length
        for sig_name in m1.signals:
            s1 = m1.signals[sig_name]
            s2 = m2.signals[sig_name]
            assert s1.start_bit == s2.start_bit
            assert s1.length == s2.length
            assert s1.factor == pytest.approx(s2.factor)
            assert s1.offset == pytest.approx(s2.offset)
