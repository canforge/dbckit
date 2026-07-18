# Recipes

Common tasks composed from dbckit's public API and the standard library. Log
recipes stream one frame at a time unless noted.

All examples assume:

```python
import dbckit
```

## Validate and group issues by severity

```python
db = dbckit.load("vehicle.dbc")
by_severity = {"error": [], "warning": []}

for issue in dbckit.validate(db):
    by_severity[issue.severity].append(issue)

for severity, issues in by_severity.items():
    print(f"{severity}: {len(issues)}")
    for issue in issues:
        print(f"  {issue.code} {issue.location}: {issue.message}")
```

## Summarize a database diff

```python
before = dbckit.load("vehicle.base.dbc")
after = dbckit.load("vehicle.dbc")
changes = dbckit.diff(before, after)

print(f"+{len(changes.added_messages)} -{len(changes.removed_messages)} "
      f"~{len(changes.modified_messages)} messages")
for change in changes.modified_messages:
    fields = ", ".join(change.field_changes) or "signals"
    print(f"  {change.arbitration_id:#x} {change.message_name}: {fields}")
```

## Extract messages by ID, name, or node

```python
db = dbckit.load("vehicle.dbc")
subset = dbckit.extract(
    db,
    [0x100, 0x200],
    message_names=["EngineData"],
    node_names=["Gateway"],
)
dbckit.save(subset, "powertrain.dbc")
```

## Normalize a third-party DBC

```python
dbckit.save(dbckit.load("vendor.dbc"), "vendor.normalized.dbc")
```

## Set a cycle time across matching messages

Every edit returns a new database, so keep the result and re-navigate from it.

```python
db = dbckit.load("vehicle.dbc")
matching_ids = [mid for mid, msg in db.messages.items() if msg.name.startswith("Powertrain")]

for arbitration_id in matching_ids:
    db = db.message(arbitration_id).update(cycle_time=100)

db.save("vehicle.updated.dbc")
```

## Decode an ASC log to CSV

This streams in constant memory; the signal map is JSON inside the last column.

```python
import csv
import json

db = dbckit.load("vehicle.dbc")
with open("decoded.csv", "w", newline="") as out:
    writer = csv.writer(out)
    writer.writerow(["timestamp", "frame_id", "message_id", "signals"])
    for frame in dbckit.decode_log(db, "trace.asc"):
        ids = f"{frame.arbitration_id:X}", f"{frame.message_arbitration_id:X}"
        writer.writerow([frame.timestamp, *ids, json.dumps(frame.signals)])
```

## Load a messy DBC without hiding decode risk

Inspect the global rollup and per-message safety before decoding.

```python
db = dbckit.load("vendor.dbc", on_unsupported="skip")

for diagnostic in db.parse_diagnostics:
    print(diagnostic.line, diagnostic.construct, diagnostic.effect, diagnostic.detail)

print("globally decode-safe:", db.decode_safe)
for arbitration_id, safe in db.message_decode_safety.items():
    if not safe:
        print(f"unsafe message: {arbitration_id:#x}")
```

## Resolve J1939 frames by PGN

Both stages are lazy, and ambiguous PGN matches stay explicit.

```python
from pathlib import Path

db = dbckit.load("j1939.dbc")
raw_frames = dbckit.AscReader().read(Path("trace.asc"))

for frame in dbckit.decode_frames(db, raw_frames, match="j1939"):
    if isinstance(frame, dbckit.AmbiguousFrameMatch):
        print("ambiguous:", frame.candidate_message_ids)
    else:
        print(frame.timestamp, frame.message_arbitration_id, frame.signals)
```

## Generate a standalone Python decoder

```python
from pathlib import Path

db = dbckit.load("vehicle.dbc")
source = dbckit.codegen(db, "python")
Path("vehicle_decoder.py").write_text(source, encoding="utf-8")
```
