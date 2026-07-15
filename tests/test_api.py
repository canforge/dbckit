"""Tests for the explicit object-model API (views, typed methods)."""
from __future__ import annotations

from pathlib import Path

import pytest

import dbckit
from dbckit import Database, Message, Node, Signal
from dbckit.model.database import AttributeDefinition, AttributeKind
from dbckit.views import MessageView, NodeView, SignalView

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def db() -> Database:
    return dbckit.load(FIXTURES / "simple.dbc")


@pytest.fixture
def j1939_db() -> Database:
    return Database(
        version="",
        messages={
            0x100: Message(
                arbitration_id=0x100,
                name="EngineData",
                length=8,
                attributes={"PGN": 61444},
                signals={
                    "EngineSpeed": Signal(name="EngineSpeed", start_bit=0, length=16, attributes={"SPN": 190}),
                    "EngineMode": Signal(name="EngineMode", start_bit=16, length=8, attributes={"SPN": "899"}),
                },
            ),
            0x101: Message(
                arbitration_id=0x101,
                name="TransmissionData",
                length=8,
                attributes={"PGN": "0xF005"},
                signals={
                    "TransmissionTemp": Signal(
                        name="TransmissionTemp",
                        start_bit=0,
                        length=16,
                        attributes={"SPN": 177.0},
                    ),
                    "InvalidSpn": Signal(
                        name="InvalidSpn",
                        start_bit=16,
                        length=8,
                        attributes={"SPN": "not-an-int"},
                    ),
                },
            ),
            0x102: Message(
                arbitration_id=0x102,
                name="DuplicatePgn",
                length=8,
                attributes={"PGN": "61444"},
                signals={
                    "VehicleSpeed": Signal(name="VehicleSpeed", start_bit=0, length=16, attributes={"SPN": 84}),
                },
            ),
            0x103: Message(
                arbitration_id=0x103,
                name="DuplicateSpn",
                length=8,
                attributes={"PGN": 65265.5},
                signals={
                    "BackupEngineSpeed": Signal(
                        name="BackupEngineSpeed",
                        start_bit=0,
                        length=16,
                        attributes={"SPN": "190"},
                    ),
                },
            ),
        },
    )


class TestModuleExports:
    def test_allowed_top_level_helpers_exist(self):
        for name in (
            "load",
            "save",
            "parse",
            "dump",
            "validate",
            "decode_frame",
            "encode_frame",
            "decode_signal",
            "encode_signal",
            "diff",
            "merge",
            "extract",
            "search_messages",
            "search_signals",
            "find_messages_by_pgn",
            "find_signals_by_spn",
            "decode_frames",
            "decode_log",
            "FrameLike",
            "codegen",
        ):
            assert hasattr(dbckit, name)
            assert name in dbckit.__all__

    def test_mutation_helpers_not_exported(self):
        for name in (
            "add_message",
            "add_node",
            "define_attribute",
            "delete_attribute",
            "add_signal",
            "update_message",
            "delete_message",
            "rename_message",
            "update_signal",
            "delete_signal",
            "rename_signal",
            "delete_node",
            "rename_node",
            "set_attribute",
            "unset_attribute",
            "add_signal_choice",
            "remove_signal_choice",
            "signal_layout",
        ):
            assert not hasattr(dbckit, name)

    def test_mutation_helpers_not_in___all__(self):
        for name in (
            "add_message",
            "add_node",
            "define_attribute",
            "delete_attribute",
            "add_signal",
            "update_message",
            "delete_message",
            "rename_message",
            "update_signal",
            "delete_signal",
            "rename_signal",
            "delete_node",
            "rename_node",
            "set_attribute",
            "unset_attribute",
            "add_signal_choice",
            "remove_signal_choice",
            "signal_layout",
        ):
            assert name not in dbckit.__all__


# ── Database navigation ───────────────────────────────────────────────────────

