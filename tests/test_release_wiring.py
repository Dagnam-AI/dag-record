"""The release of ``dagnam-record`` and the CI that gates it, pinned as facts about the workflow files.

A tag publishes to PyPI by trusted publishing and PyPI takes no version back, so the shape of
``release.yml`` (what runs before what, who may mint a token, nothing optional) and of the
matrix that gates it is checked here rather than trusted to reading YAML. A source distribution
carries no workflows, so the module is skipped there.
"""

from __future__ import annotations

from pathlib import Path
import re

import pytest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
if not WORKFLOWS.is_dir():
    pytest.skip("a source distribution carries no .github/workflows", allow_module_level=True)
RELEASE = (WORKFLOWS / "release.yml").read_text(encoding="utf-8")
CI = (WORKFLOWS / "ci.yml").read_text(encoding="utf-8")
COMPAT = (ROOT / "dagnam_record" / "_compat.py").read_text(encoding="utf-8")
PUBLISH = {"publish-testpypi", "publish-pypi"}
PIN = re.compile(r"uses: ([\w./-]+)@([0-9a-f]{40})")


def _jobs(workflow: str) -> dict[str, str]:
    """Each job's block of a workflow file, by job id."""
    blocks: dict[str, list[str]] = {}
    current: list[str] | None = None
    for line in workflow.split("\njobs:\n", 1)[1].splitlines():
        job = re.fullmatch(r"  ([\w-]+):", line)
        if job:
            current = blocks.setdefault(job[1], [])
        elif current is not None:
            current.append(line)
    return {name: "\n".join(lines) for name, lines in blocks.items()}


def _needs(job: str) -> set[str]:
    declared = re.search(r"^    needs:\s*(.*)$", job, re.M)
    return set(re.findall(r"[\w-]+", declared[1])) if declared else set()


def _reaches(jobs: dict[str, str], start: str, goal: str) -> bool:
    todo, seen = [start], set[str]()
    while todo:
        name = todo.pop()
        if name == goal:
            return True
        if name not in seen:
            seen.add(name)
            todo += _needs(jobs[name])
    return False


def _problems(workflow: str) -> list[str]:
    """What lets a release publish around a gate, or lets a gate be skipped."""
    jobs = _jobs(workflow)
    found = [f"no job {name}" for name in ("check", "ci", "build") if name not in jobs]
    if found:
        return found
    found += [
        f"{name} can start before {gate}"
        for name in PUBLISH
        for gate in ("build", "check", "ci")
        if not _reaches(jobs, name, gate)
    ]
    found += [
        f"build does not wait for {gate}"
        for gate in ("check", "ci")
        if gate not in _needs(jobs["build"])
    ]
    if "smoke-testpypi" not in _needs(jobs["publish-pypi"]):
        found.append("pypi does not wait for the TestPyPI smoke test")
    found += [
        f"{name} can be skipped or fail without failing the release"
        for name, job in jobs.items()
        if re.search(r"^\s+(if|continue-on-error):", job, re.M)
    ]
    return found


def test_the_workflow_is_triggered_by_a_version_tag_and_nothing_else() -> None:
    triggers = RELEASE.split("\nconcurrency:", 1)[0]
    assert re.search(r'^on:\n  push:\n    tags:\n      - "v\*"\n', triggers, re.M)
    assert "branches" not in triggers
    assert "pull_request" not in triggers
    assert "workflow_dispatch" not in triggers


def test_a_second_tag_never_cancels_a_release_that_is_uploading() -> None:
    assert "group: release-${{ github.ref }}\n  cancel-in-progress: false" in RELEASE


def test_the_release_cannot_publish_around_a_gate() -> None:
    assert _problems(RELEASE) == []
    assert set(_jobs(RELEASE)) >= PUBLISH | {"build", "check", "ci"}


@pytest.mark.parametrize(
    ("old", "new", "problem"),
    [
        ("    needs: [check, ci]\n", "    needs: [check]\n", "build does not wait"),
        ("    needs: [check, ci]\n", "    needs: [ci]\n", "build does not wait"),
        (
            "    name: Publish to TestPyPI\n    needs: build\n",
            "    name: Publish to TestPyPI\n    needs: []\n",
            "publish-testpypi can start before",
        ),
        (
            "    name: Publish to PyPI\n    needs: smoke-testpypi\n",
            "    name: Publish to PyPI\n    needs: build\n",
            "pypi does not wait",
        ),
        (
            "    name: CI on the tagged commit\n",
            "    name: CI on the tagged commit\n    if: false\n",
            "ci can be skipped",
        ),
        (
            "    timeout-minutes: 15\n",
            "    timeout-minutes: 15\n    continue-on-error: true\n",
            "build can be skipped",
        ),
    ],
)
def test_a_workflow_that_lets_a_release_around_a_gate_is_caught(
    old: str, new: str, problem: str
) -> None:
    assert old in RELEASE, old
    assert any(problem in found for found in _problems(RELEASE.replace(old, new, 1)))


