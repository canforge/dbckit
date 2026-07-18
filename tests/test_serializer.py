"""Tests for the DBC serializer."""
from __future__ import annotations

from pathlib import Path

import pytest

import dbckit
from dbckit.model.database import (
    AttributeDefinition,
    AttributeKind,
    Database,
    EnvironmentVariable,
)
from dbckit.model.message import Message
from dbckit.model.signal import ByteOrder, Signal, SignalGroup, ValueTable
from dbckit.serializer import dump

FIXTURES = Path(__file__).parent / "fixtures"


def _minimal_db() -> Database:
    sig = Signal(name="TestSig", start_bit=0, length=8, byte_order=ByteOrder.little_endian,
                 is_signed=False, factor=1.0, offset=0.0, unit="rpm")
    msg = Message(arbitration_id=0x100, name="TestMsg", length=8,
                  senders=["ECU1"], signals={"TestSig": sig})
    return Database(version="test", messages={0x100: msg})


def test_dump_produces_string():
    result = dump(_minimal_db())
    assert isinstance(result, str)
    assert "VERSION" in result
    assert "BO_" in result
    assert "SG_" in result


def test_dump_version():
    db = _minimal_db().model_copy(update={"version": "my_version"})
    assert 'VERSION "my_version"' in dump(db)


def test_dump_message():
    assert "BO_ 256 TestMsg" in dump(_minimal_db())


def test_dump_signal():
    result = dump(_minimal_db())
    assert "SG_ TestSig" in result
    assert "0|8@1+" in result
    assert '"rpm"' in result


def test_dump_big_endian_signal():
    sig = Signal(name="BigSig", start_bit=7, length=8, byte_order=ByteOrder.big_endian)
    msg = Message(arbitration_id=1, name="M", length=8, signals={"BigSig": sig})
    db = Database(version="", messages={1: msg})
    assert "7|8@0+" in dump(db)


def test_dump_comment():
    db = _minimal_db()
    msg = db.messages[0x100].model_copy(update={"comment": "A test message"})
    db = db.model_copy(update={"messages": {0x100: msg}})
    assert 'CM_ BO_  256 "A test message"' in dump(db)


def test_dump_multiplex_indicator():
    sig = Signal(name="MuxSig", start_bit=0, length=4, multiplex_indicator="M")
    msg = Message(arbitration_id=1, name="M", length=8, signals={"MuxSig": sig})
    db = Database(version="", messages={1: msg})
    assert "SG_ MuxSig M :" in dump(db)


def test_roundtrip_preserves_signals():
    db1 = dbckit.load(FIXTURES / "simple.dbc")
    db2 = dbckit.parse(dbckit.dump(db1))
    for arb_id, msg in db1.messages.items():
        for sig_name, sig in msg.signals.items():
            s2 = db2.messages[arb_id].signals[sig_name]
            assert s2.start_bit == sig.start_bit
            assert s2.length == sig.length
            assert s2.byte_order == sig.byte_order
            assert s2.is_signed == sig.is_signed
            assert s2.factor == pytest.approx(sig.factor)
            assert s2.offset == pytest.approx(sig.offset)
            assert s2.unit == sig.unit


def test_roundtrip_preserves_value_tables():
    db1 = dbckit.load(FIXTURES / "simple.dbc")
    db2 = dbckit.parse(dbckit.dump(db1))
    vt1 = db1.messages[500].signals["IgnitionStatus"].value_table
    vt2 = db2.messages[500].signals["IgnitionStatus"].value_table
    assert vt1 is not None and vt2 is not None
    assert vt1.values == vt2.values


def test_roundtrip_complex():
    db1 = dbckit.load(FIXTURES / "complex.dbc")
    db2 = dbckit.parse(dbckit.dump(db1))
    assert len(db2.messages) == len(db1.messages)
    assert set(db2.messages.keys()) == set(db1.messages.keys())


# ── extended frames ───────────────────────────────────────────────────────────

def test_extended_frame_flag_parsed():
    db = dbckit.load(FIXTURES / "extended.dbc")
    assert db.messages[0x100].is_extended_frame is True


def test_standard_frame_flag_parsed():
    db = dbckit.load(FIXTURES / "extended.dbc")
    assert db.messages[512].is_extended_frame is False