class TestDatabaseNavigation:
    def test_message_returns_message_view(self, db):
        assert isinstance(db.message(500), MessageView)

    def test_message_correct_id(self, db):
        assert db.message(500).arbitration_id == 500

    def test_message_missing_raises(self, db):
        with pytest.raises(KeyError):
            db.message(0xDEAD)

    def test_node_returns_node_view(self, db):
        assert isinstance(db.node("ECU1"), NodeView)

    def test_node_correct_name(self, db):
        assert db.node("ECU1").name == "ECU1"

    def test_node_missing_raises(self, db):
        with pytest.raises(KeyError):
            db.node("NoSuchNode")

    def test_list_messages(self, db):
        views = db.list_messages()
        assert len(views) == len(db.messages)
        assert all(isinstance(v, MessageView) for v in views)
        assert {v.arbitration_id for v in views} == set(db.messages.keys())

    def test_list_nodes(self, db):
        views = db.list_nodes()
        assert len(views) == len(db.nodes)
        assert all(isinstance(v, NodeView) for v in views)
        assert {v.name for v in views} == set(db.nodes.keys())

    def test_no_legacy_list_names(self, db):
        assert not hasattr(db, "messages_list")
        assert not hasattr(db, "nodes_list")

    def test_message_by_pgn_returns_message_view(self, j1939_db):
        view = j1939_db.message_by_pgn(61445)
        assert isinstance(view, MessageView)
        assert view.name == "TransmissionData"

    def test_message_by_pgn_missing_raises(self, j1939_db):
        with pytest.raises(KeyError, match="PGN=99999"):
            j1939_db.message_by_pgn(99999)

    def test_message_by_pgn_duplicate_raises(self, j1939_db):
        with pytest.raises(ValueError, match="PGN=61444"):
            j1939_db.message_by_pgn(61444)

    def test_signal_by_spn_returns_message_and_signal_views(self, j1939_db):
        message_view, signal_view = j1939_db.signal_by_spn(177)
        assert isinstance(message_view, MessageView)
        assert isinstance(signal_view, SignalView)
        assert message_view.name == "TransmissionData"
        assert signal_view.name == "TransmissionTemp"

    def test_signal_by_spn_missing_raises(self, j1939_db):
        with pytest.raises(KeyError, match="SPN=99999"):
            j1939_db.signal_by_spn(99999)

    def test_signal_by_spn_duplicate_raises(self, j1939_db):
        with pytest.raises(ValueError, match="SPN=190"):
            j1939_db.signal_by_spn(190)


# ── Database add mutations ────────────────────────────────────────────────────

class TestDatabaseAddMutations:
    def test_add_message(self, db):
        msg = Message(arbitration_id=0x999, name="Added", length=4)
        db2 = db.add_message(msg)
        assert 0x999 in db2.messages
        assert 0x999 not in db.messages  # original unchanged

    def test_add_message_duplicate_raises(self, db):
        with pytest.raises(ValueError):
            db.add_message(Message(arbitration_id=500, name="Dup", length=8))

    def test_add_node(self, db):
        db2 = db.add_node(Node(name="NewECU"))
        assert "NewECU" in db2.nodes
        assert "NewECU" not in db.nodes

    def test_add_node_duplicate_raises(self, db):
        with pytest.raises(ValueError):
            db.add_node(Node(name="ECU1"))

    def test_define_attribute(self, db):
        ad = AttributeDefinition(
            name="NewAttr", kind=AttributeKind.INT, object_type="BO_",
            minimum=0, maximum=1000,
        )
        db2 = db.define_attribute(ad)
        assert "NewAttr" in db2.attributes
        assert "NewAttr" not in db.attributes

    def test_delete_attribute(self, db):
        db2 = db.define_attribute(
            AttributeDefinition(name="NodeAttr", kind=AttributeKind.INT, object_type="BU_")
        )
        db3 = db2.node("ECU1").set_attribute("NodeAttr", 42)
        db4 = db3.delete_attribute("NodeAttr")
        assert "NodeAttr" in db3.attributes
        assert "NodeAttr" in db3.nodes["ECU1"].attributes
        assert "NodeAttr" not in db4.attributes
        assert "NodeAttr" not in db4.nodes["ECU1"].attributes


