# `dbckit` API Reference

Version covered: `1.1.0`

This file documents the public Python API exported by:

- `dbckit`
- `dbckit.model`
- `dbckit.codec`
- `dbckit.parser`
- `dbckit.operations`

Excluded on purpose:

- CLI commands in `dbckit/cli.py` — see the [CLI reference](cli.md)
- Low-level mutation helper modules under `dbckit.mutations.*`
- Internal helpers prefixed with `_`

## API conventions

- Models are Pydantic v2 `BaseModel` types.
- Mutation helpers are copy-on-write: they return a new `Database` and do not mutate the input `Database`.
- Missing referenced objects usually raise `KeyError`.
- Duplicate inserts, merge conflicts, and unsupported codegen targets raise `ValueError`.
- Arbitration IDs are plain Python `int` values.

## Public import surface

Canonical imports:

```python
import dbckit
from dbckit import Database, Message, Signal, Node
```

Views are returned by `Database.message()` and `Database.node()`. They are
database-bound handles used for edits; most callers do not import them directly.

Equivalent submodule imports:

```python
from dbckit.model import Database, Message, Signal
from dbckit.codec import decode_frame, decode_signal, encode_frame, encode_signal
from dbckit.parser import parse_string, normalize
from dbckit.operations import (
    diff,
    merge,
    extract,
    codegen,
    decode_frames,
    decode_log,
    AmbiguousFrameMatch,
    FrameMatchMode,
    FrameLike,
    find_messages_by_pgn,
    find_signals_by_spn,
    pgn_from_arbitration_id,
)
```

## Data model

### `AttributeKind`

Enum values:

- `AttributeKind.INT`
- `AttributeKind.HEX`
- `AttributeKind.FLOAT`
- `AttributeKind.STRING`
- `AttributeKind.ENUM`

### `ByteOrder`

Enum values:

- `ByteOrder.little_endian`
- `ByteOrder.big_endian`

### `AttributeDefinition`

Pydantic model describing a `BA_DEF_` entry.

Fields:

- `name: str`
- `kind: AttributeKind`
- `object_type: str = ""`
- `minimum: float | None = None`
- `maximum: float | None = None`
- `values: list[str] = []`
- `default: Any = None`

### `Node`

Fields:

- `name: str`
- `comment: str | None = None`
- `attributes: dict[str, Any] = {}`

### `EnvironmentVariable`

Public from `dbckit.model`, not re-exported from `dbckit`.

Fields:

- `name: str`
- `var_type: int = 0`
- `minimum: float = 0.0`
- `maximum: float = 0.0`
- `unit: str = ""`
- `initial_value: float = 0.0`
- `ev_id: int = 0`
- `access_type: str = ""`
- `access_nodes: list[str] = []`
- `comment: str | None = None`
- `data_size: int | None = None`
- `attributes: dict[str, Any] = {}`
- `value_table: ValueTable | None = None`

### `Issue`

Validation finding returned by `validate()`.

Fields:

- `severity: Literal["error", "warning"]`
- `code: str`
- `location: str`
- `message: str`

### `ParseDiagnostic`

Source metadata recorded when lenient parsing skips an unsupported construct or
dangling reference.

Fields:

- `construct: str`
- `line: int` — one-based normalized source line
- `message_id: int | None = None`
- `signal_name: str | None = None`
- `effect: Literal["decode_degraded", "cosmetic"]`
- `detail: str`

### `ValueTable`

Fields:

- `name: str`
- `values: dict[int, str] = {}`

### `BitSlot`

Returned by `MessageView.layout()`.

Fields:

- `bit: int`
- `signal_name: str | None = None`
- `is_msb: bool = False`
- `is_lsb: bool = False`
- `byte_order: ByteOrder | None = None`

### `Signal`

Fields:

- `name: str`
- `start_bit: int`
- `length: int`
- `byte_order: ByteOrder = ByteOrder.little_endian`
- `is_signed: bool = False`
- `factor: float = 1.0`
- `offset: float = 0.0`
- `minimum: float | None = None`
- `maximum: float | None = None`
- `unit: str = ""`
- `receivers: list[str] = []`
- `comment: str | None = None`
- `value_table: ValueTable | None = None`
- `attributes: dict[str, Any] = {}`
- `multiplex_indicator: str | None = None`
- `signal_type: int | None = None` — `SIG_VALTYPE_` override: `1` for a
  32-bit IEEE-754 float, `2` for a 64-bit IEEE-754 double; `None` or `0` uses
  the integer codec

