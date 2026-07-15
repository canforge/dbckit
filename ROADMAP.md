# Roadmap

The pre-1.0 planning checklists are complete and retired; what remains is the
publish work below and the deferred feature list.

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

## Deferred additions

Nonblocking; decide per item whether it lands in a 1.x release:

- [ ] Lenient load mode (`errors="collect"`): recover from dangling references and record
  them as parse issues instead of failing — the main friction point on real-world OEM files
- [ ] Built-in candump reader (other formats can already integrate through `dbckit.readers`)
- [ ] Free-slot layout helper and opt-in overlap checking during `add_signal`
- [ ] Sorted serialization via a `sort=` option
- [ ] Global `VAL_TABLE_` mutation APIs
- [ ] Opt-in `GenSigStartValue` encoding defaults
- [ ] `codegen` C target remains experimental (decode stubs only) — keep it labelled until
  it is production-grade
