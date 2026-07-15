"""Tests for low-level mutation helper modules."""
from __future__ import annotations

from pathlib import Path

import pytest

import dbckit
from dbckit.model.database import AttributeDefinition, AttributeKind, Database, Node
from dbckit.model.message import Message
from dbckit.model.signal import Signal, SignalGroup
from dbckit.mutations.attribute import (
    define_attribute,
    delete_attribute,
    set_database_attribute,
    set_message_attribute,
    set_node_attribute,
    set_signal_attribute,
    unset_database_attribute,
    unset_message_attribute,
    unset_node_attribute,
    unset_signal_attribute,
)
from dbckit.mutations.message import (
    add_message,
    add_sender,
    delete_message,
    remove_sender,
    rename_message,
    update_message,
)
from dbckit.mutations.node import add_node, delete_node, rename_node
from dbckit.mutations.signal import (
    add_signal,
    add_signal_choice,
    delete_signal,
    remove_signal_choice,
    rename_signal,
    signal_layout,
    update_signal,
)
from dbckit.mutations.signal_group import (
    add_signal_group,
    add_signal_to_group,
    remove_signal_from_group,
    remove_signal_group,
)

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def db() -> Database:
    return dbckit.load(FIXTURES / "simple.dbc")


# ── message mutations ─────────────────────────────────────────────────────────

class TestMessageMutations:
    def test_add_message_returns_new_db(self, db):
        msg = Message(arbitration_id=0x999, name="New", length=8)
        db2 = add_message(db, msg)
        assert 0x999 in db2.messages
        assert 0x999 not in db.messages  # original unchanged

    def test_add_message_duplicate_raises(self, db):
        msg = Message(arbitration_id=500, name="Dup", length=8)
        with pytest.raises(ValueError, match="already exists"):
            add_message(db, msg)

    def test_delete_message(self, db):
        db2 = delete_message(db, 500)
        assert 500 not in db2.messages
        assert 500 in db.messages

    def test_delete_message_missing_raises(self, db):
        with pytest.raises(KeyError):
            delete_message(db, 0xDEAD)

    def test_rename_message(self, db):
        db2 = rename_message(db, 500, "EngineStatus")
        assert db2.messages[500].name == "EngineStatus"
        assert db.messages[500].name == "EngineData"

    def test_rename_message_collision_raises(self, db):
        # simple.dbc has two messages; rename one to the other's name
        names = [m.name for m in db.messages.values()]
        assert len(names) >= 2
        arb_ids = list(db.messages.keys())
        other_name = db.messages[arb_ids[1]].name
        with pytest.raises(ValueError, match=other_name):
            rename_message(db, arb_ids[0], other_name)

    def test_rename_message_same_name_is_noop(self, db):
        db2 = rename_message(db, 500, "EngineData")
        assert db2.messages[500].name == "EngineData"

    def test_update_message_cycle_time(self, db):
        db2 = update_message(db, 500, cycle_time=100)
        assert db2.messages[500].cycle_time == 100
        assert db.messages[500].cycle_time == 100

    def test_add_sender(self, db):
        db2 = add_sender(db, 500, "NewECU")
        assert db2.messages[500].senders == [*db.messages[500].senders, "NewECU"]
        assert "NewECU" not in db.messages[500].senders

    def test_add_sender_duplicate_raises(self, db):
        with pytest.raises(ValueError, match="already exists"):
            add_sender(db, 500, db.messages[500].senders[0])

    def test_remove_sender(self, db):
        sender = db.messages[500].senders[0]
        db2 = remove_sender(db, 500, sender)
        assert sender not in db2.messages[500].senders
        assert sender in db.messages[500].senders

    def test_remove_sender_missing_raises(self, db):
        with pytest.raises(KeyError, match="Ghost"):
            remove_sender(db, 500, "Ghost")

    def test_message_view_sender_mutations(self, db):
        db2 = db.message(500).add_sender("NewECU")
        db3 = db2.message(500).remove_sender("NewECU")
        assert "NewECU" in db2.messages[500].senders
        assert "NewECU" not in db3.messages[500].senders


# ── signal mutations ──────────────────────────────────────────────────────────

