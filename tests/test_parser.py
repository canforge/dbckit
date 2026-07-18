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

EXTENDED_ID = 0x18FF1234
FLAGGED_EXTENDED_ID = EXTENDED_ID | 0x80000000
MISSING_ID = 999
FLAGGED_MISSING_ID = MISSING_ID | 0x80000000


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


def test_bare_extended_mux_namespace_token_round_trips():
    dbc = """\
VERSION ""
NS_ :
    NS_DESC_
    SG_MUL_VAL_ // namespace capability token
    CM_
BS_ :
BU_ : ECU
"""

    db = dbckit.parse(dbc)
    assert db.ns_values == ["NS_DESC_", "SG_MUL_VAL_", "CM_"]

    reparsed = dbckit.parse(dbckit.dump(db))
    assert reparsed.ns_values == db.ns_values


def test_inline_namespace_tokens_round_trip():
    dbc = """\
VERSION ""
NS_ : NS_DESC_ CM_ BA_DEF_ SG_MUL_VAL_
BS_ :
BU_ :
"""

    db = dbckit.parse(dbc)
    assert db.ns_values == ["NS_DESC_", "CM_", "BA_DEF_", "SG_MUL_VAL_"]

    reparsed = dbckit.parse(dbckit.dump(db))
    assert reparsed.ns_values == db.ns_values


def test_value_table_namespace_token_is_not_misclassified():
    dbc = """\
VERSION ""
NS_ :
    VAL_TABLE_
    NS_DESC_
BS_ :
BU_ :
"""

    db = dbckit.parse(dbc)
    assert db.ns_values == ["VAL_TABLE_", "NS_DESC_"]


def test_three_line_split_value_table_after_namespace_round_trips():
    dbc = """\
VERSION ""
NS_ :
    NS_DESC_
    CM_
VAL_TABLE_
SwitchStates
0 "Off" 1 "On";
BS_ :
BU_ :
"""

    db = dbckit.parse(dbc)
    assert db.ns_values == ["NS_DESC_", "CM_"]
    assert db.value_tables["SwitchStates"].values == {0: "Off", 1: "On"}

    reparsed = dbckit.parse(dbckit.dump(db))
    assert reparsed.ns_values == db.ns_values
    assert reparsed.value_tables == db.value_tables


def test_two_line_split_value_table_after_namespace_round_trips():
    dbc = """\
VERSION ""
NS_ :
    NS_DESC_
    CM_
VAL_TABLE_ SwitchStates
0 "Off" 1 "On";
BS_ :
BU_ :
"""

    db = dbckit.parse(dbc)
    assert db.ns_values == ["NS_DESC_", "CM_"]
    assert db.value_tables["SwitchStates"].values == {0: "Off", 1: "On"}

    reparsed = dbckit.parse(dbckit.dump(db))
    assert reparsed.ns_values == db.ns_values
    assert reparsed.value_tables == db.value_tables


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


def test_skip_extended_mux_records_ordered_degrading_diagnostics():
    dbc = (
        '\ufeffVERSION ""\r\n'
        "NS_ :\r\n"
        "BS_ :\r\n"
        "BU_ : ECU\r\n"
        "BO_ 100 ExtendedMux: 8 ECU\r\n"
        '\tSG_ Kept : 0|8@1+ (1,0) [0|255] "" ECU\r\n'
        '\tSG_ Variant m0M : 8|8@1+ (1,0) [0|255] "" ECU\r\n'
        'CM_ SG_ 100 Missing "dangling";\r\n'
        "SG_MUL_VAL_ 100 Kept Kept 0-1;\r\n"
    )

    db = dbckit.parse(dbc, on_unsupported="skip")

    assert list(db.messages[100].signals) == ["Kept"]
    assert [diagnostic.construct for diagnostic in db.parse_diagnostics] == [
        "SG_",
        "CM_",
        "SG_MUL_VAL_",
    ]
    assert [diagnostic.line for diagnostic in db.parse_diagnostics] == [7, 8, 9]
    assert db.parse_diagnostics[0].message_id == 100
    assert db.parse_diagnostics[0].signal_name == "Variant"
    assert db.parse_diagnostics[0].effect == "decode_degraded"
    assert db.parse_diagnostics[1].effect == "cosmetic"
    assert db.parse_diagnostics[2].effect == "decode_degraded"
    assert db.decode_safe is False
    assert db.message_decode_safety == {100: False}
    assert db.message_decode_safe(100) is False
    assert db.is_message_decode_safe(100) is False


