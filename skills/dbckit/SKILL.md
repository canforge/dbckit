---
name: dbckit
description: >
  Correct usage of the dbckit Python library and CLI for DBC (CAN database)
  files: loading, inspecting, decoding/encoding CAN frames and signals,
  validating, editing, diffing/merging, extracting, and decoding CAN logs.
  Use this skill whenever a task involves .dbc files, CAN bus databases,
  CAN frame or signal decoding, J1939 PGN/SPN lookup, or .asc log decoding
  in a project that has dbckit installed or mentions dbckit — even if the
  request doesn't name the library. This includes building tools, servers,
  or scripts ON TOP of dbckit (MCP servers, CI checks, converters). Also
  consult it before reaching for cantools idioms: dbckit's API is
  deliberately different (immutable, copy-on-write), and cantools habits
  produce silently wrong code.
---

# dbckit

dbckit is a Python library (`pip install dbckit`, CLI via `pip install "dbckit[cli]"`)
for working with DBC files. It is **not cantools** and does not share its API or
semantics. If you know cantools, read "Coming from cantools" below before writing
any code.

## The one rule that prevents silent data loss

**Every edit returns a NEW `Database`. Nothing is modified in place.**

```python
# WRONG — edits vanish; db is unchanged and the save writes the original
db = dbckit.load("vehicle.dbc")
db.message(0x1F4).rename("MotorData")     # returned Database discarded!
db.save("out.dbc")                        # saves the UNEDITED database

# RIGHT — capture each returned Database and chain from it
db = dbckit.load("vehicle.dbc")
db2 = db.message(0x1F4).rename("MotorData")
db3 = db2.message(0x1F4).signal("EngineSpeed").update(factor=0.5)
db4 = db3.add_node(dbckit.Node(name="Logger"))
db4.save("out.dbc")
```

A view (from `db.message(...)`) is bound to the database it came from. After an
edit, re-navigate from the *new* database — views from the old one still see the
old data.

## Reading vs. editing

- **Read**: `db.messages` is a `dict[int, Message]` keyed by arbitration ID;
  `db.nodes` is a `dict[str, Node]`. Iterate these for inspection.
- **Edit/decode via views**: `db.message(0x1F4)` → `MessageView`,
  `.signal("Name")` → `SignalView`, `db.node("ECU1")` → `NodeView`.
  `db.list_messages()` / `db.list_nodes()` give view lists.

```python
import dbckit

db = dbckit.load("vehicle.dbc")             # encoding= optional (utf-8→cp1252 fallback)
msg = db.message(0x1F4)                     # KeyError if absent
sig = msg.signal("EngineSpeed")

values = msg.decode(b"\xE8\x03\x00\x00\x00\x00\x00\x00")   # dict[str, float|int|str]
raw = msg.encode({"EngineSpeed": 825.0})    # unspecified signals zero-fill
one = sig.decode(raw)                       # single physical value
labeled = sig.decode_phys(raw)              # resolves value-table labels to str
```

Module-level equivalents: `dbckit.decode_frame(db, arb_id, data)`,
`dbckit.encode_frame(db, arb_id, values, strict=False)`. Encoding clamps
out-of-range values unless `strict=True` (then `ValueError`).

## Coming from cantools

| cantools habit | dbckit reality |
|---|---|
| `cantools.database.load_file(p)` | `dbckit.load(p)` |
| `db.get_message_by_frame_id(id)` | `db.message(id)` (view) or `db.messages[id]` (model) |
| `db.get_message_by_name(n)` | iterate `db.messages.values()` or `dbckit.search_messages(db, n)` |
| `msg.frame_id` | `msg.arbitration_id` |
| `db.decode_message(id, data)` | `dbckit.decode_frame(db, id, data)` |
| mutate object, then `db.dump_file(p)` | edits return a **new** `Database`; `db2.save(p)` |
| `msg.signals` (list) | `msg.signals` (dict `name → Signal` on the model) |
| `db.messages` (list) | `db.messages` (dict `arbitration_id → Message`) |

Do not import cantools in a dbckit task; the APIs don't interoperate directly.
(Third-party frame objects DO interoperate — see "Logs and frames".)

## Common operations