class TestSignalMutations:
    def _new_sig(self) -> Signal:
        return Signal(name="NewSig", start_bit=32, length=8)

    def test_add_signal(self, db):
        db2 = add_signal(db, 500, self._new_sig())
        assert "NewSig" in db2.messages[500].signals
        assert "NewSig" not in db.messages[500].signals

    def test_add_signal_duplicate_raises(self, db):
        with pytest.raises(ValueError):
            add_signal(db, 500, Signal(name="EngineSpeed", start_bit=0, length=16))

    def test_delete_signal(self, db):
        db2 = delete_signal(db, 500, "EngineSpeed")
        assert "EngineSpeed" not in db2.messages[500].signals
        assert "EngineSpeed" in db.messages[500].signals

    def test_delete_signal_missing_raises(self, db):
        with pytest.raises(KeyError):
            delete_signal(db, 500, "NoSuchSignal")

    def test_rename_signal(self, db):
        db2 = rename_signal(db, 500, "EngineSpeed", "RPM")
        assert "RPM" in db2.messages[500].signals
        assert "EngineSpeed" not in db2.messages[500].signals
        assert db2.messages[500].signals["RPM"].start_bit == 0

    def test_rename_signal_collision_raises(self, db):
        with pytest.raises(ValueError, match="EngineTemp"):
            rename_signal(db, 500, "EngineSpeed", "EngineTemp")

    def test_rename_signal_same_name_is_noop(self, db):
        db2 = rename_signal(db, 500, "EngineSpeed", "EngineSpeed")
        assert "EngineSpeed" in db2.messages[500].signals

    def test_update_signal_factor(self, db):
        db2 = update_signal(db, 500, "EngineSpeed", factor=0.5)
        assert db2.messages[500].signals["EngineSpeed"].factor == pytest.approx(0.5)
        assert db.messages[500].signals["EngineSpeed"].factor == pytest.approx(0.1)

    def test_add_signal_choice(self, db):
        db2 = add_signal_choice(db, 500, "IgnitionStatus", 2, "Crank")
        vt = db2.messages[500].signals["IgnitionStatus"].value_table
        assert vt is not None
        assert vt.values[2] == "Crank"
        # original unchanged
        orig_vt = db.messages[500].signals["IgnitionStatus"].value_table
        assert orig_vt is not None
        assert 2 not in orig_vt.values

    def test_remove_signal_choice(self, db):
        db2 = remove_signal_choice(db, 500, "IgnitionStatus", 0)
        vt = db2.messages[500].signals["IgnitionStatus"].value_table
        assert vt is not None
        assert 0 not in vt.values
        # original has key 0
        assert db.messages[500].signals["IgnitionStatus"].value_table.values[0] == "Off"

    def test_remove_signal_choice_missing_raises(self, db):
        with pytest.raises(KeyError):
            remove_signal_choice(db, 500, "IgnitionStatus", 99)

    def test_signal_layout_returns_bit_slots(self, db):
        msg = db.messages[500]
        slots = signal_layout(msg)
        assert len(slots) == msg.length * 8
        # EngineSpeed occupies bits 0-15
        speed_slots = [s for s in slots if s.signal_name == "EngineSpeed"]
        assert len(speed_slots) == 16


# ── signal-group mutations

class TestSignalGroupMutations:
    def test_add_and_remove_signal_group(self, db):
        group = SignalGroup(
            name="Powertrain", message_id=500, signal_names=["EngineSpeed"]
        )
        db2 = add_signal_group(db, group)
        db3 = remove_signal_group(db2, 500, "Powertrain")
        assert group in db2.signal_groups
        assert group not in db.signal_groups
        assert group not in db3.signal_groups

    def test_add_duplicate_group_raises(self, db):
        group = SignalGroup(name="Powertrain", message_id=500)
        db2 = add_signal_group(db, group)
        with pytest.raises(ValueError, match="already exists"):
            add_signal_group(db2, group)

    def test_add_group_validates_message_and_signals(self, db):
        with pytest.raises(KeyError):
            add_signal_group(db, SignalGroup(name="Missing", message_id=999))
        with pytest.raises(KeyError, match="Ghost"):
            add_signal_group(
                db,
                SignalGroup(name="Missing", message_id=500, signal_names=["Ghost"]),
            )

    def test_add_and_remove_signal_from_group(self, db):
        group = SignalGroup(
            name="Powertrain", message_id=500, signal_names=["EngineSpeed"]
        )
        db2 = add_signal_group(db, group)
        db3 = add_signal_to_group(db2, 500, "Powertrain", "EngineTemp")
        db4 = remove_signal_from_group(db3, 500, "Powertrain", "EngineSpeed")
        assert db3.signal_groups[-1].signal_names == ["EngineSpeed", "EngineTemp"]
        assert db4.signal_groups[-1].signal_names == ["EngineTemp"]
        assert db2.signal_groups[-1].signal_names == ["EngineSpeed"]

    def test_signal_membership_errors(self, db):
        group = SignalGroup(
            name="Powertrain", message_id=500, signal_names=["EngineSpeed"]
        )
        db2 = add_signal_group(db, group)
        with pytest.raises(ValueError, match="already belongs"):
            add_signal_to_group(db2, 500, "Powertrain", "EngineSpeed")
        with pytest.raises(KeyError, match="EngineTemp"):
            remove_signal_from_group(db2, 500, "Powertrain", "EngineTemp")

    def test_database_signal_group_methods(self, db):
        group = SignalGroup(name="Powertrain", message_id=500)
        db2 = db.add_signal_group(group)
        db3 = db2.add_signal_to_group(500, "Powertrain", "EngineSpeed")
        db4 = db3.remove_signal_from_group(500, "Powertrain", "EngineSpeed")
        db5 = db4.remove_signal_group(500, "Powertrain")
        assert db3.signal_groups[-1].signal_names == ["EngineSpeed"]
        assert db5.signal_groups == db.signal_groups