# ── Database cross-database operations ───────────────────────────────────────

class TestDatabaseOperations:
    def test_validate_returns_list(self, db):
        issues = db.validate()
        assert isinstance(issues, list)

    def test_validate_clean_db(self, db):
        assert [i for i in db.validate() if i.severity == "error"] == []

    def test_diff_identical_is_empty(self, db):
        assert db.diff(db).is_empty

    def test_diff_detects_change(self, db):
        db2 = db.message(500).rename("Changed")
        assert not db.diff(db2).is_empty

    def test_merge_disjoint(self, db):
        other = Database(version="", messages={0x999: Message(arbitration_id=0x999, name="X", length=4)})
        merged = db.merge(other)
        assert 0x999 in merged.messages
        assert 500 in merged.messages

    def test_extract(self, db):
        sub = db.extract([500])
        assert list(sub.messages.keys()) == [500]

    def test_dump_returns_dbc_string(self, db):
        text = db.dump()
        assert "VERSION" in text
        assert "EngineData" in text

    def test_save_round_trip(self, db, tmp_path):
        p = tmp_path / "out.dbc"
        db.save(p)
        db2 = dbckit.load(p)
        assert set(db2.messages.keys()) == set(db.messages.keys())

    # removed from Database — verify they are NOT attributes
    def test_no_codegen_method(self, db):
        assert not hasattr(db, "codegen")

    def test_no_decode_log_method(self, db):
        assert not hasattr(db, "decode_log")

    def test_no_decode_frame_method(self, db):
        assert not hasattr(db, "decode_frame")

    def test_no_encode_frame_method(self, db):
        assert not hasattr(db, "encode_frame")

    def test_no_search_messages_method(self, db):
        assert not hasattr(db, "search_messages")

    def test_no_delete_message_method(self, db):
        assert not hasattr(db, "delete_message")

    def test_no_rename_node_method(self, db):
        assert not hasattr(db, "rename_node")

    def test_no_set_attribute_method(self, db):
        assert not hasattr(db, "set_attribute")


# ── MessageView ───────────────────────────────────────────────────────────────