def test_the_gates_are_the_ci_workflow_and_the_tag_check() -> None:
    jobs = _jobs(RELEASE)
    assert "uses: ./.github/workflows/ci.yml" in jobs["ci"]
    assert re.search(r"^  workflow_call:", CI, re.M)
    assert (
        'python scripts/check_changelog.py --tag "$GITHUB_REF_NAME" --tag-prefix v'
        in (jobs["check"])
    )


def test_there_is_no_platform_gate_because_the_package_depends_on_nothing() -> None:
    assert "platform" not in _jobs(RELEASE)
    assert "check_platform" not in RELEASE
    assert "dependencies = []" in (ROOT / "pyproject.toml").read_text(encoding="utf-8")


def test_publishing_is_by_trusted_publishing_and_no_secret_is_used() -> None:
    assert re.search(r"^permissions: \{\}$", RELEASE, re.M)  # nothing inherited
    assert "secrets." not in RELEASE
    assert "secrets." not in CI
    for forbidden in ("password:", "api-token", "TWINE_", "PYPI_TOKEN"):
        assert forbidden not in RELEASE
    jobs = _jobs(RELEASE)
    minting = {name for name, job in jobs.items() if "id-token: write" in job}
    assert minting == {"build", *PUBLISH}  # build for the attestation, the others for OIDC
    assert {name for name, job in jobs.items() if "attestations: write" in job} == {"build"}
    assert "contents: write" not in RELEASE
    for name in PUBLISH:
        job = jobs[name]
        assert "pypa/gh-action-pypi-publish@" in job
        assert re.search(r"^    permissions:\n      id-token: write\n    steps:", job, re.M)
    assert (
        "environment:\n      name: testpypi\n      url: https://test.pypi.org/p/dagnam-record"
        in (jobs["publish-testpypi"])
    )
    assert (
        "environment:\n      name: pypi\n      url: https://pypi.org/p/dagnam-record"
        in (jobs["publish-pypi"])
    )
    assert "repository-url: https://test.pypi.org/legacy/" in jobs["publish-testpypi"]
    assert "repository-url" not in jobs["publish-pypi"]


def test_every_action_is_pinned_to_a_commit() -> None:
    for name, workflow in (("release.yml", RELEASE), ("ci.yml", CI)):
        used = re.findall(r"uses: (\S+)", workflow)
        assert used, name
        for action in used:
            assert action.startswith("./") or PIN.fullmatch(f"uses: {action}"), action


def test_every_job_has_a_timeout() -> None:
    for name, workflow in (("release.yml", RELEASE), ("ci.yml", CI)):
        for job_name, job in _jobs(workflow).items():
            if re.search(r"^    uses: ", job, re.M):
                continue  # a call of a reusable workflow: its own jobs carry the timeouts
            assert re.search(r"^    timeout-minutes: \d+$", job, re.M), f"{name}:{job_name}"


def test_the_built_files_are_run_before_anything_is_published() -> None:
    build = _jobs(RELEASE)["build"]
    assert "        run: uv build" in build
    assert "twine check dist/*" in build
    assert 'python-version: "3.9"' in build  # the oldest supported Python, a clean environment
    assert 'scripts/smoke_record.py "$version"' in build
    assert "dist/*.whl dist/*.tar.gz" in build  # the wheel and the sdist both
    assert build.index("smoke_record.py") < build.index("attest-build-provenance")
    smoke = _jobs(RELEASE)["smoke-testpypi"]
    assert 'python scripts/smoke_record.py "${GITHUB_REF_NAME#v}"' in smoke
    assert "dagnam-record==${GITHUB_REF_NAME#v}" in smoke


def _bounds(name: str) -> tuple[str, str]:
    found = re.search(rf'^{name} = \("(>=[0-9.]+)", "(<[0-9.]+)"\)$', COMPAT, re.M)
    assert found is not None, name
    return found[1], found[2]