def test_extended_frame_id_stored_as_clean_id():
    db = dbckit.load(FIXTURES / "extended.dbc")
    assert db.messages[0x100].arbitration_id == 0x100


def test_extended_frame_serialized_with_high_bit():
    db = dbckit.load(FIXTURES / "extended.dbc")
    text = dump(db)
    assert "2147483904" in text  # 0x80000100


def test_extended_frame_transmitters_serialized_with_high_bit():
    msg = Message(
        arbitration_id=0x100,
        name="M",
        length=8,
        is_extended_frame=True,
        senders=["ECU1", "ECU2"],
    )
    text = dump(Database(messages={0x100: msg}))

    assert "BO_ 2147483904 M:" in text
    assert "BO_TX_BU_ 2147483904 : ECU1,ECU2;" in text


def _message_reference_db(*, is_extended_frame: bool) -> Database:
    arbitration_id = 0x321
    signal = Signal(
        name="State",
        start_bit=0,
        length=32,
        receivers=["ECU2"],
        comment="signal comment",
        value_table=ValueTable(name="StateValues", values={0: "Off", 1: "On"}),
        attributes={"SignalAttr": 9},
        signal_type=1,
    )
    message = Message(
        arbitration_id=arbitration_id,
        name="ReferenceMessage",
        length=8,
        is_extended_frame=is_extended_frame,
        senders=["ECU1", "ECU2"],
        signals={signal.name: signal},
        comment="message comment",
        attributes={"MessageAttr": 7},
        cycle_time=25,
    )
    attributes = {
        "GenMsgCycleTime": AttributeDefinition(
            name="GenMsgCycleTime",
            kind=AttributeKind.INT,
            object_type="BO_",
            minimum=0,
            maximum=1000,
        ),
        "MessageAttr": AttributeDefinition(
            name="MessageAttr",
            kind=AttributeKind.INT,
            object_type="BO_",
            minimum=0,
            maximum=10,
        ),
        "SignalAttr": AttributeDefinition(
            name="SignalAttr",
            kind=AttributeKind.INT,
            object_type="SG_",
            minimum=0,
            maximum=10,
        ),
    }
    group = SignalGroup(
        name="Status",
        message_id=arbitration_id,
        signal_names=[signal.name],
    )
    return Database(
        messages={arbitration_id: message},
        attributes=attributes,
        signal_groups=[group],
    )


def _assert_message_reference_ids(text: str, expected_id: int) -> None:
    expected_lines = (
        f"BO_ {expected_id} ReferenceMessage: 8 ECU1",
        f"BO_TX_BU_ {expected_id} : ECU1,ECU2;",
        f'CM_ BO_  {expected_id} "message comment";',
        f'CM_ SG_  {expected_id} State "signal comment";',
        f'BA_ "GenMsgCycleTime" BO_ {expected_id} 25;',
        f'BA_ "MessageAttr" BO_ {expected_id} 7;',
        f'BA_ "SignalAttr" SG_ {expected_id} State 9;',
        f'VAL_ {expected_id} State 0 "Off" 1 "On" ;',
        f"SIG_GROUP_ {expected_id} Status 1 : State;",
        f"SIG_VALTYPE_ {expected_id} State : 1 ;",
    )
    for expected in expected_lines:
        assert expected in text


def test_extended_frame_references_serialized_with_high_bit_and_roundtrip():
    arbitration_id = 0x321
    flagged_id = arbitration_id | 0x80000000
    db = _message_reference_db(is_extended_frame=True)
    before = db.model_dump()

    text = dump(db)

    _assert_message_reference_ids(text, flagged_id)
    assert db.model_dump() == before

    reparsed = dbckit.parse(text)
    message = reparsed.messages[arbitration_id]
    assert message.is_extended_frame is True
    assert message.senders == ["ECU1", "ECU2"]
    assert message.comment == "message comment"
    assert message.cycle_time == 25
    assert message.attributes["MessageAttr"] == 7
    signal = message.signals["State"]
    assert signal.comment == "signal comment"
    assert signal.attributes["SignalAttr"] == 9
    assert signal.signal_type == 1
    assert signal.value_table is not None
    assert signal.value_table.values == {0: "Off", 1: "On"}
    assert reparsed.signal_groups[0].message_id == arbitration_id