```python
from dbckit import Message, Signal, Node

# create
db2 = db.add_node(Node(name="Gateway"))
db3 = db2.add_message(Message(arbitration_id=0x400, name="BrakeData", length=8))
db4 = db3.message(0x400).add_signal(Signal(name="BrakePressure", start_bit=0, length=16))

# modify / delete existing entities — always through views
db5 = db4.message(0x400).update(cycle_time=20)
db6 = db5.message(0x400).signal("BrakePressure").update(factor=0.1, unit="kPa")
db7 = db6.message(0x400).delete_signal("BrakePressure")
db8 = db7.node("Gateway").delete()

# validate — structured issues, not exceptions
for issue in dbckit.validate(db8):          # strict=True → warnings become errors
    print(issue.severity, issue.code, issue.location, issue.message)

# cross-database
result = dbckit.diff(db_a, db_b)            # result.is_empty, added/removed/modified
merged = dbckit.merge(db_a, db_b, strategy="ours")   # raise | ours | theirs
sub = dbckit.extract(db, [0x100], message_names=["EngineData"], node_names=["Gateway"])

# J1939 attribute lookup
views = dbckit.find_messages_by_pgn(db, 61444)
owner_view, sig_view = db.signal_by_spn(190)
pgn = dbckit.pgn_from_arbitration_id(0x18F00401)

# codegen
text = dbckit.codegen(db, "python")         # "c" | "python" | "markdown" | "json-schema"
```

Signal fields: `start_bit`, `length`, `byte_order` (`ByteOrder.little_endian` /
`big_endian`), `is_signed`, `factor`, `offset`, `minimum`, `maximum`, `unit`,
`receivers`, `multiplex_indicator` (`"M"` or `"m0"`, `"m1"`, …).

## Logs and frames

```python
for frame in dbckit.decode_log(db, "trace.asc"):        # Vector .asc built in
    frame.timestamp, frame.arbitration_id, frame.signals

dbckit.decode_log(db, "capture.txt", format="asc")      # extension override

# any object with .timestamp, .arbitration_id, .data decodes — python-can included
decoded = dbckit.decode_frames(db, frames_iterable)     # iterator, no file I/O
decoded = dbckit.decode_frames(db, frames_iterable, match="j1939")
decoded = dbckit.decode_frames(db, frames_iterable, match="auto")
```

Other log formats: `dbckit.register_reader(".blf", reader)` or a package
exposing the `dbckit.readers` entry-point group.

## CLI

Command groups: `db`, `message`, `signal`, `node`, `attribute`, `decode`,
`encode`, `codegen`. Read commands accept `-o table|json|csv` — use `json` when
parsing output. **Edit commands rewrite the `--db` file in place** (unlike the
library). `db validate` exits non-zero on errors.

```bash
dbckit db info --db vehicle.dbc -o json
dbckit db validate --db vehicle.dbc --strict
dbckit db diff base.dbc changed.dbc
dbckit message list --db vehicle.dbc -o json
dbckit signal layout --db vehicle.dbc 0x1F4          # colored bit grid
dbckit decode frame --db vehicle.dbc 0x1F4 "E8 03 00 00 00 00 00 00"
dbckit decode log --db vehicle.dbc trace.asc --limit 100
dbckit encode frame --db vehicle.dbc 0x1F4 EngineSpeed=825
dbckit attribute set --db vehicle.dbc message:0x1F4 GenMsgCycleTime 100
```

Attribute targets: `node:ECU1`, `message:0x1F4`, `signal:0x1F4:Speed`, `""` = database.

## Hard limits — don't fight these

- **Extended multiplexing** (`m0M` indicators, `SG_MUL_VAL_`) is rejected at
  parse time with a clear error. There is no workaround flag; simple `M`/`mX`
  multiplexing is fully supported.
- **CAN FD** is untested/unsupported; `.sym`, `.kcd`, ARXML are out of scope.
- **J1939** lookup helpers need explicit `PGN`/`SPN` attribute values. Frame
  decoding can match by a PGN derived from 29-bit IDs with `match="j1939"`;
  `match="auto"` requires a valid `PGN` or J1939 `ProtocolType` marker.
- Encoding zero-fills unspecified signals and ignores `GenSigStartValue`.
- Missing entities raise `KeyError`; duplicates, rename collisions, and mux
  contradictions raise `ValueError`. Parsing rejects dangling `CM_`/`BA_`/`VAL_`
  references instead of dropping them — a file that won't load is malformed,
  not a dbckit bug.

## Full reference

Bundled with this skill — read them instead of searching installed sources or
the web when a question goes beyond this file:

- `references/api-reference.md` — the complete public API contract, including
  every model field, method signature, raise condition, and codec edge case
- `references/cli.md` — every CLI command and option
- `references/dbc-support.md` — which DBC sections are fully/partially/not
  supported, and round-trip guarantees
