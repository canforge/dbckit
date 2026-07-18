# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

dbckit is a Python library + Typer CLI for parsing, editing, validating, diffing, and
encoding/decoding DBC (CAN database) files. Published to PyPI as `dbckit` from this repo
(github.com/canforge/dbckit). It is a deliberate alternative to cantools: typed models,
copy-on-write edits, structured validation — not a decode-everything library.

## Commands

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"                          # includes CLI deps

pytest                                           # full suite
pytest tests/test_mutations.py                   # one file
pytest tests/test_parser.py -k extended_mux      # one test
pytest --cov=dbckit --cov-fail-under=90 -q       # the CI coverage gate
ruff check dbckit/                               # lint (CI-blocking)
mypy dbckit/                                     # types (CI-blocking)
python -m build                                  # sdist+wheel check (CI-blocking)
```

Coverage note: `dbckit/cli.py` is omitted from the coverage gate on purpose; the CLI is
covered separately by `tests/test_cli.py` (exit codes + json/csv output).

## Architecture

One-way pipeline, pure functions at every stage:

```
DBC text ──normalize()──> parser/dbc.lark + parser/grammar.py (Lark → DBCTransformer)
        ──> model/  (Pydantic v2: Database, Message, Signal, Node, ...)
        ──> serializer.py (deterministic output, fixed section order)
```

- **`model/`** — data only. `Database.method()` conveniences delegate to `mutations/` and
  `operations/` via deferred imports (avoids cycles; keep that pattern).
- **`mutations/`** — pure copy-on-write edit functions: take a `Database`, return a NEW
  `Database`, never touch the input. This invariant is the product; breaking it is never
  a fix. `_cycle_time.py` keeps `Message.cycle_time` and the `GenMsgCycleTime` attribute
  synchronized — any mutation touching either must go through it.
- **`views.py`** — `MessageView`/`SignalView`/`NodeView`: thin database-bound wrappers over
  mutations. Views are the public way to modify/delete existing entities; `Database` is
  for navigation, top-level creation, and persistence.
- **`codec/`** — signal/frame encode+decode. Integer and IEEE-754 float/double
  (`SIG_VALTYPE_`), Intel + Motorola. Clamps on overflow unless `strict=True`. Zero-fills
  unspecified signals; short payloads read missing bytes as zero.
- **`validator.py`** — returns `Issue(severity, code, location, message)` records; codes
  are a public contract documented in docs/api-reference.md — add, don't rename.
- **`operations/`** — diff/merge/extract/codegen/J1939 lookup, plus `log.py`: the
  `FrameLike` protocol, `decode_frames()` (pure), `decode_log()` (file), and reader
  registry (`register_reader()` + `dbckit.readers` entry-point group — a stable public
  extension point).
- **`cli.py`** — thin Typer shell over the public API. CLI edit commands save back to the
  `--db` file in place (unlike the library). Output formats: table/json/csv.

## Scope walls (policy, not gaps)

These fail loudly by design — "fixing" them is a roadmap decision, not a bug fix:

- Extended multiplexing (`m0M`, `SG_MUL_VAL_`) is rejected by default; opt-in
  `on_unsupported="skip"` isolates line-bounded forms with decode diagnostics.
- Dangling `CM_`/`BA_`/`VAL_`/`SIG_VALTYPE_`/`ENVVAR_DATA_` references raise by
  default and become structured diagnostics in skip mode. Skipped forward
  `VAL_`/`SIG_VALTYPE_` entries are decode-degraded when their final target
  survives; references whose targets remain absent are cosmetic.
- J1939 lookup helpers read explicit `PGN`/`SPN` attributes; frame-stream decoding
  supports derived-PGN `exact`/`j1939`/attribute-gated `auto` matching.
- CAN FD untested; `.sym`/`.kcd`/ARXML out of scope.

ROADMAP.md is the authority on which of these change in 1.0.1/1.1.0 and how.

## Testing conventions

- `tests/fixtures/golden/` holds pinned, licensed real-world fixtures (commaai/opendbc
  DBCs, a python-can ASC trace). Never regenerate or "fix" them; round-trip tests compare
  semantics against them.
- Parser error tests match on message text, not exception type — Lark wraps errors in
  `VisitError`.
- New DBC constructs need round-trip coverage: parse → serialize → reparse → compare.

## Docs that must move together

A change to the public surface touches all of: `docs/api-reference.md`, `docs/cli.md`,
`docs/dbc-support.md`, `docs/recipes.md`, `CHANGELOG.md` (Keep a Changelog, semver), and
the verbatim copies in `skills/dbckit/references/` (agent skill; sync = `cp` from docs/,
drift guard planned).
README stays a teaser — full API/CLI detail lives in docs/, not README.

## Releasing

Tag-driven: bump `pyproject.toml`, update CHANGELOG, push to `main`, then
`git tag -a vX.Y.Z && git push origin vX.Y.Z` — `.github/workflows/release.yml` builds and
publishes to PyPI via trusted publishing (OIDC, environment `pypi`, no tokens). Full steps:
docs/releasing.md.

## Repo quirks

- `docs/archive/` is gitignored on purpose (local-only historical planning docs).
- History starts at the 1.0.0 root commit by design; don't dig for older context.
- `skills/dbckit/` is a user-facing agent skill for *consumers* of the library; this file
  is the guidance for *developing* it. Keep the two audiences straight.