def test_standard_frame_references_serialized_without_high_bit():
    arbitration_id = 0x321
    flagged_id = arbitration_id | 0x80000000

    text = dump(_message_reference_db(is_extended_frame=False))

    _assert_message_reference_ids(text, arbitration_id)
    assert str(flagged_id) not in text


def test_dangling_signal_group_serialized_without_guessing_extended_flag():
    message_id = 0x18FF1234
    group = SignalGroup(name="Dangling", message_id=message_id)

    text = dump(Database(signal_groups=[group]))

    assert f"SIG_GROUP_ {message_id} Dangling 1 : ;" in text
    assert str(message_id | 0x80000000) not in text


def test_standard_frame_serialized_without_high_bit():
    db = dbckit.load(FIXTURES / "extended.dbc")
    text = dump(db)
    assert "\nBO_ 512 " in text


def test_extended_frame_roundtrip():
    db1 = dbckit.load(FIXTURES / "extended.dbc")
    db2 = dbckit.parse(dbckit.dump(db1))
    msg = db2.messages[0x100]
    assert msg.is_extended_frame is True
    assert msg.arbitration_id == 0x100
    assert msg.name == "ExtMsg"
    assert "ExtSig" in msg.signals


def test_extended_frame_constructed_roundtrip():
    from dbckit.model.signal import Signal
    sig = Signal(name="S", start_bit=0, length=8)
    msg = Message(arbitration_id=0x18FF1234, name="J1939Msg", length=8,
                  is_extended_frame=True, signals={"S": sig})
    db = Database(version="", messages={0x18FF1234: msg})
    db2 = dbckit.parse(dump(db))
    assert db2.messages[0x18FF1234].is_extended_frame is True
    assert db2.messages[0x18FF1234].arbitration_id == 0x18FF1234


def test_css_electronics_extended_id_fixture_roundtrip():
    original = dbckit.load(FIXTURES / "css_electronics_extended.dbc").model_copy(
        update={"filename": None}
    )
    flagged_id = 2364540158
    extended_id = flagged_id & 0x1FFFFFFF
    standard_id = 512
    incorrectly_flagged_standard_id = standard_id | 0x80000000

    assert original.messages[extended_id].cycle_time == 100

    serialized = dbckit.dump(original)

    expected_id_references = (
        f"BO_ {flagged_id} EngineTelemetry:",
        f"BO_TX_BU_ {flagged_id} :",
        f"CM_ BO_  {flagged_id} ",
        f"CM_ SG_  {flagged_id} EngineSpeed ",
        f'BA_ "GenMsgCycleTime" BO_ {flagged_id} 100;',
        f'BA_ "VFrameFormat" BO_ {flagged_id} ',
        f'BA_ "SPN" SG_ {flagged_id} EngineSpeed ',
        f"VAL_ {flagged_id} EngineStatus ",
        f"SIG_GROUP_ {flagged_id} EngineSignals ",
        f"SIG_VALTYPE_ {flagged_id} EngineSpeed ",
    )
    for expected in expected_id_references:
        assert expected in serialized
    assert str(extended_id) not in serialized

    expected_standard_id_references = (
        f"BO_ {standard_id} StandardStatus:",
        f"CM_ BO_  {standard_id} ",
        f"VAL_ {standard_id} SystemState ",
    )
    for expected in expected_standard_id_references:
        assert expected in serialized
    assert str(incorrectly_flagged_standard_id) not in serialized

    reparsed = dbckit.parse(serialized)
    assert reparsed.messages[extended_id].cycle_time == 100
    assert reparsed == original


# ── BO_TX_BU_ ─────────────────────────────────────────────────────────────────

def test_bo_tx_bu_emitted_for_multiple_senders():
    msg = Message(arbitration_id=0x100, name="M", length=8, senders=["ECU1", "ECU2"])
    db = Database(version="", messages={0x100: msg})
    text = dump(db)
    assert "BO_TX_BU_" in text
    assert "ECU1" in text
    assert "ECU2" in text