def test_skip_extended_mux_diagnostics_are_parse_metadata_only():
    dbc = f"""\
{MINIMAL_DBC}
SG_MUL_VAL_ 100 ExistingSignal ExistingSignal 0-1;
"""

    parsed = dbckit.parse(dbc, on_unsupported="skip")
    dumped = dbckit.dump(parsed)
    reparsed = dbckit.parse(dumped)

    assert parsed.parse_diagnostics
    assert "SG_MUL_VAL_" not in dumped
    assert reparsed.parse_diagnostics == []
    assert reparsed.messages == parsed.messages
    assert parsed.diff(reparsed).is_empty


def test_skip_refuses_unknown_or_unbounded_syntax():
    with pytest.raises(Exception):
        dbckit.parse(f"{MINIMAL_DBC}\nUNKNOWN_SECTION_ 100;\n", on_unsupported="skip")

    with pytest.raises(ValueError, match="Unsupported DBC construct 'SG_MUL_VAL_'"):
        dbckit.parse(
            f"{MINIMAL_DBC}\nSG_MUL_VAL_ cannot_be_safely_scoped;\n",
            on_unsupported="skip",
        )


@pytest.mark.parametrize("policy", ["", "collect", "ignore"])
def test_invalid_unsupported_policy_raises_before_parsing(policy: str):
    with pytest.raises(
        ValueError,
        match="on_unsupported must be 'raise' or 'skip'",
    ):
        dbckit.parse("not valid DBC", on_unsupported=policy)


def test_extended_frame_references_use_clean_arbitration_id():
    dbc = f"""\
VERSION ""
NS_ :
BS_ :
BU_ : ECU1 ECU2
BO_ {FLAGGED_EXTENDED_ID} ExtendedMessage: 8 ECU1
 SG_ State : 0|8@1+ (1,0) [0|255] "" ECU2
BO_TX_BU_ {FLAGGED_EXTENDED_ID} : ECU1,ECU2;
SIG_GROUP_ {FLAGGED_EXTENDED_ID} Status 1 : State;
CM_ BO_ {FLAGGED_EXTENDED_ID} "message comment";
CM_ SG_ {FLAGGED_EXTENDED_ID} State "signal comment";
BA_DEF_ BO_ "GenMsgCycleTime" INT 0 1000;
BA_DEF_ BO_ "MessageAttr" INT 0 10;
BA_DEF_ SG_ "SignalAttr" INT 0 10;
BA_ "GenMsgCycleTime" BO_ {FLAGGED_EXTENDED_ID} 25;
BA_ "MessageAttr" BO_ {FLAGGED_EXTENDED_ID} 7;
BA_ "SignalAttr" SG_ {FLAGGED_EXTENDED_ID} State 9;
VAL_ {FLAGGED_EXTENDED_ID} State 0 "Off" 1 "On";
SIG_VALTYPE_ {FLAGGED_EXTENDED_ID} State : 1;
"""

    db = dbckit.parse(dbc)

    assert list(db.messages) == [EXTENDED_ID]
    msg = db.messages[EXTENDED_ID]
    assert msg.arbitration_id == EXTENDED_ID
    assert msg.is_extended_frame is True
    assert msg.senders == ["ECU1", "ECU2"]
    assert msg.comment == "message comment"
    assert msg.cycle_time == 25
    assert msg.attributes["GenMsgCycleTime"] == 25
    assert msg.attributes["MessageAttr"] == 7

    sig = msg.signals["State"]
    assert sig.comment == "signal comment"
    assert sig.attributes["SignalAttr"] == 9
    assert sig.signal_type == 1
    assert sig.value_table is not None
    assert sig.value_table.values == {0: "Off", 1: "On"}

    assert len(db.signal_groups) == 1
    group = db.signal_groups[0]
    assert group.message_id == EXTENDED_ID
    assert group.signal_names == ["State"]