Multiplexing contract:

- simple multiplexing is supported: one signal marked `M`, with variants marked
  `mX` where `X` is a non-negative selector value (`m0`, `m1`, and so on)
- extended/nested multiplexing (`mXM`, for example `m0M`) is not supported and
  is rejected at parse time with `NotImplementedError` wrapped by Lark's
  `VisitError`

### `SignalGroup`

Fields:

- `name: str`
- `message_id: int`
- `signal_names: list[str] = []`
- `repetitions: int = 1`

### `Message`

Fields:

- `arbitration_id: int`
- `name: str`
- `length: int`
- `is_extended_frame: bool = False` — whether DBC serialization applies the
  bit-31 marker for a 29-bit CAN arbitration ID
- `senders: list[str] = []`
- `signals: dict[str, Signal] = {}`
- `comment: str | None = None`
- `attributes: dict[str, Any] = {}`
- `cycle_time: int | None = None`

`cycle_time` and the message attribute `GenMsgCycleTime` are synchronized. Direct
construction, parsing, and the pure mutation APIs populate both representations;
an explicitly supplied `cycle_time` wins if both values conflict. Cycle times must
be integral. An existing `GenMsgCycleTime` definition controls the accepted range
and is never widened. Mutations synthesize `BA_DEF_ BO_ "GenMsgCycleTime" INT 0
2147483647` with default `0` only when no definition exists.

### `Database`

Top-level DBC object.

Fields:

- `version: str = ""`
- `filename: str | None = None`
- `nodes: dict[str, Node] = {}`
- `messages: dict[int, Message] = {}`
- `attributes: dict[str, AttributeDefinition] = {}`
- `attribute_values: dict[str, Any] = {}`
- `value_tables: dict[str, ValueTable] = {}`
- `signal_groups: list[SignalGroup] = []`
- `environment_variables: dict[str, EnvironmentVariable] = {}`
- `ns_values: list[str] = []`
- `bit_timing: str | None = None`
- `dbc_specific: dict[str, Any] = {}`
- `parse_diagnostics: list[ParseDiagnostic] = []`

`parse_diagnostics` is source metadata. It is not emitted by `dump()` and does
not participate in semantic database diffing.

### Lenient parsing and decode safety

`Database.decode_safe` is a derived global rollup. It is false when any parse
diagnostic has `effect == "decode_degraded"`; cosmetic diagnostics do not make
it false. `Database.is_decode_safe` is an alias.

`Database.message_decode_safety` derives a mapping for every surviving message.
`Database.message_decode_safe(arbitration_id)` returns one entry and raises
`KeyError` for an unknown ID; `is_message_decode_safe()` is an alias. A scoped
degrading diagnostic marks only its affected message unsafe. An unscoped
degrading diagnostic makes the global rollup unsafe without guessing which
individual message was affected.

## Database Methods

`Database` is the primary object for:

- navigation
- top-level creation
- cross-database operations
- persistence

### Navigation

#### `Database.message(arbitration_id: int) -> MessageView`

Returns a `MessageView` for an existing message.

Raises:

- `KeyError` if the message ID does not exist

#### `Database.node(name: str) -> NodeView`

Returns a `NodeView` for an existing node.

Raises:

- `KeyError` if the node does not exist

#### `Database.list_messages() -> list[MessageView]`

Returns all messages as `MessageView` instances.

#### `Database.list_nodes() -> list[NodeView]`

Returns all nodes as `NodeView` instances.

### J1939 lookup

These helpers currently read J1939 metadata from DBC attribute values:

- message attribute: `PGN`
- signal attribute: `SPN`

#### `Database.message_by_pgn(pgn: int) -> MessageView`

Returns the unique `MessageView` whose `PGN` attribute matches `pgn`.

Raises:

- `KeyError` if no message has that PGN
- `ValueError` if multiple messages have that PGN

#### `Database.signal_by_spn(spn: int) -> tuple[MessageView, SignalView]`

Returns the unique `(MessageView, SignalView)` pair whose `SPN` attribute matches `spn`.

Raises:

- `KeyError` if no signal has that SPN
- `ValueError` if multiple signals have that SPN

### Top-level creation