def test_the_matrix_runs_the_ends_of_the_ranges_the_recorder_declares() -> None:
    """Python 3.9, 3.11 and 3.13 against the lowest and the highest ``openai`` and ``anthropic``."""
    matrix = _jobs(CI)["matrix"]
    assert 'python-version: ["3.9", "3.11", "3.13"]' in matrix
    for sdk, package in (("openai", "OPENAI"), ("anthropic", "ANTHROPIC")):
        low, high = _bounds(package)
        floor = f"{low.removeprefix('>=')}.0"
        assert f'{sdk}: "{sdk}=={floor}"' in matrix, f"lowest {sdk} is not the declared floor"
        assert f'{sdk}: "{sdk}{high}"' in matrix, f"highest {sdk} is not the declared ceiling"
    assert matrix.count("name: lowest") == matrix.count("name: highest") == 1
    assert 'DAGNAM_RECORD_SDK_MATRIX: "1"' in matrix  # the fixtures are for the locked SDKs only
    # The guard that fails when the newest SDK drops a feature runs in "highest" rows only if the
    # row says which it is; it may skip in "lowest" rows.
    assert "DAGNAM_RECORD_SDK_ROW: ${{ matrix.sdk.name }}" in matrix
    # Through the repo's poe task, in the throwaway environment (poe is installed there).
    assert "poethepoet" in matrix
    assert 'PATH="$RUNNER_TEMP/env/bin:$PATH" poe test-record' in matrix
    assert (
        "pytest" not in matrix.split("- name: Recorder tests\n", 1)[1]
    )  # no bare pytest in the step
    assert "--cov" not in matrix  # the 100% floor is the check job's, through `poe check`
    assert "fail-fast: false" in matrix


def test_the_coverage_floor_stays_with_the_check_job() -> None:
    check = _jobs(CI)["check"]
    assert "run: uv run poe check" in check
    assert "fail_under = 100" in (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    # No flag overrides that floor.
    assert "--cov-fail-under" not in CI
    assert "--cov" not in _jobs(CI)["matrix"]
    assert "--cov" not in _jobs(CI)["sdist"]


def test_ci_runs_on_pull_requests_trunk_and_when_called() -> None:
    triggers = CI.split("\npermissions:", 1)[0]
    assert "  pull_request:\n" in triggers
    assert "    branches:\n      - main\n" in triggers
    assert "  workflow_call:\n" in triggers


def test_the_sdist_carries_tests_that_run_from_the_unpacked_archive() -> None:
    sdist = _jobs(CI)["sdist"]
    assert "uv build --sdist" in sdist
    assert (
        'DAGNAM_RECORD_SDK_MATRIX: "1"' in sdist
    )  # the newest SDKs, not the fixtures' locked ones
    # The one bare pytest: an unpacked archive has no uv.lock or poe, so no task runner.
    assert "-m pytest tests -q" in sdist
    assert "has no uv.lock" in sdist
    assert "poe test-record" not in sdist
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert 'include = ["dagnam_record", "tests", "scripts", ' in pyproject
    assert 'packages = ["dagnam_record"]' in pyproject  # the wheel is the package alone


def test_the_poe_task_the_matrix_calls_runs_only_the_tests_without_coverage() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    task = re.search(r"^test-record = (\{.*\})$", pyproject, re.M)
    assert task is not None
    assert '"python -m pytest tests -q -p no:cacheprovider"' in task[1]
    assert (
        'executor = { type = "simple" }' in task[1]
    )  # the active environment, not the repo's .venv
    assert "--cov" not in task[1]


def test_every_ci_call_of_the_recorders_tests_goes_through_poe_except_the_sdist() -> None:
    bare = [
        (name, line.strip())
        for name, job in _jobs(CI).items()
        for line in job.splitlines()
        if re.search(r"-m pytest|\bpytest tests", line) and not line.strip().startswith("#")
    ]
    assert [name for name, _ in bare] == ["sdist"], bare


def test_the_testpypi_install_takes_nothing_from_the_real_index() -> None:
    install = _jobs(RELEASE)["smoke-testpypi"].split("- name: Install from TestPyPI", 1)[1]
    install = install.split("- name: Run what was installed", 1)[0]
    # The package has no dependencies; a second index would let a squatted name win a tie.
    assert "--no-deps" in install
    assert "--index-url https://test.pypi.org/simple/" in install
    assert "extra-index-url" not in install
    assert "https://pypi.org/simple" not in install