@pytest.mark.parametrize(
    ("entry", "section"),
    [
        (f'CM_ BO_ {FLAGGED_MISSING_ID} "comment";', "CM_"),
        (f'BA_ "Attr" BO_ {FLAGGED_MISSING_ID} 1;', "BA_"),
        (f'VAL_ {FLAGGED_MISSING_ID} MissingSignal 0 "Off";', "VAL_"),
        (
            f"SIG_VALTYPE_ {FLAGGED_MISSING_ID} MissingSignal : 1;",
            "SIG_VALTYPE_",
        ),
    ],
)
def test_flagged_dangling_reference_reports_clean_id(entry: str, section: str):
    error = f"{section} references unknown message arbitration_id={MISSING_ID:#x}"
    with pytest.raises(ValueError, match=re.escape(error)):
        dbckit.parse(f"{MINIMAL_DBC}\n{entry}\n")


def test_flagged_forward_reference_preserves_strict_source_order():
    dbc = f"""\
VERSION ""
NS_ :
BS_ :
BU_ : ECU
CM_ BO_ {FLAGGED_EXTENDED_ID} "defined later";
BO_ {FLAGGED_EXTENDED_ID} ExtendedMessage: 8 ECU
"""
    error = f"CM_ references unknown message arbitration_id={EXTENDED_ID:#x}"
    with pytest.raises(ValueError, match=re.escape(error)):
        dbckit.parse(dbc)


def test_flagged_unknown_non_strict_references_remain_non_raising():
    dbc = f"""\
{MINIMAL_DBC}
BO_TX_BU_ {FLAGGED_MISSING_ID} : ECU,Other;
SIG_GROUP_ {FLAGGED_MISSING_ID} MissingGroup 1 : MissingSignal;
"""

    db = dbckit.parse(dbc)

    assert db.messages[100].senders == ["ECU"]
    assert db.signal_groups[0].message_id == MISSING_ID


def test_flagged_reference_matches_standard_message_by_clean_id():
    flagged_standard_id = 100 | 0x80000000
    db = dbckit.parse(
        f'{MINIMAL_DBC}\nCM_ BO_ {flagged_standard_id} "masked match";\n'
    )

    assert db.messages[100].is_extended_frame is False
    assert db.messages[100].comment == "masked match"


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


