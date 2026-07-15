# `dbckit` CLI Reference

The CLI is a thin shell over the public Python API. Install it with the `cli`
extra:

```bash
pip install "dbckit[cli]"
```

Run `dbckit` with no arguments to see the command groups:

| Group | Purpose |
|---|---|
| `dbckit db` | Database-level commands (info, validate, diff, merge, extract, export, import) |
| `dbckit message` | Message commands |
| `dbckit signal` | Signal commands |
| `dbckit node` | Node commands |
| `dbckit attribute` | Attribute definition and value commands |
| `dbckit decode` | Decode frames, signals, and log files |
| `dbckit encode` | Encode signal values into frame payloads |
| `dbckit codegen` | Code/doc generation |

## Conventions

- Most commands take `--db <path>` pointing at the `.dbc` file to operate on.
- Arbitration IDs are accepted in hex (`0x1F4`) or decimal (`500`).
- Read-oriented commands accept `--output` / `-o` with `table` (default),
  `json`, or `csv`. Commands that list only some of these formats below do not
  implement the others.
- **Edit commands rewrite the `--db` file in place.** The library API is
  copy-on-write, but the CLI saves the result back to the same path.
- Commands exit non-zero on errors (missing message/signal/node/attribute,
  validation errors, bad arguments).

---

## `dbckit db`

### `db info --db FILE [-o table|json|csv]`

Show high-level database info: version, nodes, message count, attribute count,
value-table count.

```bash
dbckit db info --db vehicle.dbc
```

### `db validate --db FILE [--strict] [-o table|json|csv]`

Validate the database and list issues (severity, code, location, message).

- `--strict` treats warnings as errors.
- Exits `1` when any error-severity issue is found, in every output format.

```bash
dbckit db validate --db vehicle.dbc --strict -o json
```

### `db diff BASE CHANGED [-o table|json]`

Diff two DBC files. The table output shows added/removed/modified messages,
field-level changes, and per-signal changes; `-o json` prints the full
`DiffResult`.

```bash
dbckit db diff base.dbc changed.dbc
```

### `db merge BASE OTHER OUT [--strategy raise|ours|theirs]`

Merge `OTHER` into `BASE` and write the result to `OUT`.

- `--strategy raise` (default) fails on conflicts.
- `--strategy ours` keeps `BASE` values on conflict; `theirs` keeps `OTHER`.

```bash
dbckit db merge base.dbc feature.dbc merged.dbc --strategy ours
```

### `db extract --db FILE IDS... --out OUT`

Extract the given messages (by arbitration ID) into a new DBC file.

```bash
dbckit db extract --db vehicle.dbc 0x100 0x200 --out subset.dbc
```

### `db export --db FILE [--out OUT.json]`

Export the full database model as JSON (to stdout, or to `--out`).

### `db import SRC.json --out OUT.dbc`

Rebuild a database from previously exported JSON and write it as DBC.

```bash
dbckit db export --db vehicle.dbc --out vehicle.json
dbckit db import vehicle.json --out roundtrip.dbc
```

---

## `dbckit message`

### `message list --db FILE [--node NAME] [--pgn PGN] [-o table|json|csv]`

List messages, optionally filtered by sender node and/or J1939 PGN attribute
value.

```bash
dbckit message list --db vehicle.dbc --node ECU1
```

### `message get --db FILE [ARB_ID] [--pgn PGN] [-o table|json|csv]`

Show one message (details plus its signal table). Provide exactly one of
`ARB_ID` or `--pgn`.

```bash
dbckit message get --db vehicle.dbc 0x1F4
dbckit message get --db vehicle.dbc --pgn 61444
```

### `message search --db FILE QUERY [-o table|json|csv]`

Search messages by name/comment.

### `message create --db FILE ARB_ID NAME [--length/-l BYTES] [--sender NODE]`

Add a new message. `--length` defaults to 8.

```bash
dbckit message create --db vehicle.dbc 0x400 BrakeData --length 8 --sender ECU1
```

### `message update --db FILE ARB_ID [--length/-l BYTES] [--sender NODE ...] [--comment TEXT] [--cycle-time MS]`

Update message fields. `--sender` may be repeated and **replaces** the sender
list. `--cycle-time` sets the `GenMsgCycleTime` attribute (kept in sync with
`Message.cycle_time`). At least one field is required.

### `message delete --db FILE ARB_ID`

Delete a message.

### `message rename --db FILE ARB_ID NEW_NAME`

Rename a message.

---

## `dbckit signal`

### `signal list --db FILE ARB_ID [-o table|json|csv]`

List signals in a message (start bit, length, byte order, factor, offset, unit,
mux indicator).

### `signal get --db FILE ARB_ID SIGNAL [-o table|json|csv]`

Show one signal, including receivers, comment, and value-table entries.

### `signal search --db FILE QUERY [-o table|json|csv]`

Search signals by name/comment across all messages.

### `signal layout --db FILE ARB_ID`

Render a colored 8-column bit grid of the message layout, with a per-signal
legend.

### `signal create --db FILE ARB_ID NAME --start-bit N --length N [options]`

Add a new signal. Options:

- `--byte-order little_endian|big_endian` (default `little_endian`)
- `--signed` / `--unsigned` (default unsigned)
- `--factor F` (default 1.0), `--offset F` (default 0.0)
- `--minimum F`, `--maximum F`
- `--unit TEXT`
- `--receiver NODE` (repeat as needed)
- `--comment TEXT`
- `--multiplex M|mX` — multiplex indicator, e.g. `M` or `m0`

```bash
dbckit signal create --db vehicle.dbc 0x400 BrakePressure \
    --start-bit 0 --length 16 --factor 0.1 --unit kPa
```

### `signal update --db FILE ARB_ID SIGNAL [options]`

Update signal fields; accepts the same options as `signal create` (all
optional, at least one required). A repeated `--receiver` replaces the
receiver list.

### `signal delete --db FILE ARB_ID SIGNAL`

Delete a signal from a message.

### `signal rename --db FILE ARB_ID SIGNAL NEW_NAME`

Rename a signal.

### `signal add-choice --db FILE ARB_ID SIGNAL VALUE LABEL`

Add a value-description (choice) to a signal's value table.

```bash
dbckit signal add-choice --db vehicle.dbc 0x1F4 IgnitionStatus 2 Crank
```

### `signal remove-choice --db FILE ARB_ID SIGNAL VALUE`

Remove a value-description from a signal.

---

## `dbckit node`

### `node list --db FILE [-o table|json|csv]`

List all nodes with comments.

### `node get --db FILE NAME [-o table|json|csv]`

Show one node (comment and attribute values).

### `node create --db FILE NAME [--comment TEXT]`

Add a new node.

### `node delete --db FILE NAME`

Delete a node.

### `node rename --db FILE NAME NEW_NAME`

Rename a node.

---

## `dbckit attribute`

### `attribute list --db FILE [-o table|json|csv]`

List attribute definitions (name, kind, scope, range, default).

### `attribute get --db FILE NAME [-o table|json|csv]`

Show one attribute definition, including enum values.

### `attribute define --db FILE NAME KIND [options]`

Define (or redefine) an attribute definition.

- `KIND` is one of `INT`, `HEX`, `FLOAT`, `STRING`, `ENUM`.
- `--scope DB|BU_|BO_|SG_|EV_` (default `DB`)
- `--minimum F`, `--maximum F`
- `--default VALUE` (parsed according to `KIND`)
- `--enum-value VALUE` (repeat as needed, for `ENUM`)

```bash
dbckit attribute define --db vehicle.dbc GenMsgCycleTime INT \
    --scope BO_ --minimum 0 --maximum 10000 --default 100
```

### `attribute set --db FILE TARGET NAME VALUE`

Set an attribute value on a target. `TARGET` selects the object:

- `""` (empty string) — the database itself
- `node:ECU1`
- `message:0x1F4`
- `signal:0x1F4:EngineSpeed`

The value is parsed according to the attribute's defined kind when the
definition exists; otherwise it is stored as a string.

```bash
dbckit attribute set --db vehicle.dbc message:0x1F4 GenMsgCycleTime 100
```

### `attribute unset --db FILE TARGET NAME`

Remove an attribute value from a target (same `TARGET` syntax as `set`).

### `attribute delete --db FILE NAME`

Delete an attribute definition and all values that reference it.

---

## `dbckit decode`

### `decode frame --db FILE ARB_ID HEX_DATA [-o table|json]`

Decode a frame payload into signal values. `HEX_DATA` is a hex string (spaces
allowed).

```bash
dbckit decode frame --db vehicle.dbc 0x1F4 "E8 03 00 00 00 00 00 00"
```

### `decode signal --db FILE ARB_ID SIGNAL HEX_DATA`

Decode a single signal from frame bytes and print its physical value with the
unit.

### `decode log --db FILE LOG_PATH [--limit N] [--format EXT] [-o table|json]`

Decode frames from a CAN log file. The reader is selected by file extension
(`.asc` is built in; more can be registered via `dbckit.register_reader()` or
the `dbckit.readers` entry-point group).

- `--limit N` stops after N frames (0 = all).
- `--format EXT` overrides extension-based reader selection for oddly named
  files, with or without a leading dot (e.g. `--format asc`).

```bash
dbckit decode log --db vehicle.dbc trace.asc --limit 100
dbckit decode log --db vehicle.dbc capture.txt --format asc
```

---

## `dbckit encode`

### `encode frame --db FILE ARB_ID NAME=VALUE...`

Encode signal values into a frame payload and print it as uppercase hex.
Unspecified signals are zero-filled.

```bash
dbckit encode frame --db vehicle.dbc 0x1F4 EngineSpeed=825 EngineTemp=90
```

---

## `dbckit codegen`

### `codegen c|python|markdown|json-schema --db FILE [--out PATH]`

Generate code or docs from the database, to stdout or `--out`.

- `c` — C header (experimental; decode stubs are marked in the output)
- `python` — self-contained dataclasses with working `decode()`/`encode()`
- `markdown` — human-readable message/signal documentation
- `json-schema` — JSON Schema describing decoded frame payloads

```bash
dbckit codegen c --db vehicle.dbc --out engine.h
dbckit codegen markdown --db vehicle.dbc --out messages.md
```
