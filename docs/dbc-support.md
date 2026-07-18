# DBC format support

This document is the authoritative statement of what `dbckit` supports, partially supports,
and does not support in the DBC file format.

---

## Supported sections

These sections round-trip without semantic loss: parse → model → serialize produces
equivalent output.

| Section | What is stored |
|---------|----------------|
| `VERSION` | Version string |
| `NS_` | Namespace keyword list (preserved as-is), including the bare `SG_MUL_VAL_` capability token |
| `BS_` | Bit timing string (preserved as-is) |
| `BU_` | Node names, comments, and attribute values |
| `VAL_TABLE_` | Named global value tables |
| `BO_` | Messages: ID, name, DLC, first sender |
| `SG_` | Signals: bit position, length, byte order, sign, factor, offset, min/max, unit, receivers, comment, multiplex indicator, per-signal value table, attribute values |
| `SIG_GROUP_` | Signal group name, message ID, repetition count, signal list |
| `BO_TX_BU_` | All message transmitters (emitted when a message has more than one sender) |
| `EV_` | Environment variable name, type, range, unit, initial value, ID, access type, access nodes |
| `ENVVAR_DATA_` | Environment variable data size |
| `SIG_VALTYPE_` | Signal value type override (1 = float, 2 = double) stored on the signal and round-tripped |
| `CM_` | Database, message, signal, node, and environment-variable comments, including a distinct empty database comment |
| `BA_DEF_` | Attribute definitions for database, nodes, messages, signals, and environment variables |
| `BA_DEF_DEF_` | Attribute default values |
| `BA_` (database, node, message, signal, env var) | Attribute values for all object types including environment variables |
| `VAL_` | Per-signal and environment-variable value mappings |

---

## Attribute conventions

`Message.cycle_time` and the `GenMsgCycleTime` message attribute are synchronized
through parsing, direct model validation, and pure mutations. Values must be
integral. If a file defines `GenMsgCycleTime`, its declared minimum and maximum
are authoritative and are never widened. Mutations and serialization create the
standard `BO_` `INT 0 2147483647` definition with default `0` only when a stored
cycle time otherwise has no definition.

`VAL_ <name> ...;` targets a previously declared environment variable and is
stored on that variable. Global named value tables use `VAL_TABLE_`; an unknown
or forward-referenced environment-variable target is rejected.

---

## Signal codec coverage

### Supported

- Little-endian (Intel byte order) signals
- Big-endian (Motorola byte order) signals
- Signed and unsigned signals
- Factor and offset conversions
- Value-table label resolution on decode (returns string label when available)

### Partial

- **Multiplexed messages (simple multiplexing):** the `multiplex_indicator` field
  (`M`, `m0`, `m1`, …) is fully supported by `decode_frame()` and `encode_frame()`.
  On decode, the `M` signal is read first and only the matching `mX` signals are returned.
  On encode, the selector is taken from the `M` value in the input dict or inferred from
  whichever `mX` signals are present; the `M` signal is auto-encoded when inferred.
  Providing a contradictory combination raises `ValueError`.
  Extended multiplexing (`m0M` style nested selectors) is not supported.

### Payload length behaviour

- **Short payload** (fewer bytes than DLC): bits beyond the end of the supplied
  data are read as ``0``.  The frame is decoded as if the missing bytes were
  all-zero.  No error is raised.
- **Overlong payload** (more bytes than DLC): the extra bytes are ignored.
  Signal positions are defined relative to the DBC layout and never read
  beyond their declared range.

### Overflow behaviour for encode

For integer signals, `encode_signal` and `encode_frame` convert a physical value to a raw integer
via ``round((physical − offset) / factor)`` and then *clamp* the result to the
signal's bit-width range before writing.  Out-of-range values are silently
truncated by default.

Pass ``strict=True`` to raise ``ValueError`` instead of clamping::

    dbckit.encode_frame(db, 0x100, {"Speed": 99999.0}, strict=True)  # raises
    encode_signal(buf, sig, 99999.0, strict=True)                    # raises

### Float and double signals

`SIG_VALTYPE_` value 0 retains the integer codec; value 1 decodes and encodes a
32-bit IEEE-754 float, and value 2 uses a 64-bit IEEE-754 double. Both Intel
and Motorola layouts are supported, and scale/offset conversion is applied
around the IEEE value. A mismatched signal length or unknown `SIG_VALTYPE_`
value raises `ValueError`.

### Not supported

- Extended multiplexing (``m0M``-style nested selectors) is not supported by
  ``decode_frame`` / ``encode_frame``. Inline nested selectors and
  `SG_MUL_VAL_` range statements are rejected with clear parser errors in the
  default strict mode. With `on_unsupported="skip"`, a line-bounded nested
  signal or range statement is omitted with a `decode_degraded` diagnostic for
  its message and signal. A bare `SG_MUL_VAL_` capability token inside `NS_` is
  accepted and round-tripped.

## CAN and format scope

- Classic CAN is the supported frame scope. CAN FD remains untested, and FD-specific
  attributes such as `VFrameFormat` are not interpreted.