@pytest.mark.parametrize(
    ("entry", "construct", "message_id", "signal_name"),
    [
        ('CM_ BO_ 999 "comment";', "CM_", 999, None),
        ('CM_ SG_ 100 MissingSignal "comment";', "CM_", 100, "MissingSignal"),
        ('CM_ EV_ MissingEnvvar "comment";', "CM_", None, None),
        ('BA_ "Attr" BO_ 999 1;', "BA_", 999, None),
        ('BA_ "Attr" SG_ 100 MissingSignal 1;', "BA_", 100, "MissingSignal"),
        ('BA_ "Attr" EV_ MissingEnvvar 1;', "BA_", None, None),
        ('VAL_ 100 MissingSignal 0 "Off";', "VAL_", 100, "MissingSignal"),
        ('VAL_ 999 MissingSignal 0 "Off";', "VAL_", 999, "MissingSignal"),
        ("SIG_VALTYPE_ 100 MissingSignal : 1;", "SIG_VALTYPE_", 100, "MissingSignal"),
        ("ENVVAR_DATA_ MissingEnvvar : 8;", "ENVVAR_DATA_", None, None),
        ("BO_TX_BU_ 999 : ECU;", "BO_TX_BU_", 999, None),
        ("SIG_GROUP_ 999 MissingGroup 1 : MissingSignal;", "SIG_GROUP_", 999, None),
        ("SIG_GROUP_ 100 MissingGroup 1 : MissingSignal;", "SIG_GROUP_", 100, "MissingSignal"),
    ],
)
def test_skip_dangling_reference_records_cosmetic_diagnostic(
    entry: str,
    construct: str,
    message_id: int | None,
    signal_name: str | None,
):
    db = dbckit.parse(f"{MINIMAL_DBC}\n{entry}\n", on_unsupported="skip")

    assert len(db.parse_diagnostics) == 1
    diagnostic = db.parse_diagnostics[0]
    assert diagnostic.construct == construct
    assert diagnostic.line == 8
    assert diagnostic.message_id == message_id
    assert diagnostic.signal_name == signal_name
    assert diagnostic.effect == "cosmetic"
    assert diagnostic.detail
    assert db.decode_safe is True
    assert db.message_decode_safe(100) is True


def test_skip_forward_reference_is_diagnosed_in_source_order():
    dbc = """\
VERSION ""
NS_ :
BS_ :
BU_ : ECU
CM_ BO_ 100 "defined later";
BO_ 100 DefinedLater: 8 ECU
"""

    db = dbckit.parse(dbc, on_unsupported="skip")

    assert db.messages[100].comment is None
    assert len(db.parse_diagnostics) == 1
    assert db.parse_diagnostics[0].line == 5
    assert db.parse_diagnostics[0].message_id == 100
    assert db.parse_diagnostics[0].effect == "cosmetic"
    assert db.decode_safe is True


def test_skip_forward_decode_references_degrade_final_target():
    dbc = """\
VERSION ""
NS_ :
BS_ :
BU_ : E
SIG_VALTYPE_ 256 F : 1;
VAL_ 256 State 1 "On" 0 "Off" ;
BO_ 256 M: 8 E
 SG_ F : 0|32@1+ (1,0) [0|0] "" E
 SG_ State : 32|8@1+ (1,0) [0|1] "" E
"""

    db = dbckit.parse(dbc, on_unsupported="skip")

    assert [diagnostic.construct for diagnostic in db.parse_diagnostics] == [
        "SIG_VALTYPE_",
        "VAL_",
    ]
    assert [diagnostic.line for diagnostic in db.parse_diagnostics] == [5, 6]
    assert [diagnostic.message_id for diagnostic in db.parse_diagnostics] == [
        256,
        256,
    ]
    assert [diagnostic.signal_name for diagnostic in db.parse_diagnostics] == [
        "F",
        "State",
    ]
    assert [diagnostic.effect for diagnostic in db.parse_diagnostics] == [
        "decode_degraded",
        "decode_degraded",
    ]
    assert db.messages[256].signals["F"].signal_type is None
    assert db.messages[256].signals["State"].value_table is None
    assert db.decode_safe is False
    assert db.message_decode_safety == {256: False}
    assert db.message_decode_safe(256) is False


def test_forward_decode_reference_preserves_strict_source_order():
    dbc = """\
VERSION ""
NS_ :
BS_ :
BU_ : E
SIG_VALTYPE_ 256 F : 1;
BO_ 256 M: 8 E
 SG_ F : 0|32@1+ (1,0) [0|0] "" E
"""

    with pytest.raises(
        ValueError,
        match="SIG_VALTYPE_ references unknown message arbitration_id=0x100",
    ):
        dbckit.parse(dbc)


def test_message_decode_safe_rejects_unknown_message():
    db = dbckit.parse(MINIMAL_DBC)

    with pytest.raises(KeyError, match="arbitration_id=0x3e7"):
        db.message_decode_safe(999)


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