#### `Database.add_message(msg: Message) -> Database`

Adds a message keyed by `msg.arbitration_id`.

Raises:

- `ValueError` if the arbitration ID already exists

#### `Database.add_node(nd: Node) -> Database`

Adds a node keyed by `nd.name`.

Raises:

- `ValueError` if the node name already exists

#### `Database.define_attribute(ad: AttributeDefinition) -> Database`

Adds or replaces an attribute definition in `db.attributes`.

#### `Database.delete_attribute(name: str) -> Database`

Removes:

- the attribute definition from `db.attributes`
- the database-level value from `db.attribute_values`
- all message-level values
- all signal-level values

#### `Database.add_signal_group(group: SignalGroup) -> Database`

Adds a signal group after validating its message and listed signals.

#### `Database.remove_signal_group(message_id: int, name: str) -> Database`

Removes the named signal group from a message.

#### `Database.add_signal_to_group(message_id: int, group_name: str, signal_name: str) -> Database`

Adds an existing signal to an existing signal group.

#### `Database.remove_signal_from_group(message_id: int, group_name: str, signal_name: str) -> Database`

Removes a signal from an existing signal group.

Signal-group methods are copy-on-write. Missing messages, signals, groups, or
members raise `KeyError`; duplicate groups or members raise `ValueError`.

## Views

Modify/delete operations for existing entities are View-first.

### `MessageView`

Returned by `Database.message()`.

Common properties:

- `arbitration_id: int`
- `name: str`
- `length: int`
- `senders: list[str]`
- `comment: str | None`
- `attributes: dict[str, Any]`
- `cycle_time: int | None`

Navigation and codec:

#### `MessageView.signal(name: str) -> SignalView`

Returns a `SignalView` for an existing signal.

Raises:

- `KeyError` if the signal does not exist

#### `MessageView.list_signals() -> list[SignalView]`

Returns all signals as `SignalView` instances.

#### `MessageView.layout() -> list[BitSlot]`

Returns one `BitSlot` per bit in `message.length * 8`.

#### `MessageView.decode(data: bytes) -> dict[str, float | int | str]`

Decodes all signals in the message and resolves value-table matches to labels.

#### `MessageView.encode(values: dict[str, float]) -> bytes`

Encodes selected signal values into a new payload buffer sized to the message DLC.

Raises:

- `KeyError` if any provided signal name is not present in the message

Existing-entity edits:

#### `MessageView.update(**fields) -> Database`

Updates selected message fields.

#### `MessageView.delete() -> Database`

Deletes the current message and its signal groups.

#### `MessageView.rename(new_name: str) -> Database`

Renames the current message.

#### `MessageView.change_arbitration_id(new_id: int) -> Database`

Renumbers the current message, preserving message order and extended-frame state
and updating matching `SignalGroup.message_id` references. The same ID is a no-op;
a missing source raises `KeyError`, and an occupied destination raises `ValueError`.
The module-level pure function is importable as
`dbckit.mutations.message.change_arbitration_id` but is not re-exported at the
package root.

#### `MessageView.add_sender(sender: str) -> Database`

Appends a transmitter. Raises `ValueError` if it is already present.

#### `MessageView.remove_sender(sender: str) -> Database`

Removes a transmitter. Raises `KeyError` if it is not present.

#### `MessageView.add_signal(sig: Signal) -> Database`

Adds a signal to the current message.

Raises:

- `ValueError` if the signal name already exists

#### `MessageView.delete_signal(name: str) -> Database`

Deletes a signal from the current message and removes it from every signal group
attached to that message.

#### `MessageView.rename_signal(old_name: str, new_name: str) -> Database`

Renames a signal in the current message and updates its name in every signal group
attached to that message.

Raises `ValueError` if `new_name` belongs to another signal in the message.

#### `MessageView.update_signal(name: str, **fields) -> Database`

Updates selected fields on a signal in the current message.

Passing `name` raises `ValueError`; use `rename_signal()` so signal-group
memberships are updated atomically.

#### `MessageView.set_attribute(name: str, value: Any) -> Database`

Sets a message-level attribute value.

#### `MessageView.unset_attribute(name: str) -> Database`

Removes a message-level attribute value.

### `SignalView`

Returned by `MessageView.signal()`.

Common properties:

- `name: str`
- `start_bit: int`
- `length: int`
- `byte_order: ByteOrder`
- `is_signed: bool`
- `factor: float`
- `offset: float`
- `minimum: float | None`
- `maximum: float | None`
- `unit: str`
- `receivers: list[str]`
- `comment: str | None`
- `value_table: ValueTable | None`
- `attributes: dict[str, Any]`
- `multiplex_indicator: str | None`

Decode helpers:

#### `SignalView.decode(data: bytes) -> float`

Returns the physical value for this signal.

#### `SignalView.decode_phys(data: bytes) -> float | str`

Returns the resolved value-table label when present, otherwise the physical value.

#### `SignalView.choices() -> dict[int, str] | None`

Returns a copy of the signal value-table mapping.

#### `SignalView.choice(val: int) -> str | None`

Returns the label for one raw integer value.

Existing-entity edits:

#### `SignalView.update(**fields) -> Database`

Updates selected signal fields.

Passing `name` raises `ValueError`; use `rename()` instead.

#### `SignalView.delete() -> Database`

Deletes the current signal.

#### `SignalView.rename(new_name: str) -> Database`

Renames the current signal and updates its name in every signal group attached to
the message. Raises `ValueError` if `new_name` belongs to another signal.

#### `SignalView.add_choice(value: int, label: str) -> Database`

Adds or replaces one value-table entry on the current signal.

#### `SignalView.remove_choice(value: int) -> Database`

Removes one value-table entry from the current signal.

Raises:

- `KeyError` if the signal has no value table or the value is not present

#### `SignalView.set_attribute(name: str, value: Any) -> Database`

Sets a signal-level attribute value.

#### `SignalView.unset_attribute(name: str) -> Database`

Removes a signal-level attribute value.

### `NodeView`

Returned by `Database.node()`.

Common properties:

- `name: str`
- `comment: str | None`
- `attributes: dict[str, Any]`

Existing-entity edits:

#### `NodeView.delete() -> Database`

Deletes the current node.

#### `NodeView.rename(new_name: str) -> Database`

Renames the current node and rewrites references to it in:

- `Message.senders`
- `Signal.receivers`

Important:

- current implementation does not reject collisions with an existing `new_name`

#### `NodeView.set_attribute(name: str, value: Any) -> Database`

Sets a node-level attribute value.

#### `NodeView.unset_attribute(name: str) -> Database`

Removes a node-level attribute value.

## Parse and I/O

### `parse(text: str, *, on_unsupported: Literal["raise", "skip"] = "raise") -> Database`

Top-level convenience wrapper for `normalize()` followed by `parse_string()`.

Behavior:

- strips BOM
- normalizes line endings to `\n`
- replaces tabs with spaces
- ensures trailing newline
- parses the normalized text into a `Database`
- preserves strict 1.0 behavior when `on_unsupported="raise"`
- with `on_unsupported="skip"`, isolates only safely bounded unsupported
  constructs and records ordered `ParseDiagnostic` entries

Raises:

- parser exceptions from Lark on invalid DBC syntax
- `ValueError` for an invalid `on_unsupported` policy
- parser exceptions for unknown or unsafe-to-isolate syntax even in skip mode

### `parse_string(text: str, *, on_unsupported: Literal["raise", "skip"] = "raise") -> Database`

Public from `dbckit.parser`.

Parses a DBC string exactly as provided. Use this if you want parser access without
the normalization pass. It accepts the same unsupported-construct policy as `parse()`.

Raises:

- parser exceptions from Lark on invalid DBC syntax

### `normalize(text: str) -> str`

Public from `dbckit.parser`.

Normalizes raw DBC text before parsing:

- strips UTF-8 BOM
- converts `CRLF` and `CR` to `LF`
- replaces tabs with spaces
- appends a trailing newline when missing

### `load(path: str | Path, *, encoding: str | None = None, on_unsupported: Literal["raise", "skip"] = "raise") -> Database`

Reads a DBC file and returns a parsed `Database`.

Behavior:

- when `encoding` is omitted, decodes strictly as UTF-8 and falls back to cp1252
- when `encoding` is provided, uses it strictly without fallback or replacement
- parses normalized content
- forwards `on_unsupported` to the parser
- returns a copy with `db.filename` set to the string form of `path`

Raises:

- filesystem exceptions from `Path.read_bytes()`
- `UnicodeDecodeError` when an explicit encoding cannot decode the file, or when
  neither default encoding can decode it
