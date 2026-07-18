# Roadmap

The pre-1.0 planning checklists are complete and retired; what remains is the
publish work below, the planned 1.0.1 and 1.1.0 releases, and the deferred
feature list.

## Publish 1.0.0 to PyPI

- [x] **1. Add `.github/workflows/release.yml`**: trigger on `v*` tags; build sdist + wheel;
  publish with `pypa/gh-action-pypi-publish` using OIDC (`permissions: id-token: write`,
  environment `pypi`) — no API tokens
- [x] **2. Register the trusted publisher on pypi.org** *(manual)*: add a *pending publisher*
  under your PyPI account for `canforge/dbckit`, workflow `release.yml`, environment `pypi`
- [ ] **3. Optional TestPyPI dry run**: point the workflow (or a copy) at TestPyPI, publish,
  `pip install -i https://test.pypi.org/simple/ dbckit`
- [x] **4. Update [docs/releasing.md](docs/releasing.md)**: replace the manual twine steps with
  the tag-driven workflow
- [x] **5. Merge to `main` and push**
- [x] **6. Tag and release**: `git tag -a v1.0.0 -m "Release 1.0.0" && git push origin v1.0.0` —
  the workflow builds and publishes
- [x] **7. Verify the release**
  - [x] In a clean venv: `pip install dbckit` then
    `python -c "import dbckit; print(dbckit.parse('VERSION \"1\"').version)"`
  - [x] `pip install "dbckit[cli]"` and run `dbckit --help`
  - [x] PyPI page shows license, links, and README correctly

## 1.0.1 — extended-ID reference fixes (patch)

Bug fixes only, no API change. Ship first and alone: extended flagged IDs plus
`CM_`/`BA_`/`VAL_` sections are the norm in real-world J1939 DBCs, and today such files
cannot load at all — which pushes clients into stripping sections to work around it.

- [x] Normalize the extended-frame flag through one shared helper at every message
  reference, not only `BO_`: `CM_`/`BA_`/`VAL_`/`SIG_VALTYPE_` look up messages by the
  raw flagged ID and fail, `BO_TX_BU_` silently drops senders, `SIG_GROUP_` stores the
  unmasked ID, and the `CM_ BO_` handler writes back under the raw key (would duplicate
  messages once lookups alone were fixed)
- [x] Serialize the flagged ID consistently in every section, not only `BO_`, so emitted
  files round-trip and match what other tools expect
- [x] Accept the bare `SG_MUL_VAL_` token inside `NS_:`; reject only an actual statement
  (has arguments). Real extended multiplexing is already rejected at the signal level,
  so the line-based pre-scan may shrink to nothing
- [x] Regression fixture: a CSS-Electronics-shaped DBC (extended flagged IDs,
  `CM_`/`BA_`/`VAL_`/`SIG_VALTYPE_` referencing them, `SG_MUL_VAL_` in `NS_`) exercised
  in the round-trip suite — the single test that would have caught all of the above
- [x] Keep signal groups consistent through signal and message mutations:
  `delete_signal` prunes the deleted name, `rename_signal` rewrites the old name,
  `delete_message` prunes the message's groups, and `update_signal` rejects name changes
  in favor of `rename_signal`. Validate that each group's `message_id` exists and its
  `signal_names` belong to that message so dangling references cannot round-trip into
  emitted DBC text undetected.

## 1.1.0 — lenient parsing and J1939 matching (minor)

Depends on 1.0.1: the `PGN`/`ProtocolType` attributes that drive J1939 auto-detection
live in exactly the `BA_` lines that currently fail to parse on extended-ID files.

- [x] Lenient parsing with diagnostics: `parse(text, on_unsupported="raise" | "skip")`,
  default `"raise"` so 1.0 behavior is unchanged. Each skipped construct or dangling
  reference records a structured diagnostic (construct, line, affected message/signal,
  `effect: decode_degraded | cosmetic`); decode-safety is tracked per message with a
  derived global rollup, and lenient mode never silently alters decode semantics.
  Subsumes the previously deferred `errors="collect"` lenient load mode item.
- [ ] J1939 PGN-aware message resolution: `decode_frames(..., match="exact" | "j1939" |
  "auto")`. PGN is derived from the 29-bit arbitration ID (PDU1/PDU2 handling, source
  address ignored); the `BA_` `PGN`/`ProtocolType` attributes serve only as the
  auto-detection signal; ambiguous PGN matches are returned explicitly. Pure ID math
  stays in dependency-free functions in `operations/j1939.py` — the extraction seam if
  transport protocol or DM diagnostics ever justify a separate j1939kit.
- [x] Timeboxed: try `parser="lalr"` in place of Earley. A cold parse of a 1,900-message
  / 13,000-signal DBC measures ~10 s and scales linearly; LALR is behavior-neutral if
  the grammar is compatible, and the 1.0.1 round-trip suite verifies it. Defer without
  guilt if the grammar resists.

## Deferred additions

Nonblocking; decide per item whether it lands in a 1.x release:

- [ ] Built-in candump reader (other formats can already integrate through `dbckit.readers`)
- [ ] Free-slot layout helper and opt-in overlap checking during `add_signal`
- [ ] Sorted serialization via a `sort=` option
- [ ] Global `VAL_TABLE_` mutation APIs
- [ ] Opt-in `GenSigStartValue` encoding defaults
- [ ] `codegen` C target remains experimental (decode stubs only) — keep it labelled until
  it is production-grade
- [ ] Replace the deprecated `typer[rich]` extra with `typer` + explicit `rich` in the `cli`
  and `dev` dependency groups — modern typer bundles rich, and the extra now emits an
  install warning
- [ ] Guard the agent skill's bundled docs against drift: `skills/dbckit/references/` holds
  verbatim copies of `docs/{api-reference,cli,dbc-support}.md` so agents get local,
  version-coherent reads. Add a `scripts/sync_skill_refs.sh` (plain `cp`) plus a CI step
  that `diff -r`s the two locations, so a PR touching docs without re-syncing fails; add
  a "Canonical source + version" header line to each bundled copy