def test_bo_tx_bu_not_emitted_for_single_sender():
    msg = Message(arbitration_id=0x100, name="M", length=8, senders=["ECU1"])
    db = Database(version="", messages={0x100: msg})
    assert "BO_TX_BU_" not in dump(db)


def test_bo_tx_bu_roundtrip():
    msg = Message(arbitration_id=0x100, name="M", length=8, senders=["ECU1", "ECU2", "ECU3"])
    db = Database(version="", messages={0x100: msg})
    db2 = dbckit.parse(dump(db))
    assert db2.messages[0x100].senders == ["ECU1", "ECU2", "ECU3"]


def test_bo_tx_bu_fixture_roundtrip():
    db1 = dbckit.load(FIXTURES / "extended.dbc")
    assert db1.messages[512].senders == ["ECU1", "ECU2"]
    db2 = dbckit.parse(dump(db1))
    assert db2.messages[512].senders == ["ECU1", "ECU2"]


# ── EV_ / ENVVAR_DATA_ ────────────────────────────────────────────────────────

def _ev_db() -> Database:
    ev = EnvironmentVariable(
        name="MyEnvVar",
        var_type=0,
        minimum=0.0,
        maximum=100.0,
        unit="%",
        initial_value=0.0,
        ev_id=1,
        access_type="DUMMY_NODE_VECTOR0",
        access_nodes=["ECU1"],
        comment="A test env var",
        data_size=4,
    )
    return Database(version="", environment_variables={"MyEnvVar": ev})


def test_ev_section_emitted():
    text = dump(_ev_db())
    assert "EV_ MyEnvVar:" in text
    assert "DUMMY_NODE_VECTOR0" in text


def test_envvar_data_emitted():
    assert "ENVVAR_DATA_ MyEnvVar: 4" in dump(_ev_db())


def test_ev_comment_emitted():
    assert 'CM_ EV_  MyEnvVar "A test env var"' in dump(_ev_db())


def test_ev_roundtrip():
    db = _ev_db()
    db2 = dbckit.parse(dump(db))
    ev = db2.environment_variables["MyEnvVar"]
    assert ev.var_type == 0
    assert ev.minimum == 0.0
    assert ev.maximum == 100.0
    assert ev.unit == "%"
    assert ev.ev_id == 1
    assert ev.access_type == "DUMMY_NODE_VECTOR0"
    assert ev.access_nodes == ["ECU1"]
    assert ev.comment == "A test env var"
    assert ev.data_size == 4


def test_extract_preserves_environment_variables():
    ev = EnvironmentVariable(
        name="MyEnvVar", var_type=0, minimum=0.0, maximum=0.0,
        unit="", initial_value=0.0, ev_id=0,
        access_type="DUMMY_NODE_VECTOR0", access_nodes=["Vector__XXX"],
    )
    msg = Message(arbitration_id=0x100, name="M", length=8)
    db = Database(version="", messages={0x100: msg}, environment_variables={"MyEnvVar": ev})
    sub = dbckit.extract(db, [0x100])
    assert "MyEnvVar" in sub.environment_variables


# ── SIG_VALTYPE_ ──────────────────────────────────────────────────────────────

def test_sig_valtype_emitted():
    sig = Signal(name="FloatSig", start_bit=0, length=32, signal_type=1)
    msg = Message(arbitration_id=0x100, name="M", length=8, signals={"FloatSig": sig})
    db = Database(version="", messages={0x100: msg})
    text = dump(db)
    assert "SIG_VALTYPE_" in text
    assert "FloatSig" in text
    assert ": 1" in text


def test_sig_valtype_not_emitted_when_absent():
    sig = Signal(name="NormalSig", start_bit=0, length=8)
    msg = Message(arbitration_id=0x100, name="M", length=8, signals={"NormalSig": sig})
    db = Database(version="", messages={0x100: msg})
    assert "SIG_VALTYPE_" not in dump(db)


def test_sig_valtype_roundtrip():
    sig = Signal(name="FloatSig", start_bit=0, length=32, signal_type=2)
    msg = Message(arbitration_id=0x100, name="M", length=8, signals={"FloatSig": sig})
    db = Database(version="", messages={0x100: msg})
    db2 = dbckit.parse(dump(db))
    assert db2.messages[0x100].signals["FloatSig"].signal_type == 2