- parser exceptions for invalid DBC content

### `dump(db: Database) -> str`

Serializes a `Database` back to DBC text.

Current behavior:

- writes `VERSION`, `NS_`, `BS_`, `BU_`, `BO_`, `SG_`, comments, attribute definitions, attribute values, `VAL_`, and `SIG_GROUP_`
- emits `Vector__XXX` as the fallback sender/receiver when none are present
- preserves round-trip structure covered by the current test suite for included features
- preserves an absent, empty, or nonempty database-level comment distinctly
- emits environment-variable choices as `VAL_ <environment-variable> ...;`
- validates `GenMsgCycleTime` against an existing definition; when a stored cycle
  time has no definition, non-mutatively synthesizes the standard `INT 0
  2147483647` definition and default `0`

### `save(db: Database, path: str | Path, *, encoding: str = "utf-8") -> None`

Serializes with `dump()` and writes text to `path` using UTF-8 by default.
Pass `encoding="cp1252"` when output must remain compatible with Vector-style
Windows tooling.

Raises:

- filesystem exceptions from `Path.write_text()`

## Validation

### `validate(db: Database, strict: bool = False) -> list[Issue]`

Returns every validation finding.

Current checks:

- duplicate message IDs
- duplicate signal names within a message
- signal length overflow past message size
- signal overlap for non-multiplexed signals
- multiple multiplexer signals in one message
- multiplexed variants without exactly one `M` selector
- multiplexed selector values that do not fit the `M` signal's raw bit range
- overlap between common and multiplexed signals or signals in the same `mX` variant
- missing senders
- missing receivers
- undefined attributes
- numeric attribute range violations
- enum attribute value violations
- signal groups that reference missing messages
- signal-group members that do not belong to the referenced message

Behavior:

- `strict=False`: warnings stay warnings
- `strict=True`: every warning is rewritten as an error in the returned list

Known issue codes:

- `DUPLICATE_ID`
- `INVALID_ID`
- `DUPLICATE_SIGNAL`
- `SIGNAL_EXCEEDS_LENGTH`
- `SIGNAL_OVERLAP`
- `MUX_INVALID`
- `MUX_MISSING_SELECTOR`
- `MUX_SELECTOR_OUT_OF_RANGE`
- `MUX_OVERLAP`
- `MISSING_SENDER`
- `MISSING_RECEIVER`
- `ATTR_UNDEFINED`
- `ATTR_OUT_OF_RANGE`
- `SIGNAL_GROUP_MISSING_MESSAGE`
- `SIGNAL_GROUP_MISSING_SIGNAL`

## Codec

### `decode_signal(data: bytes, signal: Signal) -> float`

Decodes one signal from raw frame bytes.

Behavior:

- supports Intel and Motorola bit layouts
- sign-extends signed signals
- treats `SIG_VALTYPE_` 0 as an integer and decodes values 1 and 2 as 32-bit float and 64-bit double
  IEEE-754 values; mismatched lengths or unknown types raise `ValueError`
- returns physical value as `numeric * factor + offset`
- treats any signal bits beyond the end of `data` as `0`; a short or empty payload does not raise an exception

### `encode_signal(data: bytearray, signal: Signal, physical: float, *, strict: bool = False) -> None`

Encodes one physical value into `data` in place.

Behavior:

- converts integer signals with `round((physical - offset) / factor)`
- treats `SIG_VALTYPE_` 0 as an integer and encodes values 1 and 2 as 32-bit float and 64-bit double
  IEEE-754 values after reversing scale and offset
- with `strict=False`, clamps out-of-range raw values to the representable range: unsigned *n*-bit signals use `[0, 2**n - 1]`; signed *n*-bit signals use `[-2**(n-1), 2**(n-1) - 1]`
- with `strict=True`, raises `ValueError` instead of clamping; the message has the form `Signal '<name>': physical <physical> → raw <raw> is outside [<min>, <max>] for a <signed|unsigned> <n>-bit signal`
- stores negative signed values using their *n*-bit two's-complement representation
- mutates the provided `bytearray`
- silently skips signal bits that fall beyond the end of `data`; the buffer is not extended

The `strict` overflow option applies to integer signals. IEEE-754 values are
not clamped; values that cannot be represented by the selected float format
raise `ValueError`.

The function returns `None`.