- `.sym`, `.kcd`, and ARXML database formats are out of scope.
- J1939 lookup uses explicit `PGN` and `SPN` attributes only; PGNs are not derived
  from 29-bit arbitration IDs.
- Encoding allocates a zero-filled payload and writes only supplied signals.
  `GenSigStartValue` is ignored.

---

## Extended frames

Extended (29-bit) CAN frame IDs are encoded in DBC files by setting bit 31 of
the message ID integer (i.e. `arbitration_id | 0x80000000`) on `BO_` definitions
and sections that repeat the message ID.

- **Parsed:** the high bit is detected and stripped from `BO_`, `BO_TX_BU_`,
  `SIG_GROUP_`, message/signal `CM_`, message/signal `BA_`, `VAL_`, and
  `SIG_VALTYPE_` IDs. `Message.is_extended_frame` is set from the `BO_`
  definition, and in-memory message and signal-group IDs always use the clean
  29-bit arbitration ID.
- **Serialized:** the high bit is re-applied to `BO_`, `BO_TX_BU_`, `SIG_GROUP_`,
  message/signal `CM_`, message/signal `BA_`, `VAL_`, and `SIG_VALTYPE_`
  message IDs.
- **Round-trip:** fully supported.

Standard frames (`is_extended_frame=False`, default) use 11-bit IDs (0–0x7FF).

## Validation coverage

`dbckit.validate()` checks:

| Code | What it detects |
|------|----------------|
| `DUPLICATE_ID` | Two or more messages share the same arbitration ID |
| `INVALID_ID` | Arbitration ID exceeds the range for the frame type (standard: > 0x7FF, extended: > 0x1FFFFFFF) |
| `DUPLICATE_SIGNAL` | Two or more signals in one message share the same name |
| `SIGNAL_EXCEEDS_LENGTH` | A signal's bit range extends beyond the message DLC |
| `SIGNAL_OVERLAP` | Two non-multiplexed signals occupy the same bit position |
| `MUX_INVALID` | A message contains more than one multiplexer signal (`M`) |
| `MUX_MISSING_SELECTOR` | An `mX` signal has no unique `M` selector signal in its message |
| `MUX_SELECTOR_OUT_OF_RANGE` | An `mX` selector value cannot be represented by the `M` signal's raw bit range |
| `MUX_OVERLAP` | An `mX` signal overlaps a common signal or another signal active for the same selector value |
| `MISSING_SENDER` | A message's sender is not declared in `BU_` |
| `MISSING_RECEIVER` | A signal receiver is not declared in `BU_` |
| `ATTR_UNDEFINED` | An attribute value references an undefined attribute definition |
| `ATTR_OUT_OF_RANGE` | A numeric attribute value falls outside the defined min/max |
| `SIGNAL_GROUP_MISSING_MESSAGE` | A signal group references a message that does not exist |
| `SIGNAL_GROUP_MISSING_SIGNAL` | A signal-group member does not exist in the referenced message |

Sender and receiver references are validated by `MISSING_SENDER` and
`MISSING_RECEIVER`; there is no separate node-validation pass.

---

## Known parser and serializer edge cases

`parse()` and `load()` default to `on_unsupported="raise"`, preserving strict
1.0 behavior. `on_unsupported="skip"` is deliberately narrow: it skips only
safely bounded extended-multiplexing syntax and dangling references understood
by the parser. Every omission produces an ordered `Database.parse_diagnostics`
entry with its construct, one-based line, affected message/signal when known,
effect, and detail. Unknown or unbounded syntax still raises.

Skipped extended-multiplexing semantics are `decode_degraded`. Dangling
references, comments, transmitter metadata, signal groups, and environment-only
metadata are `cosmetic` because they remove no decode semantics from a surviving
message. `Database.decode_safe` and the per-message helpers derive their values
from these effects. Diagnostics are parse metadata: `dump()` does not serialize
them and `diff()` ignores them.

- **Determinism:** serializer output is deterministic; section and entry order is stable
  across repeated calls on the same `Database` object.
- **Unknown sections:** DBC sections not listed above cause a parse error even in
  skip mode; they are never silently skipped. An `SG_MUL_VAL_` range statement
  receives a targeted unsupported-feature error in strict mode; the bare `NS_`
  capability token is supported.
- **Dangling references:** strict mode rejects `CM_`, `BA_`, `VAL_`,
  `SIG_VALTYPE_`, and `ENVVAR_DATA_` entries that refer to an unknown message,
  signal, or environment variable. References are resolved in source order, so the
  referenced object must be declared before the referencing entry. The error
  identifies the section and missing target and is raised as `ValueError`. Skip
  mode declines the update and records a cosmetic diagnostic; it also diagnoses
  missing `BO_TX_BU_` and `SIG_GROUP_` targets without changing their legacy
  strict behavior.
- **Duplicate message IDs in source:** the last `BO_` definition wins (parser overwrites).
- **Extended frames:** `Message.is_extended_frame` records the DBC bit-31 convention;
  parsing strips the marker from message definitions and references, while
  serialization restores it on every section that references the message ID.
