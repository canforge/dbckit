"""Tests for the Typer CLI surface."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

import dbckit
from dbckit.cli import app
from dbckit.model.database import Database
from dbckit.model.message import Message
from dbckit.model.signal import Signal

FIXTURES = Path(__file__).parent / "fixtures"
SIMPLE = FIXTURES / "simple.dbc"
COMPLEX = FIXTURES / "complex.dbc"

runner = CliRunner()


def _copy_fixture(tmp_path: Path, name: str = "simple.dbc") -> Path:
    src = FIXTURES / name
    dst = tmp_path / name
    shutil.copyfile(src, dst)
    return dst


def test_db_import_round_trip(tmp_path):
    runner = CliRunner()
    db = dbckit.load(FIXTURES / "simple.dbc")
    exported = tmp_path / "db.json"
    exported.write_text(db.model_dump_json(indent=2), encoding="utf-8")
    out_dbc = tmp_path / "imported.dbc"

    result = runner.invoke(app, ["db", "import", str(exported), "--out", str(out_dbc)])

    assert result.exit_code == 0, result.stdout
    imported = dbckit.load(out_dbc)
    assert set(imported.messages) == set(db.messages)


def test_message_update(tmp_path):
    runner = CliRunner()
    dbc_path = _copy_fixture(tmp_path)

    result = runner.invoke(
        app,
        ["message", "update", "--db", str(dbc_path), "500", "--cycle-time", "250", "--comment", "Updated"],
    )

    assert result.exit_code == 0, result.stdout
    db = dbckit.load(dbc_path)
    assert db.messages[500].attributes["GenMsgCycleTime"] == 250
    assert db.messages[500].comment == "Updated"


def test_signal_create(tmp_path):
    runner = CliRunner()
    dbc_path = _copy_fixture(tmp_path)

    result = runner.invoke(
        app,
        [
            "signal",
            "create",
            "--db",
            str(dbc_path),
            "500",
            "OilPressure",
            "--start-bit",
            "32",
            "--length",
            "16",
            "--factor",
            "0.5",
            "--unit",
            "kPa",
            "--receiver",
            "GW",
        ],
    )

    assert result.exit_code == 0, result.stdout
    db = dbckit.load(dbc_path)
    sig = db.messages[500].signals["OilPressure"]
    assert sig.factor == 0.5
    assert sig.unit == "kPa"
    assert sig.receivers == ["GW"]


def test_signal_update(tmp_path):
    runner = CliRunner()
    dbc_path = _copy_fixture(tmp_path)

    result = runner.invoke(
        app,
        [
            "signal",
            "update",
            "--db",
            str(dbc_path),
            "500",
            "EngineSpeed",
            "--factor",
            "0.25",
            "--unit",
            "rpm2",
            "--receiver",
            "ECU2",
        ],
    )

    assert result.exit_code == 0, result.stdout
    db = dbckit.load(dbc_path)
    sig = db.messages[500].signals["EngineSpeed"]
    assert sig.factor == 0.25
    assert sig.unit == "rpm2"
    assert sig.receivers == ["ECU2"]


def test_node_get_json(tmp_path):
    runner = CliRunner()
    dbc_path = _copy_fixture(tmp_path)

    result = runner.invoke(app, ["node", "get", "--db", str(dbc_path), "ECU1", "--output", "json"])

    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["name"] == "ECU1"


def test_attribute_get_json(tmp_path):
    runner = CliRunner()
    dbc_path = _copy_fixture(tmp_path)

    result = runner.invoke(
        app,
        ["attribute", "get", "--db", str(dbc_path), "GenMsgCycleTime", "--output", "json"],
    )

    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["name"] == "GenMsgCycleTime"
    assert payload["kind"] == "INT"


def test_attribute_define(tmp_path):
    runner = CliRunner()
    dbc_path = _copy_fixture(tmp_path)

    result = runner.invoke(
        app,
        [
            "attribute",
            "define",
            "--db",
            str(dbc_path),
            "NewAttr",
            "INT",
            "--scope",
            "BO_",
            "--minimum",
            "0",
            "--maximum",
            "10",
            "--default",
            "1",
        ],
    )

    assert result.exit_code == 0, result.stdout
    db = dbckit.load(dbc_path)
    attr = db.attributes["NewAttr"]
    assert attr.kind.value == "INT"
    assert attr.object_type == "BO_"
    assert attr.default == 1


def test_message_list_csv(tmp_path):
    runner = CliRunner()
    dbc_path = _copy_fixture(tmp_path)

    result = runner.invoke(app, ["message", "list", "--db", str(dbc_path), "--output", "csv"])

    assert result.exit_code == 0, result.stdout
    assert "arbitration_id,name,length,senders,signal_count" in result.stdout
    assert "500,EngineData,8,ECU1,3" in result.stdout


# ── db info ───────────────────────────────────────────────────────────────────

class TestDbInfo:
    def test_table_output_exits_zero(self):
        result = runner.invoke(app, ["db", "info", "--db", str(SIMPLE)])
        assert result.exit_code == 0

    def test_json_output_structure(self):
        result = runner.invoke(app, ["db", "info", "--db", str(SIMPLE), "-o", "json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["message_count"] >= 1
        assert isinstance(data["nodes"], list)

    def test_csv_output_has_headers(self):
        result = runner.invoke(app, ["db", "info", "--db", str(SIMPLE), "-o", "csv"])
        assert result.exit_code == 0
        assert "message_count" in result.output


# ── db validate ───────────────────────────────────────────────────────────────

class TestDbValidate:
    def test_clean_file_exits_zero(self):
        result = runner.invoke(app, ["db", "validate", "--db", str(SIMPLE)])
        assert result.exit_code == 0

    def _bad_dbc(self, tmp_path: Path) -> Path:
        # Signal (16 bits) exceeds message DLC (1 byte = 8 bits)
        bad = tmp_path / "bad.dbc"
        bad.write_text(
            'VERSION ""\nNS_ :\nBS_:\nBU_:\n'
            'BO_ 100 Msg1: 1 Vector__XXX\n'
            ' SG_ BigSig : 0|16@1+ (1,0) [0|0] "" Vector__XXX\n',
            encoding="utf-8",
        )
        return bad

    def test_file_with_errors_exits_one(self, tmp_path):
        result = runner.invoke(app, ["db", "validate", "--db", str(self._bad_dbc(tmp_path))])
        assert result.exit_code == 1

    def test_json_output_contains_issue_codes(self, tmp_path):
        result = runner.invoke(app, ["db", "validate", "--db", str(self._bad_dbc(tmp_path)), "-o", "json"])
        assert result.exit_code == 1
        issues = json.loads(result.output)
        assert any(i["code"] == "SIGNAL_EXCEEDS_LENGTH" for i in issues)


# ── db diff ───────────────────────────────────────────────────────────────────

class TestDbDiff:
    def test_identical_files_prints_no_differences(self):
        result = runner.invoke(app, ["db", "diff", str(SIMPLE), str(SIMPLE)])
        assert result.exit_code == 0
        assert "No differences" in result.output

    def test_different_files_shows_changes(self):
        result = runner.invoke(app, ["db", "diff", str(SIMPLE), str(COMPLEX)])
        assert result.exit_code == 0
        assert any(sym in result.output for sym in ["+", "-", "~"])

    def test_json_output_structure(self):
        result = runner.invoke(app, ["db", "diff", str(SIMPLE), str(SIMPLE), "-o", "json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["added_messages"] == []
        assert data["removed_messages"] == []

    def test_field_changes_shown_in_output(self, tmp_path):
        db = dbckit.load(SIMPLE)
        db2 = db.message(500).update(length=4)
        modified = tmp_path / "modified.dbc"
        dbckit.save(db2, modified)
        result = runner.invoke(app, ["db", "diff", str(SIMPLE), str(modified)])
        assert result.exit_code == 0
        assert "length" in result.output


# ── db extract ────────────────────────────────────────────────────────────────

class TestDbExtract:
    def test_extracts_message_to_new_file(self, tmp_path):
        out = tmp_path / "out.dbc"
        result = runner.invoke(app, [
            "db", "extract", "--db", str(SIMPLE), "500", "--out", str(out)
        ])
        assert result.exit_code == 0
        assert out.exists()
        extracted = dbckit.load(out)
        assert 500 in extracted.messages

    def test_unknown_id_exits_nonzero(self, tmp_path):
        out = tmp_path / "out.dbc"
        result = runner.invoke(app, [
            "db", "extract", "--db", str(SIMPLE), "0xDEAD", "--out", str(out)
        ])
        assert result.exit_code != 0


# ── message list / get ────────────────────────────────────────────────────────

class TestMessageCommands:
    def test_list_json(self):
        result = runner.invoke(app, ["message", "list", "--db", str(SIMPLE), "-o", "json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert any(m["name"] == "EngineData" for m in data)

    def test_list_filter_by_node(self):
        result = runner.invoke(app, ["message", "list", "--db", str(SIMPLE), "--node", "ECU1"])
        assert result.exit_code == 0
        assert "EngineData" in result.output

    def test_get_by_id_json(self):
        result = runner.invoke(app, ["message", "get", "--db", str(SIMPLE), "500", "-o", "json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["name"] == "EngineData"
        assert data["arbitration_id"] == 500

    def test_get_unknown_id_exits_one(self):
        result = runner.invoke(app, ["message", "get", "--db", str(SIMPLE), "0xDEAD"])
        assert result.exit_code == 1

    def test_search_json(self):
        result = runner.invoke(app, ["message", "search", "--db", str(SIMPLE), "Engine", "-o", "json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert any(m["name"] == "EngineData" for m in data)


# ── signal list / get ─────────────────────────────────────────────────────────

class TestSignalCommands:
    def test_list_json(self):
        result = runner.invoke(app, ["signal", "list", "--db", str(SIMPLE), "500", "-o", "json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert any(s["name"] == "EngineSpeed" for s in data)

    def test_list_csv_has_headers(self):
        result = runner.invoke(app, ["signal", "list", "--db", str(SIMPLE), "500", "-o", "csv"])
        assert result.exit_code == 0
        assert "start_bit" in result.output

    def test_get_json(self):
        result = runner.invoke(app, ["signal", "get", "--db", str(SIMPLE), "500", "EngineSpeed", "-o", "json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["name"] == "EngineSpeed"
        assert data["start_bit"] == 0
        assert data["length"] == 16


# ── node commands ─────────────────────────────────────────────────────────────

class TestNodeCommandsCoverage:
    def test_list_json(self):
        result = runner.invoke(app, ["node", "list", "--db", str(SIMPLE), "-o", "json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert any(n["name"] == "ECU1" for n in data)

    def test_get_unknown_exits_one(self):
        result = runner.invoke(app, ["node", "get", "--db", str(SIMPLE), "Ghost"])
        assert result.exit_code == 1


# ── decode frame ──────────────────────────────────────────────────────────────

class TestDecodeFrameCmd:
    def test_decode_table_output(self):
        db = dbckit.load(SIMPLE)
        frame = dbckit.encode_frame(db, 500, {"EngineSpeed": 1000.0, "EngineTemp": 90.0, "IgnitionStatus": 1})
        result = runner.invoke(app, ["decode", "frame", "--db", str(SIMPLE), "500", frame.hex()])
        assert result.exit_code == 0
        assert "EngineSpeed" in result.output
        assert "1000" in result.output

    def test_decode_json_output(self):
        db = dbckit.load(SIMPLE)
        frame = dbckit.encode_frame(db, 500, {"EngineSpeed": 500.0, "EngineTemp": 80.0, "IgnitionStatus": 0})
        result = runner.invoke(app, ["decode", "frame", "--db", str(SIMPLE), "500", frame.hex(), "-o", "json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["EngineSpeed"] == pytest.approx(500.0, rel=1e-3)


class TestDecodeLogCmd:
    def test_format_override(self, tmp_path):
        class OverrideReader:
            def read(self, path: Path):
                assert path.suffix == ".bin"
                yield dbckit.RawFrame(
                    timestamp=1.0,
                    arbitration_id=500,
                    data=bytes([0xE8, 0x03, 0, 0, 0, 0, 0, 0]),
                )

        dbckit.register_reader("cli-override", OverrideReader())

        result = runner.invoke(
            app,
            [
                "decode",
                "log",
                "--db",
                str(SIMPLE),
                str(tmp_path / "trace.bin"),
                "--format",
                "cli-override",
            ],
        )

        assert result.exit_code == 0, result.output
        assert "EngineSpeed=100.0" in result.output

    @staticmethod
    def _ambiguous_db() -> Database:
        messages = {}
        for arbitration_id, name in (
            (0x18F00402, "First"),
            (0x18F00401, "Second"),
        ):
            messages[arbitration_id] = Message(
                arbitration_id=arbitration_id,
                name=name,
                length=8,
                is_extended_frame=True,
                signals={"Value": Signal(name="Value", start_bit=0, length=8)},
            )
        return Database(messages=messages)

    @staticmethod
    def _register_ambiguous_reader():
        class AmbiguousReader:
            def read(self, path: Path):
                yield dbckit.RawFrame(
                    timestamp=2.5,
                    arbitration_id=0x0CF004AB,
                    data=b"\x2a" + b"\x00" * 7,
                    channel=4,
                    is_extended_frame=True,
                )

        dbckit.register_reader("cli-j1939", AmbiguousReader())

    def test_j1939_ambiguity_table_output(self, tmp_path, monkeypatch):
        self._register_ambiguous_reader()
        monkeypatch.setattr("dbckit.cli._load", lambda path: self._ambiguous_db())

        result = runner.invoke(
            app,
            [
                "decode",
                "log",
                "--db",
                str(SIMPLE),
                str(tmp_path / "trace.bin"),
                "--format",
                "cli-j1939",
                "--match",
                "j1939",
            ],
        )

        assert result.exit_code == 0, result.output
        assert "ambiguous J1939 match" in result.output
        assert "0x18f00402, 0x18f00401" in result.output

    def test_j1939_ambiguity_json_output(self, tmp_path, monkeypatch):
        self._register_ambiguous_reader()
        monkeypatch.setattr("dbckit.cli._load", lambda path: self._ambiguous_db())

        result = runner.invoke(
            app,
            [
                "decode",
                "log",
                "--db",
                str(SIMPLE),
                str(tmp_path / "trace.bin"),
                "--format",
                "cli-j1939",
                "--match",
                "j1939",
                "--output",
                "json",
            ],
        )

        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload["candidate_message_ids"] == [0x18F00402, 0x18F00401]
        assert payload["arbitration_id"] == 0x0CF004AB

    def test_j1939_decoded_json_includes_resolved_message_id(
        self,
        tmp_path,
        monkeypatch,
    ):
        self._register_ambiguous_reader()
        full_db = self._ambiguous_db()
        db = full_db.model_copy(
            update={"messages": {0x18F00401: full_db.messages[0x18F00401]}},
        )
        monkeypatch.setattr("dbckit.cli._load", lambda path: db)

        result = runner.invoke(
            app,
            [
                "decode",
                "log",
                "--db",
                str(SIMPLE),
                str(tmp_path / "trace.bin"),
                "--format",
                "cli-j1939",
                "--match",
                "j1939",
                "--output",
                "json",
            ],
        )

        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload["arbitration_id"] == 0x0CF004AB
        assert payload["message_arbitration_id"] == 0x18F00401
        assert payload["signals"] == {"Value": 42.0}

    def test_rejects_unknown_match_mode(self, tmp_path):
        result = runner.invoke(
            app,
            [
                "decode",
                "log",
                "--db",
                str(SIMPLE),
                str(tmp_path / "trace.asc"),
                "--match",
                "guess",
            ],
        )

        assert result.exit_code == 2
        assert "must be one of: exact, j1939, auto" in result.output


# ── encode frame ──────────────────────────────────────────────────────────────

class TestEncodeFrameCmd:
    def test_output_is_valid_hex_and_roundtrips(self):
        result = runner.invoke(app, [
            "encode", "frame", "--db", str(SIMPLE), "500",
            "EngineSpeed=1000.0", "EngineTemp=90.0", "IgnitionStatus=1",
        ])
        assert result.exit_code == 0
        raw = bytes.fromhex(result.output.strip())
        decoded = dbckit.decode_frame(dbckit.load(SIMPLE), 500, raw)
        assert decoded["EngineSpeed"] == pytest.approx(1000.0, rel=1e-3)


# ── codegen commands ──────────────────────────────────────────────────────────

class TestCodegenCmds:
    def test_python_stdout_has_decode_and_encode(self):
        result = runner.invoke(app, ["codegen", "python", "--db", str(SIMPLE)])
        assert result.exit_code == 0
        assert "def decode" in result.output
        assert "def encode" in result.output
        assert "NotImplementedError" not in result.output

    def test_python_to_file(self, tmp_path):
        out = tmp_path / "messages.py"
        result = runner.invoke(app, ["codegen", "python", "--db", str(SIMPLE), "--out", str(out)])
        assert result.exit_code == 0
        assert out.exists()
        content = out.read_text()
        assert "def decode" in content

    def test_markdown_has_signal_table(self):
        result = runner.invoke(app, ["codegen", "markdown", "--db", str(SIMPLE)])
        assert result.exit_code == 0
        assert "# DBC Documentation" in result.output
        assert "| Signal |" in result.output

    def test_json_schema_is_valid_json(self):
        result = runner.invoke(app, ["codegen", "json-schema", "--db", str(SIMPLE)])
        assert result.exit_code == 0
        schema = json.loads(result.output)
        assert "$schema" in schema
        assert "properties" in schema

    def test_c_contains_experimental_warning(self):
        result = runner.invoke(app, ["codegen", "c", "--db", str(SIMPLE)])
        assert result.exit_code == 0
        assert "EXPERIMENTAL" in result.output
