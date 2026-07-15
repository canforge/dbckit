# Release process

## Versioning

dbckit follows [Semantic Versioning](https://semver.org/) from `1.0.0` onward.

- **Patch** (`1.0.x`) — bug fixes, no API changes.
- **Minor** (`1.x.0`) — new backwards-compatible features.
- **Major** (`x.0.0`) — breaking API changes. Requires a migration note in CHANGELOG.

## Pre-release checklist

Before tagging a release:

- [ ] All CI checks pass on `main` (tests, ruff, mypy, coverage ≥ 90%).
- [ ] `CHANGELOG.md` entry written for this version (see below).
- [ ] Version bumped in `pyproject.toml`.
- [ ] README examples still accurate for the new version.

## Steps

```bash
# 1. Bump version
#    Edit pyproject.toml: version = "1.0.0"

# 2. Update CHANGELOG (see format below)

# 3. Commit the release
git add pyproject.toml CHANGELOG.md
git commit -m "chore: release 1.0.0"

# 4. Tag
git tag -a v1.0.0 -m "Release 1.0.0"
git push origin main --tags

# 5. Build
pip install build
python -m build
# Produces dist/dbckit-1.0.0.tar.gz and dist/dbckit-1.0.0-py3-none-any.whl

# 6. Publish to PyPI
pip install twine
twine upload dist/dbckit-1.0.0*
```

## CHANGELOG format

```markdown
## [1.0.0] — 2026-07-15

### Added
- ...

### Fixed
- ...

### Changed
- ...

### Removed
- ...
```

Keep one `## [Unreleased]` section at the top for in-progress work.
