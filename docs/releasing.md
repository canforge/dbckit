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

Publishing is tag-driven: pushing a `v*` tag triggers
`.github/workflows/release.yml`, which builds the sdist and wheel and uploads
them to PyPI via [trusted publishing](https://docs.pypi.org/trusted-publishers/)
(OIDC, GitHub environment `pypi`) — no API tokens are involved.

```bash
# 1. Bump version
#    Edit pyproject.toml: version = "1.0.0"

# 2. Update CHANGELOG (see format below)

# 3. Commit the release
git add pyproject.toml CHANGELOG.md
git commit -m "chore: release 1.0.0"
git push origin main

# 4. Tag — this triggers the release workflow
git tag -a v1.0.0 -m "Release 1.0.0"
git push origin v1.0.0

# 5. Verify
gh run watch                        # release workflow builds and publishes
open https://pypi.org/project/dbckit/
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
