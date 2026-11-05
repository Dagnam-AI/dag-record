# Contributing to dagnam-record

Thanks for helping improve the Dagnam.AI local recorder.

Please keep changes focused, include tests for behavior changes, and avoid unrelated
formatting churn. The package promises to have no dependencies and no network code
(`tests/test_package_promises.py` reads its source to check that), so a change that needs
either is a design discussion first.

## Development setup

```bash
uv sync --all-extras
```

Run every quality gate the way CI does, with a single command:

```bash
uv run poe check        # ruff + format-check + pyright (Python 3.9 rules) + pytest at 100% coverage
```

Or the individual gates:

```bash
uv run poe lint          # ruff check
uv run poe format-check  # ruff format --check
uv run poe typecheck     # pyright (strict, against Python 3.9)
uv run poe test          # parallel pytest + terminal coverage (fails under 100%)
uv run poe test-cov      # the same, with HTML, JSON and XML reports
uv run poe test-record   # the tests alone, in the active environment, no coverage
uv run poe build         # source distribution and wheel
```

Coverage is gated at 100% of statements and branches. A coverage gap is a missing test, not a
reason for a suppression.

## Fixtures

`tests/fixtures/*.jsonl` are lines the recorder wrote while the real `openai` and `anthropic`
clients called a local mock server. They are generated (`tests/gen_fixtures.py`, see its
docstring) and a test fails when one is stale. Their bytes depend on the locked `openai` and
`anthropic`: regenerate them, and update `SDK_VERSIONS` in the generator, when either is bumped
in `uv.lock`. The `dagnam` SDK reads these files in its own tests, so tell its maintainers when
their shape changes.

## Supported Pythons and SDKs

The package supports Python 3.9 and newer, `openai>=1.66,<4` and `anthropic>=0.40,<3`.
CI runs the tests on Python 3.9, 3.11 and 3.13 against the lowest and the highest SDK of each
range. Write code that imports on 3.9 (`typing.Optional`, not `X | None`, outside annotations
with `from __future__ import annotations`).

## Pull requests

Open a PR from a topic branch named
`<type>/<slug>` (`feat`, `fix`, `chore`, `docs`, `test`, ...), update `CHANGELOG.md`
`[Unreleased]` for user-facing changes, and make sure `uv run poe check` passes.
