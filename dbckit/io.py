"""File-level I/O helpers."""
from __future__ import annotations

from pathlib import Path

from dbckit.model.database import Database
from dbckit.parser.grammar import parse_string
from dbckit.parser.preprocessor import (
    UnsupportedPolicy,
    validate_unsupported_policy,
)
from dbckit.parser.tokenizer import normalize
from dbckit.serializer import dump as _dump


def load(
    path: str | Path,
    *,
    encoding: str | None = None,
    on_unsupported: UnsupportedPolicy = "raise",
) -> Database:
    """Load a DBC file, trying strict UTF-8 then cp1252 by default."""
    policy = validate_unsupported_policy(on_unsupported)
    p = Path(path)
    raw = p.read_bytes()
    if encoding is not None:
        text = raw.decode(encoding)
    else:
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            text = raw.decode("cp1252")
    db = parse_string(normalize(text), on_unsupported=policy)
    return db.model_copy(update={"filename": str(p)})


def save(db: Database, path: str | Path, *, encoding: str = "utf-8") -> None:
    """Serialize *db* to DBC format and write it using *encoding*."""
    Path(path).write_text(_dump(db), encoding=encoding)
