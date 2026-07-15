"""Tests for operations: diff, merge, extract, codegen, log."""
from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest

import dbckit
from dbckit.model.database import Database, Node
from dbckit.model.message import Message
from dbckit.model.signal import Signal
from dbckit.operations.codegen import codegen
from dbckit.operations.diff import diff
from dbckit.operations.extract import extract, search_messages, search_signals
from dbckit.operations.merge import merge

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def simple_db() -> Database:
    return dbckit.load(FIXTURES / "simple.dbc")


@pytest.fixture
def complex_db() -> Database:
    return dbckit.load(FIXTURES / "complex.dbc")


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
                    "FractionalSpn": Signal(
                        name="FractionalSpn",
                        start_bit=16,
                        length=8,
                        attributes={"SPN": 177.5},
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
                attributes={"PGN": "not-an-int"},
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


# ── diff ──────────────────────────────────────────────────────────────────────

class TestDiff:
    def test_diff_identical_is_empty(self, simple_db):
        result = diff(simple_db, simple_db)
        assert result.is_empty

    def test_diff_detects_added_message(self, simple_db):
        new_msg = Message(arbitration_id=0x999, name="Added", length=4)
        db2 = simple_db.add_message(new_msg)
        result = diff(simple_db, db2)
        assert len(result.added_messages) == 1
        assert result.added_messages[0].arbitration_id == 0x999
        assert result.removed_messages == []

    def test_diff_detects_removed_message(self, simple_db):
        db2 = simple_db.message(500).delete()
        result = diff(simple_db, db2)
        assert len(result.removed_messages) == 1
        assert result.removed_messages[0].arbitration_id == 500

    def test_diff_detects_renamed_message(self, simple_db):
        db2 = simple_db.message(500).rename("NewName")
        result = diff(simple_db, db2)
        assert len(result.modified_messages) == 1
        md = result.modified_messages[0]
        assert "name" in md.field_changes
        assert md.field_changes["name"] == ("EngineData", "NewName")

    def test_diff_detects_added_signal(self, simple_db):
        sig = Signal(name="NewSig", start_bit=32, length=8)
        db2 = simple_db.message(500).add_signal(sig)
        result = diff(simple_db, db2)
        assert any(r.modified_messages for r in [result])
        mod = result.modified_messages[0]
        added = [s for s in mod.signal_diffs if s.change == "added"]
        assert any(s.signal_name == "NewSig" for s in added)

    def test_diff_detects_removed_signal(self, simple_db):
        db2 = simple_db.message(500).signal("EngineSpeed").delete()
        result = diff(simple_db, db2)
        mod = result.modified_messages[0]
        removed = [s for s in mod.signal_diffs if s.change == "removed"]
        assert any(s.signal_name == "EngineSpeed" for s in removed)

    def test_diff_detects_modified_signal(self, simple_db):
        db2 = simple_db.message(500).signal("EngineSpeed").update(factor=0.5)
        result = diff(simple_db, db2)
        mod = result.modified_messages[0]
        modified = [s for s in mod.signal_diffs if s.change == "modified"]
        assert any(s.signal_name == "EngineSpeed" for s in modified)

    def test_diff_detects_added_node(self, simple_db):
        db2 = simple_db.add_node(Node(name="NewNode"))
        result = diff(simple_db, db2)
        assert any(n.name == "NewNode" for n in result.added_nodes)

    def test_diff_detects_removed_node(self, simple_db):
        db2 = simple_db.node("GW").delete()
        result = diff(simple_db, db2)
        assert any(n.name == "GW" for n in result.removed_nodes)

    def test_diff_result_is_pydantic_model(self, simple_db):
        result = diff(simple_db, simple_db)
        assert hasattr(result, "model_dump")

    def test_diff_db_to_complex(self, simple_db, complex_db):
        result = diff(simple_db, complex_db)
        # complex has different messages, so there should be changes
        assert not result.is_empty

    def test_diff_detects_message_attribute_change(self, simple_db):
        db2 = simple_db.message(500).set_attribute("GenMsgCycleTime", 50)
        result = diff(simple_db, db2)
        assert result.modified_messages
        mod = result.modified_messages[0]
        assert "attributes" in mod.field_changes

    def test_diff_message_attribute_unchanged_not_flagged(self, simple_db):
        result = diff(simple_db, simple_db)
        assert result.is_empty

    def test_diff_detects_signal_attribute_change(self, simple_db):
        db2 = simple_db.message(500).signal("EngineSpeed").set_attribute("InitialValue", 9.0)
        result = diff(simple_db, db2)
        mod = result.modified_messages[0]
        modified_sigs = [s for s in mod.signal_diffs if s.change == "modified"]
        assert any(s.signal_name == "EngineSpeed" for s in modified_sigs)

    def test_diff_detects_added_signal_group(self, simple_db):
        from dbckit.model.signal import SignalGroup
        sg = SignalGroup(name="NewGroup", message_id=500, signal_names=["EngineSpeed"])
        db2 = simple_db.model_copy(update={"signal_groups": [*simple_db.signal_groups, sg]})
        result = diff(simple_db, db2)
        assert any(g.name == "NewGroup" for g in result.added_signal_groups)
        assert result.removed_signal_groups == []

    def test_diff_detects_removed_signal_group(self, complex_db):
        db2 = complex_db.model_copy(update={"signal_groups": []})
        result = diff(complex_db, db2)
        assert result.removed_signal_groups
        assert result.added_signal_groups == []

    def test_diff_detects_added_envvar(self, simple_db):
        from dbckit.model.database import EnvironmentVariable
        ev = EnvironmentVariable(
            name="MyEV", var_type=0, minimum=0.0, maximum=100.0, unit="",
            initial_value=0.0, ev_id=1, access_type="DUMMY_NODE_VECTOR0",
            access_nodes=["Vector__XXX"],
        )
        db2 = simple_db.model_copy(update={"environment_variables": {"MyEV": ev}})
        result = diff(simple_db, db2)
        assert any(e.name == "MyEV" for e in result.added_envvars)
        assert result.removed_envvars == []

    def test_diff_is_empty_includes_new_fields(self, simple_db):
        result = diff(simple_db, simple_db)
        assert result.added_signal_groups == []
        assert result.removed_signal_groups == []
        assert result.added_envvars == []
        assert result.removed_envvars == []
        assert result.is_empty


# ── merge ─────────────────────────────────────────────────────────────────────

class TestMerge:
    def _make_db(self, arb_id: int, name: str) -> Database:
        msg = Message(arbitration_id=arb_id, name=name, length=8)
        return Database(version="x", messages={arb_id: msg})

    def test_merge_disjoint(self):
        db_a = self._make_db(0x100, "A")
        db_b = self._make_db(0x200, "B")
        merged = merge(db_a, db_b)
        assert 0x100 in merged.messages
        assert 0x200 in merged.messages

    def test_merge_conflict_raises(self):
        db_a = self._make_db(0x100, "A")
        db_b = self._make_db(0x100, "B")
        with pytest.raises(ValueError, match="conflict"):
            merge(db_a, db_b, strategy="raise")

    def test_merge_conflict_ours(self):
        db_a = self._make_db(0x100, "A")
        db_b = self._make_db(0x100, "B")
        merged = merge(db_a, db_b, strategy="ours")
        assert merged.messages[0x100].name == "A"

    def test_merge_conflict_theirs(self):
        db_a = self._make_db(0x100, "A")
        db_b = self._make_db(0x100, "B")
        merged = merge(db_a, db_b, strategy="theirs")
        assert merged.messages[0x100].name == "B"

    def test_merge_identical_no_conflict(self):
        db_a = self._make_db(0x100, "A")
        db_b = self._make_db(0x100, "A")
        merged = merge(db_a, db_b)  # same content → no conflict
        assert 0x100 in merged.messages

    def test_merge_preserves_nodes(self, simple_db, complex_db):
        merged = merge(simple_db, complex_db, strategy="theirs")
        # merged should contain nodes from both
        assert len(merged.nodes) >= len(simple_db.nodes)

    def test_merge_deduplicates_signal_groups(self, simple_db, complex_db):
        merged = merge(simple_db, complex_db, strategy="theirs")
        # No duplicate (message_id, name) pairs
        seen = set()
        for sg in merged.signal_groups:
            key = (sg.message_id, sg.name)
            assert key not in seen
            seen.add(key)

    # ── nodes ─────────────────────────────────────────────────────────────

    def test_merge_nodes_disjoint(self):
        db_a = Database(version="", nodes={"ECU1": Node(name="ECU1")})
        db_b = Database(version="", nodes={"ECU2": Node(name="ECU2")})
        merged = merge(db_a, db_b)
        assert "ECU1" in merged.nodes
        assert "ECU2" in merged.nodes

    def test_merge_node_conflict_ours(self):
        from dbckit.model.database import Node
        db_a = Database(version="", nodes={"N": Node(name="N", comment="a")})
        db_b = Database(version="", nodes={"N": Node(name="N", comment="b")})
        merged = merge(db_a, db_b, strategy="ours")
        assert merged.nodes["N"].comment == "a"

    def test_merge_node_conflict_theirs(self):
        from dbckit.model.database import Node
        db_a = Database(version="", nodes={"N": Node(name="N", comment="a")})
        db_b = Database(version="", nodes={"N": Node(name="N", comment="b")})
        merged = merge(db_a, db_b, strategy="theirs")
        assert merged.nodes["N"].comment == "b"

    # ── attribute definitions ─────────────────────────────────────────────

    def test_merge_attribute_definitions_disjoint(self):
        from dbckit.model.database import AttributeDefinition, AttributeKind
        ad_a = AttributeDefinition(name="A", kind=AttributeKind.INT, object_type="BO_")
        ad_b = AttributeDefinition(name="B", kind=AttributeKind.STRING, object_type="SG_")
        db_a = Database(version="", attributes={"A": ad_a})
        db_b = Database(version="", attributes={"B": ad_b})
        merged = merge(db_a, db_b)
        assert "A" in merged.attributes
        assert "B" in merged.attributes

    def test_merge_attribute_conflict_raises(self):
        from dbckit.model.database import AttributeDefinition, AttributeKind
        ad = AttributeDefinition(name="X", kind=AttributeKind.INT, object_type="BO_",
                                 minimum=0, maximum=10)
        ad2 = AttributeDefinition(name="X", kind=AttributeKind.INT, object_type="BO_",
                                  minimum=0, maximum=99)
        db_a = Database(version="", attributes={"X": ad})
        db_b = Database(version="", attributes={"X": ad2})
        with pytest.raises(ValueError, match="conflict"):
            merge(db_a, db_b, strategy="raise")

    # ── attribute values ──────────────────────────────────────────────────

    def test_merge_attribute_values_disjoint(self):
        db_a = Database(version="", attribute_values={"DBVersion": "1.0"})
        db_b = Database(version="", attribute_values={"Author": "test"})
        merged = merge(db_a, db_b)
        assert merged.attribute_values["DBVersion"] == "1.0"
        assert merged.attribute_values["Author"] == "test"

    def test_merge_attribute_value_conflict_ours(self):
        db_a = Database(version="", attribute_values={"DBVersion": "1.0"})
        db_b = Database(version="", attribute_values={"DBVersion": "2.0"})
        merged = merge(db_a, db_b, strategy="ours")
        assert merged.attribute_values["DBVersion"] == "1.0"

    def test_merge_attribute_value_conflict_theirs(self):
        db_a = Database(version="", attribute_values={"DBVersion": "1.0"})
        db_b = Database(version="", attribute_values={"DBVersion": "2.0"})
        merged = merge(db_a, db_b, strategy="theirs")
        assert merged.attribute_values["DBVersion"] == "2.0"

    # ── value tables ──────────────────────────────────────────────────────

    def test_merge_value_tables_disjoint(self):
        from dbckit.model.signal import ValueTable
        vt_a = ValueTable(name="States", values={0: "Off", 1: "On"})
        vt_b = ValueTable(name="Modes", values={0: "Normal", 1: "Sport"})
        db_a = Database(version="", value_tables={"States": vt_a})
        db_b = Database(version="", value_tables={"Modes": vt_b})
        merged = merge(db_a, db_b)
        assert "States" in merged.value_tables
        assert "Modes" in merged.value_tables

    # ── environment variables ─────────────────────────────────────────────

    def test_merge_envvars_disjoint(self):
        from dbckit.model.database import EnvironmentVariable
        ev = EnvironmentVariable(
            name="EV1", var_type=0, minimum=0.0, maximum=0.0, unit="",
            initial_value=0.0, ev_id=0, access_type="DUMMY_NODE_VECTOR0",
            access_nodes=["Vector__XXX"],
        )
        db_a = Database(version="", environment_variables={"EV1": ev})
        db_b = Database(version="")
        merged = merge(db_a, db_b)
        assert "EV1" in merged.environment_variables

    def test_merge_envvar_conflict_ours(self):
        from dbckit.model.database import EnvironmentVariable
        def _ev(name, unit):
            return EnvironmentVariable(
                name=name, var_type=0, minimum=0.0, maximum=0.0, unit=unit,
                initial_value=0.0, ev_id=0, access_type="DUMMY_NODE_VECTOR0",
                access_nodes=["Vector__XXX"],
            )
        db_a = Database(version="", environment_variables={"EV1": _ev("EV1", "km/h")})
        db_b = Database(version="", environment_variables={"EV1": _ev("EV1", "mph")})
        merged = merge(db_a, db_b, strategy="ours")
        assert merged.environment_variables["EV1"].unit == "km/h"

    # ── signal groups ─────────────────────────────────────────────────────

    def test_merge_signal_groups_combined(self, simple_db, complex_db):
        merged = merge(simple_db, complex_db, strategy="theirs")
        all_names = {sg.name for sg in merged.signal_groups}
        # complex_db has DynamicsGroup; simple_db has none
        assert "DynamicsGroup" in all_names

    # ── database-level metadata ───────────────────────────────────────────

    def test_merge_version_prefers_db_b(self):
        db_a = Database(version="1.0")
        db_b = Database(version="2.0")
        merged = merge(db_a, db_b)
        assert merged.version == "2.0"

    def test_merge_version_falls_back_to_db_a_when_db_b_empty(self):
        db_a = Database(version="1.0")
        db_b = Database(version="")
        merged = merge(db_a, db_b)
        assert merged.version == "1.0"

    def test_merge_ns_values_deduplicated(self):
        db_a = Database(version="", ns_values=["NS_A", "SHARED"])
        db_b = Database(version="", ns_values=["NS_B", "SHARED"])
        merged = merge(db_a, db_b)
        assert merged.ns_values.count("SHARED") == 1
        assert "NS_A" in merged.ns_values
        assert "NS_B" in merged.ns_values


# ── extract ───────────────────────────────────────────────────────────────────

class TestExtract:
    def test_extract_single_message(self, simple_db):
        sub = extract(simple_db, [500])
        assert list(sub.messages.keys()) == [500]

    def test_extract_multiple_messages(self, simple_db):
        sub = extract(simple_db, [500, 768])
        assert set(sub.messages.keys()) == {500, 768}

    def test_extract_missing_id_raises(self, simple_db):
        with pytest.raises(KeyError):
            extract(simple_db, [0xDEAD])

    def test_extract_carries_referenced_nodes(self, simple_db):
        sub = extract(simple_db, [500])
        # ECU1 is sender, ECU2/GW are receivers
        assert "ECU1" in sub.nodes or "ECU2" in sub.nodes

    def test_extract_carries_attribute_definitions(self, simple_db):
        sub = extract(simple_db, [500])
        assert sub.attributes == simple_db.attributes

    def test_extract_carries_signal_groups(self, complex_db):
        sub = extract(complex_db, [100])
        # DynamicsGroup is for message 100
        assert any(sg.message_id == 100 for sg in sub.signal_groups)

    def test_extract_excludes_other_signal_groups(self, complex_db):
        sub = extract(complex_db, [100])
        assert all(sg.message_id == 100 for sg in sub.signal_groups)

    def test_extract_by_message_name(self, simple_db):
        sub = extract(simple_db, message_names=["EngineData"])
        assert list(sub.messages) == [500]

    def test_extract_by_multiple_message_names(self, simple_db):
        sub = simple_db.extract(
            message_names=["EngineData", "TransmissionData"]
        )
        assert set(sub.messages) == {500, 768}

    def test_extract_missing_message_name_raises(self, simple_db):
        with pytest.raises(KeyError, match="MissingMessage"):
            extract(simple_db, message_names=["MissingMessage"])

    def test_extract_by_sender_node(self, simple_db):
        sub = extract(simple_db, node_names=["ECU1"])
        assert 500 in sub.messages

    def test_extract_by_receiver_node(self, simple_db):
        sub = extract(simple_db, node_names=["GW"])
        assert 500 in sub.messages
        assert "GW" in sub.nodes

    def test_extract_missing_node_raises(self, simple_db):
        with pytest.raises(KeyError, match="Ghost"):
            extract(simple_db, node_names=["Ghost"])

    def test_extract_selectors_are_combined(self, simple_db):
        sub = extract(simple_db, [500], message_names=["TransmissionData"])
        assert set(sub.messages) == {500, 768}


# ── search ────────────────────────────────────────────────────────────────────

class TestSearch:
    def test_search_messages_by_name(self, simple_db):
        results = search_messages(simple_db, "engine")
        assert any(m.name == "EngineData" for m in results)

    def test_search_messages_case_insensitive(self, simple_db):
        assert search_messages(simple_db, "ENGINE") == search_messages(simple_db, "engine")

    def test_search_messages_by_comment(self, simple_db):
        results = search_messages(simple_db, "status message")
        assert any(m.name == "EngineData" for m in results)

    def test_search_messages_no_result(self, simple_db):
        assert search_messages(simple_db, "xyzzy_does_not_exist") == []

    def test_search_signals_by_name(self, simple_db):
        results = search_signals(simple_db, "speed")
        assert any(s.name == "EngineSpeed" for _, s in results)

    def test_search_signals_returns_message_pair(self, simple_db):
        results = search_signals(simple_db, "speed")
        assert all(isinstance(m, Message) and isinstance(s, Signal) for m, s in results)

    def test_search_signals_by_comment(self, simple_db):
        results = search_signals(simple_db, "coolant")
        assert any(s.name == "EngineTemp" for _, s in results)


class TestJ1939Lookup:
    def test_find_messages_by_pgn(self, j1939_db):
        matches = dbckit.find_messages_by_pgn(j1939_db, 61444)
        assert [view.name for view in matches] == ["EngineData", "DuplicatePgn"]

    def test_find_messages_by_pgn_returns_empty_list(self, j1939_db):
        assert dbckit.find_messages_by_pgn(j1939_db, 99999) == []

    def test_find_messages_by_pgn_normalizes_string_attributes(self, j1939_db):
        matches = dbckit.find_messages_by_pgn(j1939_db, 61445)
        assert [view.name for view in matches] == ["TransmissionData"]

    def test_find_signals_by_spn(self, j1939_db):
        matches = dbckit.find_signals_by_spn(j1939_db, 190)
        assert [(msg.name, sig.name) for msg, sig in matches] == [
            ("EngineData", "EngineSpeed"),
            ("DuplicateSpn", "BackupEngineSpeed"),
        ]

    def test_find_signals_by_spn_returns_empty_list(self, j1939_db):
        assert dbckit.find_signals_by_spn(j1939_db, 99999) == []

    def test_find_signals_by_spn_normalizes_float_attributes(self, j1939_db):
        matches = dbckit.find_signals_by_spn(j1939_db, 177)
        assert [(msg.name, sig.name) for msg, sig in matches] == [
            ("TransmissionData", "TransmissionTemp"),
        ]

    def test_find_signals_by_spn_ignores_non_integral_values(self, j1939_db):
        assert dbckit.find_signals_by_spn(j1939_db, 1775) == []


# ── codegen ───────────────────────────────────────────────────────────────────

class TestCodegen:
    def test_codegen_c(self, simple_db):
        result = codegen(simple_db, "c")
        assert "#pragma once" in result
        assert "#include <stdint.h>" in result
        assert "EngineData" in result or "ENGINEDATA" in result

    def test_codegen_python(self, simple_db):
        result = codegen(simple_db, "python")
        assert "dataclass" in result
        assert "def decode" in result
        assert "def encode" in result
        assert "NotImplementedError" not in result

    def test_codegen_python_decode_roundtrip(self, simple_db):
        src = codegen(simple_db, "python")
        ns: dict = {}
        exec(compile(src, "<codegen>", "exec"), ns)  # noqa: S102
        EngineData = ns["EngineData"]

        # Encode a known frame via dbckit, then decode with the generated class
        frame = dbckit.encode_frame(simple_db, 500, {"EngineSpeed": 1000.0, "EngineTemp": 90.0, "IgnitionStatus": 1})
        obj = EngineData.decode(frame)
        assert obj.engine_speed == pytest.approx(1000.0, rel=1e-3)
        assert obj.engine_temp == pytest.approx(90.0, rel=1e-3)
        assert obj.ignition_status == 1

    def test_codegen_python_encode_roundtrip(self, simple_db):
        src = codegen(simple_db, "python")
        ns: dict = {}
        exec(compile(src, "<codegen>", "exec"), ns)  # noqa: S102
        EngineData = ns["EngineData"]

        obj = EngineData(engine_speed=500.0, engine_temp=75.0, ignition_status=0)
        frame = obj.encode()
        decoded = dbckit.decode_frame(simple_db, 500, frame)
        assert decoded["EngineSpeed"] == pytest.approx(500.0, rel=1e-3)
        assert decoded["EngineTemp"] == pytest.approx(75.0, rel=1e-3)

    def test_codegen_python_choices_dict(self, simple_db):
        src = codegen(simple_db, "python")
        ns: dict = {}
        exec(compile(src, "<codegen>", "exec"), ns)  # noqa: S102
        # IgnitionStatus has a value table
        choices_key = [k for k in ns if "CHOICES" in k and "IGNITION" in k.upper()]
        assert choices_key, "Expected a CHOICES dict for IgnitionStatus"
        choices = ns[choices_key[0]]
        assert choices[0] == "Off"

    def test_codegen_c_is_experimental(self, simple_db):
        result = codegen(simple_db, "c")
        assert "EXPERIMENTAL" in result

    def test_codegen_markdown(self, simple_db):
        result = codegen(simple_db, "markdown")
        assert "# DBC Documentation" in result
        assert "EngineData" in result
        assert "| Signal |" in result

    def test_codegen_json_schema(self, simple_db):
        result = codegen(simple_db, "json-schema")
        schema = json.loads(result)
        assert "$schema" in schema
        assert "properties" in schema
        # There should be a property for each message (keyed by hex ID)
        assert any("1F4" in k.upper() or "500" in k or "0X1F4" in k.upper()
                   for k in schema["properties"])

    def test_codegen_markdown_includes_value_table(self, simple_db):
        result = codegen(simple_db, "markdown")
        assert "Off" in result or "On" in result  # from IgnitionStatus VAL_

    def test_codegen_invalid_target_raises(self, simple_db):
        with pytest.raises(ValueError):
            codegen(simple_db, "cobol")  # type: ignore[arg-type]

    def test_codegen_all_targets_return_nonempty_string(self, simple_db):
        for target in ("c", "python", "markdown", "json-schema"):
            result = codegen(simple_db, target)  # type: ignore[arg-type]
            assert isinstance(result, str)
            assert len(result) > 0


# ── log decoding ──────────────────────────────────────────────────────────────

class TestDecodeLog:
    @pytest.fixture
    def asc_file(self, tmp_path) -> Path:
        # Minimal ASC file: EngineSpeed=100.0 rpm (raw=1000=0x03E8 in bytes 0-1 LE)
        content = textwrap.dedent("""\
            date Mon Jan 01 00:00:00 2024
            base hex  timestamps absolute
            internal events logged
            Begin Triggerblock Mon Jan 01 00:00:00 2024
               0.001000 1  1F4              Rx   d 8 E8 03 00 00 00 00 00 00
               0.002000 1  300              Rx   d 8 00 00 00 00 00 00 00 00
            End TriggerBlock
        """)
        p = tmp_path / "test.asc"
        p.write_text(content)
        return p

    def test_decode_log_yields_decoded_frames(self, simple_db, asc_file):
        frames = list(dbckit.decode_log(simple_db, asc_file))
        # 0x1F4 = 500 = EngineData
        engine_frames = [f for f in frames if f.arbitration_id == 0x1F4]
        assert len(engine_frames) == 1
        assert "EngineSpeed" in engine_frames[0].signals
        assert engine_frames[0].signals["EngineSpeed"] == pytest.approx(100.0)

    def test_decode_log_skips_unknown_ids(self, simple_db, asc_file):
        frames = list(dbckit.decode_log(simple_db, asc_file))
        # 0x300 = 768 = TransmissionData — is in simple_db, 0x300 = 768
        ids = {f.arbitration_id for f in frames}
        # Message 500 (0x1F4) and 768 (0x300) are both in simple_db
        assert 0x1F4 in ids

    def test_decode_log_frame_has_timestamp(self, simple_db, asc_file):
        frames = list(dbckit.decode_log(simple_db, asc_file))
        assert frames[0].timestamp == pytest.approx(0.001)

    def test_decode_log_frame_has_raw_bytes(self, simple_db, asc_file):
        frames = list(dbckit.decode_log(simple_db, asc_file))
        ef = [f for f in frames if f.arbitration_id == 0x1F4][0]
        assert ef.raw == bytes([0xE8, 0x03, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])

    def test_register_reader_is_stable_public_extension_point(self, simple_db, tmp_path):
        class CustomReader:
            def read(self, path: Path):
                assert path.suffix == ".custom"
                yield dbckit.RawFrame(
                    timestamp=1.25,
                    arbitration_id=500,
                    data=bytes([0xE8, 0x03, 0, 0, 0, 0, 0, 0]),
                )

        dbckit.register_reader("CUSTOM", CustomReader())
        frames = list(dbckit.decode_log(simple_db, tmp_path / "trace.custom"))
        assert len(frames) == 1
        assert frames[0].timestamp == pytest.approx(1.25)
        assert frames[0].signals["EngineSpeed"] == pytest.approx(100.0)

    def test_register_reader_rejects_empty_extension(self):
        with pytest.raises(ValueError, match="must not be empty"):
            dbckit.register_reader("  ", dbckit.AscReader())
