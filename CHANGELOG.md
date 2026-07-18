# Changelog

All notable changes to dbckit are documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning follows [Semantic Versioning](https://semver.org/) from 1.0.0 onward.

---

## [Unreleased]

### Fixed

- Mark skipped forward `VAL_` and `SIG_VALTYPE_` references as
  `decode_degraded` when their message and signal exist in the final model, so
  global and per-message decode-safety rollups cannot report a false safe state.

## [1.1.0] — 2026-07-18

### Added

- Add a task-oriented recipe cookbook covering validation, diffs, extraction,
  normalization, bulk edits, streaming log export, lenient parsing, J1939 frame
  resolution, and standalone Python decoder generation.
- Add PGN-aware J1939 frame resolution with `match="j1939"` and attribute-gated
  `match="auto"` modes on `decode_frames()` and `decode_log()`, plus the matching
  CLI option. PGNs are derived from 29-bit IDs with PDU1/PDU2 handling;
  ambiguous candidates are returned explicitly as `AmbiguousFrameMatch`.
- Add the dependency-free `pgn_from_arbitration_id()` helper and expose the
  resolved DBC ID as `DecodedFrame.message_arbitration_id`.
- Add opt-in lenient parsing with `on_unsupported="skip"` on `parse()`,
  `parse_string()`, and `load()`. Safely bounded extended-multiplexing syntax and
  dangling references produce ordered, structured parse diagnostics with
  per-message and global decode-safety rollups; strict behavior remains the
  default.

### Changed

- Replace the Earley DBC parser with LALR and a contextual lexer, preserving
  namespace capability parsing while substantially reducing parse time for
  large databases.

### Fixed

- Preserve inline `NS_` capability lists and accept the legacy split
  `VAL_TABLE_` form immediately after namespace entries.

## [1.0.1] — 2026-07-18

### Fixed

- Normalize DBC bit-31 extended-frame IDs across every parser-side message
  reference, so comments, attributes, value mappings, signal types,
  transmitters, and signal groups resolve or store the clean arbitration ID
  without creating duplicate message keys.
- Reapply the extended-frame flag across every serializer-side message
  reference, so emitted comments, attributes, value mappings, signal types,
  transmitters, and signal groups use the same DBC wire ID as `BO_`.
- Accept the bare `SG_MUL_VAL_` capability token inside `NS_` and preserve it
  across round trips, while continuing to reject extended-multiplexing range
  statements with a targeted parser error.
- Keep signal-group membership synchronized when signals are deleted or renamed,
  prune groups when their message is deleted, reject signal-name changes through
  generic updates, and report dangling group references during validation.

## [1.0.0] — 2026-07-15

Initial public release.

### Added

**Models and API**

- Typed Pydantic v2 data models: `Database`, `Message`, `Signal`, `SignalGroup`,
  `Node`, environment variables, value tables, and attribute definitions, with
  `py.typed` shipped in the package.
- Database-bound `MessageView` / `SignalView` / `NodeView` returned by navigation
  methods — the supported surface for modifying or deleting existing entities.
- Copy-on-write editing: every mutation returns a new `Database` and never
  mutates its input.

**Parsing and serialization**

- DBC parser and deterministic serializer covering `VERSION`, `NS_`, `BS_`,
  `BU_`, `VAL_TABLE_`, `BO_`/`SG_`, `SIG_GROUP_`, `CM_` (database, node,
  message, signal, and environment variable), `BA_DEF_`/`BA_DEF_DEF_`/`BA_`,
  `VAL_`, `BO_TX_BU_`, `SIG_VALTYPE_`, and `EV_`/`ENVVAR_DATA_`, with semantic
  round trips for all supported sections.
- Extended (29-bit) frame support via the DBC bit-31 convention, round-tripping
  `Message.is_extended_frame`.
- Strict UTF-8 loading with cp1252 fallback, plus explicit `encoding=`
  overrides on `load()` and `save()`.
- Clear, targeted errors for unsupported constructs: extended multiplexing
  (`mXM` indicators and `SG_MUL_VAL_` sections) is rejected during parsing, and
  dangling `CM_`/`BA_`/`VAL_`/`SIG_VALTYPE_`/`ENVVAR_DATA_` references fail
  with section-specific diagnostics instead of being silently discarded.
- `Message.cycle_time` synchronized with the `GenMsgCycleTime` attribute across
  parsing, construction, mutation, and serialization.

**Codec**

- Frame- and signal-level encode/decode (`decode_frame`, `encode_frame`,
  `decode_signal`, `encode_signal`) for integer and IEEE-754 float/double
  (`SIG_VALTYPE_`) signals, in Intel and Motorola byte order.
- Simple multiplexing (`M`/`mX`) on decode and encode, with selector
  auto-inference and inactive-variant filtering.
- Documented overflow and error behavior: out-of-range values clamp by default
  and raise with `strict=True`; unspecified signals are zero-filled; bytes
  missing from short payloads read as zero.

**Validation**

- `validate()` returning structured issues (severity, code, location, message)
  for duplicate and invalid IDs, duplicate signals, signal overlap and
  overflow, multiplexing problems (`MUX_INVALID`, `MUX_MISSING_SELECTOR`,
  `MUX_SELECTOR_OUT_OF_RANGE`, `MUX_OVERLAP`), missing senders/receivers, and
  attribute violations.

**Editing**

- View-level edits: rename, field updates, signal add/delete/rename/update,
  sender add/remove, arbitration-ID changes (with signal-group reference
  rewrites and collision handling), value-table choices, attribute set/unset,
  and delete.
- Database-level creation and definitions: `add_message`, `add_node`,
  `define_attribute`, `delete_attribute`, and signal-group operations
  (add/remove a group, add/remove signals within a group).

**Operations**

- `diff()` with field-level message changes plus signal, signal-group,
  environment-variable, and attribute-value diffs; `merge()` with
  `raise`/`ours`/`theirs` strategies.
- `extract()` by arbitration IDs, message names, and sender/receiver node
  names (selectors combine as a union), preserving environment variables.
- `search_messages()` / `search_signals()`, and attribute-based J1939 lookup
  (`find_messages_by_pgn`, `find_signals_by_spn`, `Database.message_by_pgn`,
  `Database.signal_by_spn`).

**Log and frame decoding**

- `decode_log()` streaming decoded frames from Vector CANalyzer `.asc` files,
  including 29-bit `x`-suffixed identifiers; multiplexed frames omit inactive
  variants.
- The structural `FrameLike` contract and pure `decode_frames()` iterator for
  decoding third-party frame objects without file I/O; `RawFrame` and
  `DecodedFrame` carry optional channel and extended-frame metadata.
- Reader extensibility: `register_reader()` as a stable public extension
  point, lazy discovery through the `dbckit.readers` entry-point group, and
  API/CLI format overrides for oddly named log files.

**Code generation**

- `codegen()` targets: `python` (self-contained dataclasses with working
  `decode()`/`encode()`), `markdown`, `json-schema`, and `c` (experimental).

**CLI**

- `dbckit` command (via the `cli` extra) with `db`, `message`, `signal`,
  `node`, `attribute`, `decode`, `encode`, and `codegen` groups; `table`,
  `json`, and `csv` output; non-zero exit codes on validation errors in every
  output format.

**Docs, fixtures, and CI**

- API reference, DBC support matrix, CLI reference, and release process docs.
- Pinned, licensed golden fixtures from `commaai/opendbc` and `python-can`,
  covering semantic DBC round trips and a real Vector-format ASC trace.
- GitHub Actions CI: tests, ruff, mypy, coverage ≥ 90%, and build check on
  Python 3.11–3.14.
