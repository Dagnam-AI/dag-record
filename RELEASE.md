# Release Process

This document is for maintainers publishing `dagnam-record` to PyPI.

Releases are **automated**: pushing a tag of the form `v<version>` (for example `v0.1.0`)
triggers [`.github/workflows/release.yml`](.github/workflows/release.yml), which

1. checks that the tagged commit is on `main` (or a `release/*` backport branch), and that the
   tag, `__version__` and the changelog name one version,
2. runs the whole of CI on the tagged commit (`ci.yml`),
3. builds the wheel and sdist (a job with `contents: read` only, since it resolves fresh build
   tools), installs each into a clean Python 3.9 environment and runs `scripts/smoke_record.py`,
4. attests build provenance in a separate job that only holds the OIDC token (`id-token` and
   `attestations`) and runs nothing but pinned actions,
5. publishes to **TestPyPI**, installs from it and runs the smoke test again,
6. and only then publishes to **PyPI**.

Publishing uses PyPI **trusted publishing** (OIDC) through the `testpypi` and `pypi` GitHub
environments; there are no API tokens to manage. The package depends on nothing, so unlike the
`dagnam` SDK there is no platform check.

## One-time setup (before the first tag)

The workflow cannot protect itself: the tag's own `release.yml` is the one that runs, and PyPI
matches only the workflow file name. So these settings, not the workflow, are the guard. Do all of
them before pushing `v0.1.0`.

**1. Trusted publishers.** On both [pypi.org](https://pypi.org/manage/account/publishing/) and
[test.pypi.org](https://test.pypi.org/manage/account/publishing/) add a **pending trusted
publisher** for the project `dagnam-record`. The environment is mandatory, never left blank:

| field | value |
| --- | --- |
| PyPI project name | `dagnam-record` |
| owner | `Dagnam-AI` |
| repository | `dag-record` |
| workflow | `release.yml` |
| environment | `pypi` on PyPI, `testpypi` on TestPyPI |

**2. Environments.** Create `testpypi` and `pypi` in the repository settings (a workflow's first
reference would otherwise create them with no protection). Restrict both to **deployment tags**
`v*`, and give `pypi` a **required reviewer** who is not the person pushing the tag.

**3. Rulesets.**
- `main` and `release/**`: pull request required, the `dagnam-record CI` checks required, code-owner
  review required (`.github/CODEOWNERS` only requests a review without it), no force-push, no
  deletion.
- Tags `v*`: restrict who can create, move and delete them.
- Actions: require SHA pinning.

## Version bump (single source of truth)

The version lives in exactly one place: `__version__` in `dagnam_record/__init__.py`; hatchling
derives the built version from it.

1. Bump `__version__`.
2. Fold the `CHANGELOG.md` `[Unreleased]` entries into a dated `## [X.Y.Z] - YYYY-MM-DD`
   heading and leave a fresh empty `[Unreleased]`. A dated heading is written at release time,
   never ahead of it.
3. Check the release is ready (this refuses entries left under `[Unreleased]` or a newest
   heading that is not the version being published):

   ```bash
   python scripts/check_changelog.py
   ```

4. Run the gates and build locally:

   ```bash
   uv sync --all-extras
   uv run poe check
   uv build
   ```

## Publish

Merge the release PR to `main`, then tag that commit and push the tag:

```bash
git tag v0.1.0
git push origin v0.1.0
```

PyPI takes no version back: if a run fails after the upload step, fix forward with a new patch
version rather than re-pushing the tag. A fix for a published minor lands on `main` first and is
cherry-picked onto a `release/X.Y` branch only when trunk has moved past that minor.
