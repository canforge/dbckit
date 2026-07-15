"""Tests for file-level DBC encoding behavior."""
from __future__ import annotations

from pathlib import Path

import pytest

import dbckit


def _dbc_bytes(unit: bytes) -> bytes:
    return (
        b'VERSION ""\nNS_ :\nBS_ :\nBU_ : ECU\n'
        b'BO_ 100 Temperature: 8 ECU\n'
        b' SG_ Value : 0|8@1+ (1,0) [0|255] "' + unit + b'" ECU\n'
    )


def test_load_falls_back_to_cp1252_without_corruption(tmp_path: Path):
    source = tmp_path / "vector.dbc"
    source.write_bytes(_dbc_bytes(b"\xb0C"))

    db = dbckit.load(source)

    assert db.messages[100].signals["Value"].unit == "°C"

    output = tmp_path / "roundtrip.dbc"
    dbckit.save(db, output)
    assert b"\xc2\xb0C" in output.read_bytes()
    assert b"\xef\xbf\xbd" not in output.read_bytes()


def test_load_explicit_encoding_is_strict(tmp_path: Path):
    source = tmp_path / "vector.dbc"
    source.write_bytes(_dbc_bytes(b"\xb0C"))

    with pytest.raises(UnicodeDecodeError):
        dbckit.load(source, encoding="utf-8")

    db = dbckit.load(source, encoding="cp1252")
    assert db.messages[100].signals["Value"].unit == "°C"


def test_save_accepts_explicit_encoding(tmp_path: Path):
    source = tmp_path / "utf8.dbc"
    source.write_bytes(_dbc_bytes("°C".encode()))
    db = dbckit.load(source)

    output = tmp_path / "vector.dbc"
    db.save(output, encoding="cp1252")

    assert b"\xb0C" in output.read_bytes()