class TestMessageView:
    def test_properties_forwarded(self, db):
        view = db.message(500)
        msg = db.messages[500]
        assert view.name == msg.name
        assert view.length == msg.length
        assert view.senders == msg.senders
        assert view.comment == msg.comment
        assert view.cycle_time == msg.cycle_time

    def test_signal_returns_signal_view(self, db):
        assert isinstance(db.message(500).signal("EngineSpeed"), SignalView)

    def test_signal_missing_raises(self, db):
        with pytest.raises(KeyError):
            db.message(500).signal("NoSuchSignal")

    def test_list_signals(self, db):
        views = db.message(500).list_signals()
        assert len(views) == len(db.messages[500].signals)
        assert all(isinstance(sv, SignalView) for sv in views)

    def test_layout_returns_bit_slots(self, db):
        slots = db.message(500).layout()
        assert len(slots) == db.messages[500].length * 8

    def test_decode(self, db):
        data = bytes([0xE8, 0x03]) + b"\x00" * 6
        vals = db.message(500).decode(data)
        assert vals["EngineSpeed"] == pytest.approx(100.0)

    def test_decode_resolves_value_table(self, db):
        data = b"\x00\x00\x00\x01" + b"\x00" * 4
        assert db.message(500).decode(data)["IgnitionStatus"] == "On"

    def test_encode(self, db):
        raw = db.message(500).encode({"EngineSpeed": 100.0})
        assert raw[0] == 0xE8 and raw[1] == 0x03

    def test_encode_missing_signal_raises(self, db):
        with pytest.raises(KeyError):
            db.message(500).encode({"NoSuchSignal": 0.0})

    def test_encode_decode_roundtrip(self, db):
        raw = db.message(500).encode({"EngineSpeed": 825.0, "EngineTemp": 90.0})
        vals = db.message(500).decode(raw)
        assert vals["EngineSpeed"] == pytest.approx(825.0, abs=0.1)
        assert vals["EngineTemp"] == pytest.approx(90.0, abs=1.0)

    def test_update(self, db):
        db2 = db.message(500).update(cycle_time=50)
        assert db2.messages[500].cycle_time == 50
        assert db.messages[500].cycle_time == 100

    def test_delete(self, db):
        db2 = db.message(500).delete()
        assert 500 not in db2.messages
        assert 500 in db.messages  # original intact

    def test_rename(self, db):
        db2 = db.message(500).rename("MotorData")
        assert db2.messages[500].name == "MotorData"
        assert db.messages[500].name == "EngineData"

    def test_add_signal(self, db):
        sig = Signal(name="NewSig", start_bit=32, length=8)
        db2 = db.message(500).add_signal(sig)
        assert "NewSig" in db2.messages[500].signals
        assert "NewSig" not in db.messages[500].signals

    def test_delete_signal(self, db):
        db2 = db.message(500).delete_signal("EngineSpeed")
        assert "EngineSpeed" not in db2.messages[500].signals

    def test_rename_signal(self, db):
        db2 = db.message(500).rename_signal("EngineSpeed", "RPM")
        assert "RPM" in db2.messages[500].signals
        assert "EngineSpeed" not in db2.messages[500].signals

    def test_update_signal(self, db):
        db2 = db.message(500).update_signal("EngineSpeed", factor=0.5)
        assert db2.messages[500].signals["EngineSpeed"].factor == pytest.approx(0.5)
        assert db.messages[500].signals["EngineSpeed"].factor == pytest.approx(0.1)

    def test_set_attribute(self, db):
        db2 = db.message(500).set_attribute("GenMsgCycleTime", 200)
        assert db2.messages[500].attributes["GenMsgCycleTime"] == 200
        assert db.messages[500].attributes.get("GenMsgCycleTime") == 100  # original unchanged

    def test_unset_attribute(self, db):
        db2 = db.message(500).set_attribute("GenMsgCycleTime", 200)
        db3 = db2.message(500).unset_attribute("GenMsgCycleTime")
        assert "GenMsgCycleTime" not in db3.messages[500].attributes

    def test_repr(self, db):
        r = repr(db.message(500))
        assert "MessageView" in r and "EngineData" in r


# ── SignalView ────────────────────────────────────────────────────────────────