# ── node mutations ────────────────────────────────────────────────────────────

class TestNodeMutations:
    def test_add_node(self, db):
        db2 = add_node(db, Node(name="NewECU"))
        assert "NewECU" in db2.nodes
        assert "NewECU" not in db.nodes

    def test_add_node_duplicate_raises(self, db):
        with pytest.raises(ValueError):
            add_node(db, Node(name="ECU1"))

    def test_delete_node(self, db):
        db2 = delete_node(db, "GW")
        assert "GW" not in db2.nodes
        assert "GW" in db.nodes

    def test_delete_node_missing_raises(self, db):
        with pytest.raises(KeyError):
            delete_node(db, "Ghost")

    def test_rename_node(self, db):
        db2 = rename_node(db, "GW", "Gateway")
        assert "Gateway" in db2.nodes
        assert "GW" not in db2.nodes

    def test_rename_node_collision_raises(self, db):
        with pytest.raises(ValueError, match="ECU1"):
            rename_node(db, "GW", "ECU1")

    def test_rename_node_same_name_is_noop(self, db):
        db2 = rename_node(db, "GW", "GW")
        assert "GW" in db2.nodes

    def test_rename_node_updates_senders(self, db):
        db2 = rename_node(db, "ECU1", "EngineECU")
        # ECU1 is sender of EngineData (500)
        assert "EngineECU" in db2.messages[500].senders
        assert "ECU1" not in db2.messages[500].senders

    def test_rename_node_updates_receivers(self, db):
        db2 = rename_node(db, "GW", "Gateway")
        # GW is receiver of EngineSpeed
        assert "Gateway" in db2.messages[500].signals["EngineSpeed"].receivers
        assert "GW" not in db2.messages[500].signals["EngineSpeed"].receivers


# ── attribute mutations ───────────────────────────────────────────────────────

class TestAttributeMutations:
    def test_define_attribute(self, db):
        ad = AttributeDefinition(name="NewAttr", kind=AttributeKind.INT, object_type="BO_",
                                  minimum=0, maximum=1000)
        db2 = define_attribute(db, ad)
        assert "NewAttr" in db2.attributes
        assert "NewAttr" not in db.attributes

    def test_set_database_attribute(self, db):
        db2 = set_database_attribute(db, "DBVersion", "1.0")
        assert db2.attribute_values.get("DBVersion") == "1.0"

    def test_set_message_attribute(self, db):
        db2 = set_message_attribute(db, 500, "GenMsgCycleTime", 200)
        assert db2.messages[500].attributes["GenMsgCycleTime"] == 200
        assert db.messages[500].attributes.get("GenMsgCycleTime") == 100

    def test_set_signal_attribute(self, db):
        db2 = set_signal_attribute(db, 500, "EngineSpeed", "MyAttr", "test")
        assert db2.messages[500].signals["EngineSpeed"].attributes["MyAttr"] == "test"

    def test_set_node_attribute(self, db):
        db2 = set_node_attribute(db, "ECU1", "NodeAttr", 42)
        assert db2.nodes["ECU1"].attributes["NodeAttr"] == 42

    def test_unset_message_attribute(self, db):
        db2 = set_message_attribute(db, 500, "GenMsgCycleTime", 999)
        db3 = unset_message_attribute(db2, 500, "GenMsgCycleTime")
        assert "GenMsgCycleTime" not in db3.messages[500].attributes

    def test_unset_database_attribute(self, db):
        db2 = set_database_attribute(db, "DBVersion", "1.0")
        db3 = unset_database_attribute(db2, "DBVersion")
        assert "DBVersion" not in db3.attribute_values

    def test_unset_signal_attribute(self, db):
        db2 = set_signal_attribute(db, 500, "EngineSpeed", "MyAttr", "test")
        db3 = unset_signal_attribute(db2, 500, "EngineSpeed", "MyAttr")
        assert "MyAttr" not in db3.messages[500].signals["EngineSpeed"].attributes

    def test_unset_node_attribute(self, db):
        db2 = set_node_attribute(db, "ECU1", "NodeAttr", 42)
        db3 = unset_node_attribute(db2, "ECU1", "NodeAttr")
        assert "NodeAttr" not in db3.nodes["ECU1"].attributes

    def test_delete_attribute_removes_definition_and_values(self, db):
        db2 = define_attribute(db, AttributeDefinition(name="NodeAttr", kind=AttributeKind.INT, object_type="BU_"))
        db3 = set_node_attribute(db2, "ECU1", "NodeAttr", 42)
        db4 = delete_attribute(db3, "NodeAttr")
        assert "NodeAttr" not in db4.attributes
        assert "NodeAttr" not in db4.nodes["ECU1"].attributes
        assert "NodeAttr" in db3.attributes

    def test_set_node_attribute_missing_node_raises(self, db):
        with pytest.raises(KeyError):
            set_node_attribute(db, "NoSuchNode", "foo", "bar")