### `decode_frame(db: Database, arbitration_id: int, data: bytes) -> dict[str, float | int | str]`

Decodes every signal in the message identified by `arbitration_id`.

Behavior:

- looks up the message in `db.messages`
- for multiplexed messages, decodes the `M` selector first and includes only non-multiplexed signals, the selector itself, and `mX` signals whose `X` matches the active selector; inactive variants are omitted
- resolves value-table matches to their string labels
- treats missing bytes in a short payload as `0x00` without raising
- ignores bytes beyond the message DLC in a long payload
- returns `dict[signal_name, decoded_value]`

Raises:

- `KeyError` if the message ID is not present

### `encode_frame(db: Database, arbitration_id: int, values: dict[str, float], *, strict: bool = False) -> bytes`

Encodes selected signal values into a new payload buffer sized to the message DLC.

Behavior:

- allocates `bytearray(message.length)`
- encodes only the signals present in `values`
- leaves unspecified bits as zero
- ignores `GenSigStartValue`; start-value encoding is not currently supported
- forwards `strict` to `encode_signal`; the default clamps overflow, while `strict=True` raises `ValueError`
- for multiplexed messages, uses an explicitly supplied `M` selector or infers it from a supplied `mX` signal and writes the inferred selector automatically
- returns immutable `bytes`

Raises:

- `KeyError` if the message ID is not present
- `KeyError` if any provided signal name is not present in the message
- `ValueError` if `strict=True` and a signal's raw value is outside its representable range
- `ValueError` if a provided `mX` signal does not match the active `M` selector
- `ValueError` if provided `mX` signals imply contradictory selectors

## Operations

### `SignalDiff`

Fields:

- `signal_name: str`
- `change: Literal["added", "removed", "modified"]`
- `before: Signal | None = None`
- `after: Signal | None = None`

### `MessageDiff`

Fields:

- `arbitration_id: int`
- `message_name: str`
- `signal_diffs: list[SignalDiff] = []`
- `field_changes: dict[str, tuple] = {}`

### `DiffResult`

Fields:

- `added_messages: list[Message] = []`
- `removed_messages: list[Message] = []`
- `modified_messages: list[MessageDiff] = []`
- `added_nodes: list[Node] = []`
- `removed_nodes: list[Node] = []`
- `added_attributes: list[AttributeDefinition] = []`
- `removed_attributes: list[AttributeDefinition] = []`
- `added_signal_groups: list[SignalGroup] = []`
- `removed_signal_groups: list[SignalGroup] = []`
- `added_envvars: list[EnvironmentVariable] = []`
- `removed_envvars: list[EnvironmentVariable] = []`

Property:

- `is_empty: bool`

### `diff(db_a: Database, db_b: Database) -> DiffResult`

Computes structural differences from `db_a` to `db_b`.

Current coverage:

- added, removed, and modified messages
- added and removed nodes
- added and removed attribute definitions
- added and removed signal groups, keyed by `(message_id, name)`
- added and removed environment variables, keyed by name
- per-message field changes for `name`, `length`, `senders`, `comment`,
  `cycle_time`, and `attributes`
- per-message added, removed, and modified signals

Not currently covered:

- database-level attribute values
- node comments or node attributes
- modifications to an attribute definition that keeps the same name
- modifications to a signal group that keeps the same `(message_id, name)` key
- modifications to an environment variable that keeps the same name
- `dbc_specific`

### `MergeStrategy`

Literal values:

- `"raise"`
- `"ours"`
- `"theirs"`

### `merge(db_a: Database, db_b: Database, strategy: MergeStrategy = "raise") -> Database`

Builds a union of two databases.

Conflict handling:

- `"raise"`: `ValueError` on the first conflicting key
- `"ours"`: keep the value from `db_a`
- `"theirs"`: replace with the value from `db_b`

Current merge rules:

- merges dictionaries for messages, nodes, attribute definitions, attribute values, value tables, and environment variables
- concatenates signal groups and de-duplicates by `(message_id, name)`
- uses `db_b.version or db_a.version`
- uses `db_b.bit_timing or db_a.bit_timing`
- merges `dbc_specific` shallowly with `db_b` winning on duplicate keys
- preserves namespace order by unique concatenation of `db_a.ns_values` then `db_b.ns_values`

### `extract(db: Database, message_ids: list[int] | None = None, *, message_names: list[str] | None = None, node_names: list[str] | None = None) -> Database`