class TestSignalView:
    def test_properties_forwarded(self, db):
        sv = db.message(500).signal("EngineSpeed")
        sig = db.messages[500].signals["EngineSpeed"]
        assert sv.name == sig.name
        assert sv.start_bit == sig.start_bit
        assert sv.length == sig.length
        assert sv.factor == pytest.approx(sig.factor)
        assert sv.offset == pytest.approx(sig.offset)
        assert sv.unit == sig.unit
        assert sv.is_signed == sig.is_signed
        assert sv.byte_order == sig.byte_order

    def test_decode(self, db):
        data = bytes([0xE8, 0x03]) + b"\x00" * 6
        assert db.message(500).signal("EngineSpeed").decode(data) == pytest.approx(100.0)

    def test_decode_phys_resolves_label(self, db):
        data = b"\x00\x00\x00\x01" + b"\x00" * 4
        assert db.message(500).signal("IgnitionStatus").decode_phys(data) == "On"

    def test_choices(self, db):
        ch = db.message(500).signal("IgnitionStatus").choices()
        assert ch == {0: "Off", 1: "On"}

    def test_choices_no_table(self, db):
        assert db.message(500).signal("EngineSpeed").choices() is None

    def test_choice(self, db):
        sv = db.message(500).signal("IgnitionStatus")
        assert sv.choice(0) == "Off"
        assert sv.choice(1) == "On"
        assert sv.choice(99) is None

    def test_update(self, db):
        db2 = db.message(500).signal("EngineSpeed").update(factor=0.5)
        assert db2.messages[500].signals["EngineSpeed"].factor == pytest.approx(0.5)
        assert db.messages[500].signals["EngineSpeed"].factor == pytest.approx(0.1)

    def test_delete(self, db):
        db2 = db.message(500).signal("EngineSpeed").delete()
        assert "EngineSpeed" not in db2.messages[500].signals
        assert "EngineSpeed" in db.messages[500].signals

    def test_rename(self, db):
        db2 = db.message(500).signal("EngineSpeed").rename("RPM")
        assert "RPM" in db2.messages[500].signals
        assert "EngineSpeed" not in db2.messages[500].signals

    def test_add_choice(self, db):
        db2 = db.message(500).signal("IgnitionStatus").add_choice(2, "Crank")
        assert db2.messages[500].signals["IgnitionStatus"].value_table.values[2] == "Crank"
        assert 2 not in db.messages[500].signals["IgnitionStatus"].value_table.values

    def test_remove_choice(self, db):
        db2 = db.message(500).signal("IgnitionStatus").remove_choice(0)
        assert 0 not in db2.messages[500].signals["IgnitionStatus"].value_table.values
        assert db.messages[500].signals["IgnitionStatus"].value_table.values[0] == "Off"

    def test_set_attribute(self, db):
        db2 = db.message(500).signal("EngineSpeed").set_attribute("MyAttr", "test")
        assert db2.messages[500].signals["EngineSpeed"].attributes["MyAttr"] == "test"
        assert "MyAttr" not in db.messages[500].signals["EngineSpeed"].attributes

    def test_unset_attribute(self, db):
        db2 = db.message(500).signal("EngineSpeed").set_attribute("MyAttr", "test")
        db3 = db2.message(500).signal("EngineSpeed").unset_attribute("MyAttr")
        assert "MyAttr" not in db3.messages[500].signals["EngineSpeed"].attributes

    def test_repr(self, db):
        r = repr(db.message(500).signal("EngineSpeed"))
        assert "SignalView" in r and "EngineSpeed" in r

    def test_chained_update(self, db):
        db2 = db.message(500).signal("EngineSpeed").update(factor=0.5)
        assert isinstance(db2, Database)
        assert db2.messages[500].signals["EngineSpeed"].factor == pytest.approx(0.5)


# ── NodeView ──────────────────────────────────────────────────────────────────

class TestNodeView:
    def test_properties_forwarded(self, db):
        nv = db.node("ECU1")
        assert nv.name == db.nodes["ECU1"].name
        assert nv.comment == db.nodes["ECU1"].comment

    def test_delete(self, db):
        db2 = db.node("GW").delete()
        assert "GW" not in db2.nodes
        assert "GW" in db.nodes

    def test_rename(self, db):
        db2 = db.node("ECU1").rename("EngineECU")
        assert "EngineECU" in db2.nodes
        assert "ECU1" not in db2.nodes
        assert "ECU1" in db.nodes  # original intact

    def test_rename_patches_senders(self, db):
        db2 = db.node("ECU1").rename("EngineECU")
        assert "EngineECU" in db2.messages[500].senders
        assert "ECU1" not in db2.messages[500].senders

    def test_rename_patches_receivers(self, db):
        db2 = db.node("GW").rename("Gateway")
        assert "Gateway" in db2.messages[500].signals["EngineSpeed"].receivers
        assert "GW" not in db2.messages[500].signals["EngineSpeed"].receivers

    def test_set_attribute(self, db):
        db2 = db.node("ECU1").set_attribute("NodeAttr", 42)
        assert db2.nodes["ECU1"].attributes["NodeAttr"] == 42
        assert "NodeAttr" not in db.nodes["ECU1"].attributes

    def test_unset_attribute(self, db):
        db2 = db.node("ECU1").set_attribute("NodeAttr", 42)
        db3 = db2.node("ECU1").unset_attribute("NodeAttr")
        assert "NodeAttr" not in db3.nodes["ECU1"].attributes

    def test_repr(self, db):
        assert "NodeView" in repr(db.node("ECU1"))
        assert "ECU1" in repr(db.node("ECU1"))


