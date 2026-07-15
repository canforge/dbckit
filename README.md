# dbckit

[![PyPI](https://img.shields.io/pypi/v/dbckit)](https://pypi.org/project/dbckit/)
[![CI](https://github.com/canforge/dbckit/actions/workflows/ci.yml/badge.svg)](https://github.com/canforge/dbckit/actions/workflows/ci.yml)
[![Python versions](https://img.shields.io/pypi/pyversions/dbckit)](https://pypi.org/project/dbckit/)
[![Downloads](https://static.pepy.tech/badge/dbckit)](https://pepy.tech/project/dbckit)
[![License: MIT](https://img.shields.io/pypi/l/dbckit)](LICENSE)

`dbckit` is a Python library for working with **DBC (CAN database) files**.

Use it to:

- load and inspect DBC files
- decode CAN payloads into physical signal values — integers, floats, and doubles
- encode signal values back into CAN payloads
- validate DBC content
- apply deterministic edits and write the result back out
- diff, merge, extract, and search databases
- decode CAN log files (`.asc` built in, extensible readers) and in-memory frame streams

<p align="center">
  <img src="https://raw.githubusercontent.com/canforge/dbckit/main/docs/assets/signal-layout.svg" alt="dbckit signal layout rendering a colored bit grid of the VehicleSpeed message in the terminal" width="620">
</p>
<p align="center"><em>Output of <code>dbckit signal layout</code> — per-signal colored bit grid of a message.</em></p>

## Install

```bash
pip install dbckit
pip install "dbckit[cli]"   # adds the dbckit command-line tool
```

Requires Python `>=3.11`.

## Design

`dbckit` is built around typed data models with database-bound Views:

- `Database` is for navigation, top-level creation, cross-database operations,
  and persistence.
- `MessageView`, `SignalView`, and `NodeView` (returned by `db.message()`,
  `msg.signal()`, `db.node()`) are the normal way to modify or delete existing
  entities.
- Edit operations are copy-on-write: they return a new `Database` and never
  mutate the original.

## Quick Start

```python
import dbckit

db = dbckit.load("vehicle.dbc")

# inspect
print(db.version, len(db.messages))

msg = db.message(0x1F4)
sig = msg.signal("EngineSpeed")
print(sig.start_bit, sig.length, sig.factor, sig.unit)

# decode / encode a frame payload
values = msg.decode(bytes([0xE8, 0x03, 0, 0, 0, 0, 0, 0]))
raw = msg.encode({"EngineSpeed": 825.0, "EngineTemp": 90.0})

# validate
for issue in dbckit.validate(db):
    print(issue.severity, issue.code, issue.location)

# edits return a new Database
db2 = sig.update(factor=0.5)
db3 = db2.message(0x1F4).rename("MotorData")
db4 = db3.node("ECU1").rename("EngineECU")

db4.save("vehicle.updated.dbc")
```

## Features

### Parse and I/O

`dbckit.load()` / `dbckit.save()` for files, `dbckit.parse()` / `dbckit.dump()`
for strings. Loading tries strict UTF-8 first and falls back to cp1252 (common
in Vector-exported files); pass `encoding=` to either function to force one:

```python
db = dbckit.load("vehicle.dbc", encoding="latin-1")
dbckit.save(db, "copy.dbc", encoding="utf-8")
```

### Codec

Message-level `decode_frame()` / `encode_frame()` and signal-level
`decode_signal()` / `encode_signal()`. Both integer signals and IEEE-754
float/double signals (`SIG_VALTYPE_`) are supported, in Intel and Motorola
byte order. Encoding clamps out-of-range values by default; pass `strict=True`
to raise `ValueError` instead. Unspecified signals are zero-filled.

Simple DBC multiplexing (one `M` selector, `mX` variants) is fully supported
for decode, encode, and validation. Extended/nested multiplexing (`m0M`) is
unsupported and rejected during parsing with a clear error.

### Editing

Views cover renames, field updates, signal add/delete, sender and receiver
edits, arbitration-ID changes, value-table choices, and attribute values.
`Database` covers top-level creation and signal groups:

```python
from dbckit import Message, Signal, Node, SignalGroup

db2 = db.add_node(Node(name="Gateway"))
db3 = db2.add_message(Message(arbitration_id=0x400, name="BrakeData", length=8))
db4 = db3.message(0x400).add_signal(Signal(name="BrakePressure", start_bit=0, length=16))
db5 = db4.message(0x400).set_attribute("GenMsgCycleTime", 20)
db6 = db5.add_signal_group(SignalGroup(name="BrakeGroup", message_id=0x400, repetitions=1))
db7 = db6.add_signal_to_group(0x400, "BrakeGroup", "BrakePressure")
db7.save("vehicle.updated.dbc")
```

### Validation

`dbckit.validate(db)` returns structured issues (severity, code, location,
message) covering duplicate/invalid IDs, signal overlap and overflow,
multiplexing problems, missing senders/receivers, and attribute violations.
The full issue-code list is in the [API reference](docs/api-reference.md).

### Operations

```python
result = dbckit.diff(db_a, db_b)
merged = dbckit.merge(db_a, db_b, strategy="ours")   # raise | ours | theirs

sub = dbckit.extract(db, [0x100, 0x200])
sub = dbckit.extract(db, message_names=["EngineData"], node_names=["Gateway"])

messages = dbckit.search_messages(db, "engine")
pairs = dbckit.search_signals(db, "speed")
```

J1939 helpers look up messages and signals by explicit `PGN`/`SPN` attribute
values:

```python
matches = dbckit.find_messages_by_pgn(db, 61444)
owner, sig = db.signal_by_spn(177)
```

### Log and frame decoding

`decode_log()` streams decoded frames from a log file. Vector CANalyzer `.asc`
is built in (including extended 29-bit IDs); other formats plug in through
`register_reader()` or the `dbckit.readers` entry-point group, and
`format=` overrides extension-based detection for oddly named files:

```python
for frame in dbckit.decode_log(db, "trace.asc"):
    print(frame.timestamp, hex(frame.arbitration_id), frame.signals)

frames = dbckit.decode_log(db, "capture.txt", format="asc")
```

`decode_frames()` does the same for any iterable of frame objects — no file
I/O required. Anything with `timestamp`, `arbitration_id`, and `data`
attributes satisfies the `FrameLike` protocol, so frames from `python-can` or
your own tooling decode directly:

```python
decoded = dbckit.decode_frames(db, my_frames)   # Iterator[DecodedFrame]
```

### Code generation

```python
header = dbckit.codegen(db, "c")          # experimental
module = dbckit.codegen(db, "python")     # dataclasses with decode()/encode()
doc = dbckit.codegen(db, "markdown")
schema = dbckit.codegen(db, "json-schema")
```

## CLI

The `cli` extra installs a `dbckit` command with `db`, `message`, `signal`,
`node`, `attribute`, `decode`, `encode`, and `codegen` groups. Output formats
are `table`, `json`, and `csv`.

```bash
dbckit db info --db vehicle.dbc
dbckit db validate --db vehicle.dbc
dbckit db diff base.dbc changed.dbc
dbckit message list --db vehicle.dbc
dbckit signal layout --db vehicle.dbc 0x1F4
dbckit decode frame --db vehicle.dbc 0x1F4 "E8 03 00 00 00 00 00 00"
dbckit decode log --db vehicle.dbc trace.asc
dbckit codegen markdown --db vehicle.dbc --out docs.md
```

See the [CLI reference](docs/cli.md) for every command and option.

## Scope and Caveats

- Classic CAN DBC workflows are the supported surface; CAN FD is untested and
  FD-specific flags such as `VFrameFormat` are not interpreted.
- `.sym`, `.kcd`, and ARXML database formats are out of scope.
- J1939 helpers use explicit `PGN`/`SPN` attribute values only; they do not
  derive PGNs from 29-bit arbitration IDs.
- Frame encoding zero-fills unspecified signals and ignores `GenSigStartValue`.
- Mutation helpers are pure at the `Database` level, but the underlying
  Pydantic models are not frozen objects.

## Documentation

- [API reference](docs/api-reference.md) — the detailed public API contract,
  including codec overflow/error behavior and validation issue codes
- [DBC support matrix](docs/dbc-support.md) — which DBC sections and
  constructs are fully, partially, or not supported
- [CLI reference](docs/cli.md) — every command and option

## Development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

## License

MIT