Builds a new database containing only the selected messages.

Behavior:

- combines ID, message-name, and node-name selectors as a union
- node selection includes messages where the node is a sender or receiver
- raises if any requested message ID, message name, or node name is missing
- includes referenced sender and receiver nodes when present
- includes signal groups referencing extracted messages
- carries over attribute definitions, database-level attribute values, value tables, namespace values, and bit timing
- preserves environment variables and other database-level metadata

Raises:

- `KeyError` when any requested ID, message name, or node name is not present

### `search_messages(db: Database, query: str) -> list`

Case-insensitive substring search over:

- `Message.name`
- `Message.comment`

Returns matching `Message` objects.

### `search_signals(db: Database, query: str) -> list[tuple]`

Case-insensitive substring search over:

- `Signal.name`
- `Signal.comment`

Returns `(Message, Signal)` pairs.

### `find_messages_by_pgn(db: Database, pgn: int) -> list[MessageView]`

Returns all `MessageView` objects whose `PGN` attribute matches `pgn`.

Behavior:

- reads `Message.attributes["PGN"]`
- matches integer values, integral floats, and strings parseable with `int(..., 0)`
- ignores missing, empty, invalid, and non-integral values
- returns `[]` when there are no matches

### `find_signals_by_spn(db: Database, spn: int) -> list[tuple[MessageView, SignalView]]`

Returns all `(MessageView, SignalView)` pairs whose `SPN` attribute matches `spn`.

Behavior:

- reads `Signal.attributes["SPN"]`
- matches integer values, integral floats, and strings parseable with `int(..., 0)`
- ignores missing, empty, invalid, and non-integral values
- returns `[]` when there are no matches

### `pgn_from_arbitration_id(arbitration_id: int) -> int`

Derives the 18-bit J1939 parameter group number from a clean 29-bit CAN
arbitration ID without reading DBC attributes.

Behavior:

- retains the extended data-page, data-page, and PDU-format bits
- clears the PDU-specific byte for PDU1 (`PF < 240`), where it is a destination
  address
- retains the PDU-specific byte for PDU2, where it is the group extension
- omits the priority and source-address bits
- raises `TypeError` for non-integer values and `ValueError` outside
  `0x00000000..0x1FFFFFFF`

### `CodegenTarget`

Literal values:

- `"c"`
- `"python"`
- `"markdown"`
- `"json-schema"`

### `codegen(db: Database, target: CodegenTarget) -> str`

Generates one textual artifact from the database.

Targets:

- `"c"`: C header-style constants and stub decoder functions
- `"python"`: self-contained Python dataclasses with working `decode()` and
  `encode()` methods
- `"markdown"`: human-readable DBC documentation
- `"json-schema"`: JSON Schema describing per-message payload objects

Important:

- `"c"` output is scaffolding only; generated functions contain `TODO` placeholders
- `"python"` output implements Intel/Motorola integer bit extraction and packing,
  signed conversion, factor/offset scaling, and encode-time clamping. It also emits
  value-table constants. It does not currently reproduce `SIG_VALTYPE_` IEEE-754
  semantics or multiplexing behavior; use the runtime codec when those features are
  required.

Raises:

- `ValueError` for unsupported targets

### `FrameLike`

Stable structural contract accepted by `decode_frames()` and returned by reader
packages. A frame object needs only these readable attributes:

- `timestamp: float`
- `arbitration_id: int`
- `data: bytes`

Implementations do not need to inherit from a dbckit class or import dbckit.
Optional `channel` and `is_extended_frame` attributes are preserved when present.

### `RawFrame`

Fields:

- `timestamp: float`
- `arbitration_id: int`
- `data: bytes`
- `channel: int | None = None`
- `is_extended_frame: bool = False`

### `DecodedFrame`

Fields:

- `timestamp: float`
- `arbitration_id: int`
- `message_arbitration_id: int` — resolved DBC message ID; may differ from the
  incoming ID under J1939 PGN matching
- `raw: bytes`
- `signals: dict[str, float | int | str]`
- `channel: int | None = None`
- `is_extended_frame: bool = False`

### `AmbiguousFrameMatch`

Returned instead of decoding when J1939 PGN resolution finds multiple DBC
messages. Candidate order follows database message insertion order.

Fields:

- `timestamp: float`
- `arbitration_id: int`
- `raw: bytes`
- `candidate_message_ids: list[int]`
- `channel: int | None = None`
- `is_extended_frame: bool = False`

The result deliberately contains no decoded signals because selecting a
candidate implicitly would be unsafe.

### `FrameMatchMode`

Literal values: `"exact"`, `"j1939"`, and `"auto"`.

### `AscReader`

Reader for Vector CANalyzer `.asc` logs.

#### `AscReader.read(path: Path) -> Iterator[RawFrame]`

Behavior:

- scans line by line
- matches standard data-frame ASC rows
- ignores non-matching lines
- parses standard and `x`-suffixed extended CAN IDs as hexadecimal
- preserves the numeric channel and extended-frame marker
- returns raw payload bytes from the frame data columns

### `decode_frames(db: Database, frames: Iterable[FrameLike], *, match: FrameMatchMode = "exact") -> Iterator[DecodedFrame | AmbiguousFrameMatch]`

Pure frame-stream decoding with no file I/O.

Behavior:

- accepts any iterable whose items satisfy the three-field `FrameLike` contract
- `"exact"` preserves the original behavior: it looks up the incoming ID
  directly and skips absent IDs
- `"j1939"` derives PGNs from eligible extended input frames and extended DBC
  messages, ignoring priority, source address, and PDU1 destination address
- `"auto"` prefers an exact ID, then enables derived-PGN fallback only when a
  message has a valid `PGN` attribute or a database/message `ProtocolType`
  attribute identifies J1939
- `PGN` and `ProtocolType` are detection signals only; candidate matching always
  uses ID-derived PGNs
- returns `AmbiguousFrameMatch` when multiple messages share the derived PGN
  and skips frames with no candidate
- delegates each known frame to `decode_frame()`, including mux filtering and
  value-table resolution
- preserves the incoming ID in `arbitration_id`, records the resolved DBC ID in
  `message_arbitration_id`, and copies optional metadata with safe defaults

### `register_reader(extension: str, reader: LogReader) -> None`

Stable public extension point for registering a custom log reader under a file
extension. Reader objects satisfy the `LogReader` protocol by implementing
`read(path: Path) -> Iterator[FrameLike]`.

Behavior:

- trims and lowercases the extension and adds a leading `.` when omitted
- raises `ValueError` for an empty extension
- registration is process-global; a later registration replaces the reader for
  the same normalized extension
- explicit registration takes precedence over discovered entry points and built-ins

### `decode_log(db: Database, path: str | Path, *, format: str | None = None, match: FrameMatchMode = "exact") -> Iterator[DecodedFrame | AmbiguousFrameMatch]`

Decodes frames from a log file using the registered reader for the file extension.

Behavior:

- uses `format` when supplied; otherwise uses `Path(path).suffix.lower()`
- normalizes formats case-insensitively with or without a leading dot
- resolves readers in this order: explicit registration, entry point, built-in
- raises `ValueError` for an unknown format and lists available extensions
- delegates the reader's iterable and `match` mode to `decode_frames()`

The CLI exposes both options as `dbckit decode log --format trc --match auto`.

### Writing a reader package

Reader packages advertise zero-argument factories in the `dbckit.readers`
entry-point group. The entry-point name is the extension without a leading dot:

```toml
[project.entry-points."dbckit.readers"]
trc = "logkit.dbckit_reader:create_trc_reader"
```

```python
from dataclasses import dataclass
from pathlib import Path

@dataclass
class LogkitFrame:
    timestamp: float
    arbitration_id: int
    data: bytes

class TrcReader:
    def read(self, path: Path):
        yield LogkitFrame(0.0, 0x123, b"\x01\x02")

def create_trc_reader():
    return TrcReader()
```

Discovery occurs once on the first `decode_log()` call. Only the selected
factory is loaded, and its reader instance is cached. Duplicate factories for
one extension or a broken selected factory raise clear errors; failures in
unselected plugins do not affect decoding. A later `register_reader()` call
always overrides a discovered plugin.

## Practical notes

- The package root `dbckit` is the stable import surface to target in application code.
- `codegen()` is useful for documentation and scaffolding, not as a full production codec generator in its current form.
- `validate()` is the main guardrail before writing or shipping generated DBC content.
- Mutation helpers are appropriate for deterministic edit pipelines because they are pure at the `Database` level.