# ── Signal / Message / ValueTable model methods ───────────────────────────────

class TestModelMethods:
    def test_signal_decode(self, db):
        sig = db.messages[500].signals["EngineSpeed"]
        data = bytes([0xE8, 0x03]) + b"\x00" * 6
        assert sig.decode(data) == pytest.approx(100.0)

    def test_signal_decode_phys_label(self, db):
        sig = db.messages[500].signals["IgnitionStatus"]
        data = b"\x00\x00\x00\x01" + b"\x00" * 4
        assert sig.decode_phys(data) == "On"

    def test_signal_choices(self, db):
        sig = db.messages[500].signals["IgnitionStatus"]
        assert sig.choices() == {0: "Off", 1: "On"}

    def test_signal_choices_none(self, db):
        assert db.messages[500].signals["EngineSpeed"].choices() is None

    def test_signal_choice(self, db):
        sig = db.messages[500].signals["IgnitionStatus"]
        assert sig.choice(0) == "Off"
        assert sig.choice(99) is None

    def test_message_signal(self, db):
        msg = db.messages[500]
        assert msg.signal("EngineSpeed") is msg.signals["EngineSpeed"]

    def test_message_signal_missing_raises(self, db):
        with pytest.raises(KeyError):
            db.messages[500].signal("NoSuchSignal")

    def test_message_list_signals(self, db):
        msg = db.messages[500]
        lst = msg.list_signals()
        assert len(lst) == len(msg.signals)
        assert all(isinstance(s, Signal) for s in lst)

    def test_message_no_legacy_signals_list(self, db):
        assert not hasattr(db.messages[500], "signals_list")

    def test_message_layout(self, db):
        msg = db.messages[500]
        assert len(msg.layout()) == msg.length * 8

    def test_value_table_get(self, db):
        vt = db.messages[500].signals["IgnitionStatus"].value_table
        assert vt.get(0) == "Off" and vt.get(99) is None

    def test_value_table_has(self, db):
        vt = db.messages[500].signals["IgnitionStatus"].value_table
        assert vt.has(0) is True and vt.has(99) is False

    def test_value_table_labels_is_copy(self, db):
        vt = db.messages[500].signals["IgnitionStatus"].value_table
        labels = vt.labels()
        labels[99] = "Test"
        assert 99 not in vt.values  # copy, not the original


# ── chaining smoke tests ──────────────────────────────────────────────────────

class TestChaining:
    def test_signal_update(self, db):
        db2 = db.message(500).signal("EngineSpeed").update(factor=0.5)
        assert db2.messages[500].signals["EngineSpeed"].factor == pytest.approx(0.5)

    def test_message_delete(self, db):
        assert 500 not in db.message(500).delete().messages

    def test_node_rename(self, db):
        assert "EngineECU" in db.node("ECU1").rename("EngineECU").nodes

    def test_multi_step(self, db):
        # rename the message, then update a signal on the new db
        db2 = db.message(500).rename("MotorData")
        db3 = db2.message(500).signal("EngineSpeed").update(factor=0.5)
        assert db3.messages[500].name == "MotorData"
        assert db3.messages[500].signals["EngineSpeed"].factor == pytest.approx(0.5)

    def test_view_on_original_unaffected_by_mutation(self, db):
        view = db.message(500)
        db.message(500).delete()   # discard result
        assert view.name == "EngineData"  # view still references original db
