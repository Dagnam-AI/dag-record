"""The stdlib-only ``dagnam-record`` package keeps its promises, and every gate sees it.

The recorder runs on a customer's machine next to their training code. Its promise
is that it has no dependencies and never opens a network connection, so the
promise is checked here by reading its source (an AST walk), not by trust. The AST walk is also
the only guard that ``dagnam_record`` imports neither the SDK nor its contract: this repository
has no SDK to point an import-linter contract at.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

import pytest

# tomllib is the standard library from Python 3.11; the AST walk itself needs no more than 3.9,
# and the 3.12 jobs (the gate and the sdist run) cover it.
tomllib = pytest.importorskip("tomllib")

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "dagnam_record"

# Anything that can open a connection. Banned in every scope, lazy imports included.
NETWORK_MODULES = frozenset(
    {
        "requests",
        "urllib",
        "urllib3",
        "http",
        "httpx",
        "aiohttp",
        "socket",
        "socketserver",
        "ssl",
        "asyncio",
        "ftplib",
        "smtplib",
        "imaplib",
        "poplib",
        "telnetlib",
        "xmlrpc",
        "webbrowser",
    }
)
# ``importlib`` and ``__import__`` could load any of the above by a string the AST walk
# cannot read, so the package may not use them at all.
DYNAMIC_IMPORT_MODULES = frozenset({"importlib"})
DYNAMIC_IMPORT_CALLS = frozenset({"__import__", "import_module"})
# The SDK and its contract: banned at module level, so ``import dagnam_record`` never pulls
# them in. A lazy (function-level) import is allowed only where listed here, with its reason.
SDK_MODULES = frozenset({"dagnam", "dagnam_contracts"})
# The SDKs the recorder patches are not dependencies: ``import dagnam_record`` must work without
# them, so they may only be imported inside a function (where ``install`` looks for them).
PATCHED_SDKS = frozenset({"openai", "anthropic"})
LAZY_ALLOWLIST: dict[tuple[str, str], str] = {
    ("dagnam_record/_redact.py", "dagnam_contracts"): (
        'redact="auto" loads the optional PII redactor lazily, only when it is asked for and the '
        "dagnam-record[redact] extra is installed"
    ),
}


def _toml(path: Path) -> dict[str, Any]:
    return tomllib.loads(path.read_text(encoding="utf-8"))


def _imported_roots(node: ast.AST) -> list[str]:
    if isinstance(node, ast.Import):
        return [alias.name.split(".")[0] for alias in node.names]
    if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
        return [node.module.split(".")[0]]
    return []


def _walk(node: ast.AST, *, lazy: bool) -> list[tuple[str, bool]]:
    """Every ``(root module, is_lazy)`` imported under ``node``; lazy means inside a function."""
    found = [(root, lazy) for root in _imported_roots(node)]
    for child in ast.iter_child_nodes(node):
        inside = lazy or isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        found.extend(_walk(child, lazy=inside))
    return found


def _called_name(call: ast.Call) -> str | None:
    if isinstance(call.func, ast.Name):
        return call.func.id
    if isinstance(call.func, ast.Attribute):
        return call.func.attr
    return None


def violations(source: str, relative: str) -> list[str]:
    """What in ``source`` (a module at ``relative`` in the package) breaks the import rules."""
    found: list[str] = []
    for root, lazy in _walk(ast.parse(source), lazy=False):
        if root in NETWORK_MODULES:
            found.append(f"{relative}: imports network module {root!r}")
        elif root in DYNAMIC_IMPORT_MODULES:
            found.append(f"{relative}: imports {root!r}, which allows dynamic imports")
        elif (root in SDK_MODULES or root in PATCHED_SDKS) and not lazy:
            found.append(f"{relative}: imports {root!r} at module level")
        elif root in SDK_MODULES and (relative, root) not in LAZY_ALLOWLIST:
            found.append(f"{relative}: lazily imports {root!r} without an allowlist entry")
    found.extend(
        f"{relative}: calls {_called_name(node)!r}, a dynamic import"
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Call) and _called_name(node) in DYNAMIC_IMPORT_CALLS
    )
    return found


def test_the_package_metadata_promises_no_dependencies_and_python_39() -> None:
    project = _toml(ROOT / "pyproject.toml")["project"]
    assert project["name"] == "dagnam-record"
    assert project["dependencies"] == []
    assert project["requires-python"] == ">=3.9"
    assert project["license"] == "Apache-2.0"


def test_the_only_optional_extra_is_the_redactor_and_it_needs_only_the_contract() -> None:
    extras = _toml(ROOT / "pyproject.toml")["project"]["optional-dependencies"]
    assert list(extras) == ["redact"]
    assert [requirement.split(">")[0] for requirement in extras["redact"]] == ["dagnam-contracts"]


def test_the_lazy_contract_import_is_allowlisted_with_a_reason_and_really_exists() -> None:
    for (relative, root), reason in LAZY_ALLOWLIST.items():
        assert reason
        tree = ast.parse((ROOT / relative).read_text(encoding="utf-8"))
        lazy = [
            node
            for function in ast.walk(tree)
            if isinstance(function, ast.FunctionDef)
            for node in ast.walk(function)
            if isinstance(node, (ast.Import, ast.ImportFrom)) and root in _imported_roots(node)
        ]
        assert lazy, f"{relative} no longer imports {root} lazily: drop its allowlist entry"


def test_the_package_ships_typed_with_its_licence_files() -> None:
    assert (PACKAGE / "py.typed").is_file()
    assert (ROOT / "README.md").is_file()
    assert (ROOT / "CHANGELOG.md").is_file()
    assert "Apache License" in (ROOT / "LICENSE").read_text(encoding="utf-8")


def test_the_notice_is_the_recorders_own_and_names_nothing_it_does_not_ship() -> None:
    notice = (ROOT / "NOTICE").read_text(encoding="utf-8")
    assert notice.startswith("dagnam-record\nCopyright 2026 Dagnam.AI\n")
    assert "trademarks" in notice
    # The SDK's NOTICE credits tokenizer tables that only the SDK ships.
    for foreign in ("Qwen", "student_", "tokenizer", "vocabulary"):
        assert foreign not in notice


def test_the_classifiers_name_every_python_the_package_supports() -> None:
    classifiers = _toml(ROOT / "pyproject.toml")["project"]["classifiers"]
    for minor in range(9, 14):
        assert f"Programming Language :: Python :: 3.{minor}" in classifiers


def test_no_module_imports_the_network_or_the_sdk() -> None:
    modules = sorted(PACKAGE.rglob("*.py"))
    assert modules, "record/dagnam_record has no modules to check"
    found: list[str] = []
    for module in modules:
        relative = module.relative_to(ROOT).as_posix()
        found.extend(violations(module.read_text(encoding="utf-8"), relative))
    assert found == []


def test_the_import_walk_flags_each_kind_of_violation() -> None:
    assert violations("import socket\n", "a.py") == ["a.py: imports network module 'socket'"]
    assert violations("from urllib.request import urlopen\n", "a.py") == [
        "a.py: imports network module 'urllib'"
    ]
    assert violations("def f():\n    import requests\n", "a.py") == [
        "a.py: imports network module 'requests'"
    ]
    assert violations("import dagnam\n", "a.py") == ["a.py: imports 'dagnam' at module level"]
    assert violations(
        "try:\n    import dagnam_contracts\nexcept ImportError:\n    pass\n", "a.py"
    ) == ["a.py: imports 'dagnam_contracts' at module level"]
    assert violations("class C:\n    import dagnam\n", "a.py") == [
        "a.py: imports 'dagnam' at module level"
    ]
    assert violations("async def f():\n    import dagnam\n", "a.py") == [
        "a.py: lazily imports 'dagnam' without an allowlist entry"
    ]
    assert violations("import openai\n", "a.py") == ["a.py: imports 'openai' at module level"]
    assert violations("from anthropic import Anthropic\n", "a.py") == [
        "a.py: imports 'anthropic' at module level"
    ]
    assert (
        violations(
            "def install():\n    try:\n        import openai\n    except ImportError:\n        pass\n",
            "a.py",
        )
        == []
    )


def test_the_import_walk_flags_every_added_network_module() -> None:
    for module in sorted(NETWORK_MODULES):
        assert violations(f"import {module}\n", "a.py") == [
            f"a.py: imports network module {module!r}"
        ]


def test_the_import_walk_flags_dynamic_imports() -> None:
    assert violations("import importlib\n", "a.py") == [
        "a.py: imports 'importlib', which allows dynamic imports"
    ]
    assert violations("from importlib import import_module\n", "a.py") == [
        "a.py: imports 'importlib', which allows dynamic imports"
    ]
    assert violations("__import__('socket')\n", "a.py") == [
        "a.py: calls '__import__', a dynamic import"
    ]
    assert violations("def f(n):\n    return import_module(n)\n", "a.py") == [
        "a.py: calls 'import_module', a dynamic import"
    ]
    assert violations("x = importlib.import_module('ssl')\n", "a.py") == [
        "a.py: calls 'import_module', a dynamic import"
    ]
    assert violations("x = len('a')\nfoo.bar()\n(lambda: 1)()\n", "a.py") == []


def test_the_import_walk_allows_listed_lazy_imports_and_plain_ones() -> None:
    lazy = "def load():\n    import dagnam_contracts\n"
    assert violations(lazy, "dagnam_record/_redact.py") == []
    assert violations(lazy, "dagnam_record/other.py") == [
        "dagnam_record/other.py: lazily imports 'dagnam_contracts' without an allowlist entry"
    ]
    assert violations("import json\nfrom . import sibling\nfrom os import path\n", "a.py") == []


def test_pyright_ruff_and_coverage_see_the_package_at_its_oldest_python() -> None:
    tool = _toml(ROOT / "pyproject.toml")["tool"]
    assert tool["pyright"]["pythonVersion"] == "3.9"
    assert "dagnam_record" in tool["pyright"]["include"]
    assert tool["ruff"]["target-version"] == "py39"
    assert "dagnam_record" in tool["ruff"]["lint"]["isort"]["known-first-party"]
    assert tool["pytest"]["ini_options"]["testpaths"] == ["tests"]
    assert tool["coverage"]["run"]["source"] == ["dagnam_record"]
    assert tool["coverage"]["report"]["fail_under"] == 100
    test_task = tool["poe"]["tasks"]["test"]["cmd"]
    assert "--cov=dagnam_record" in test_task


needs_checkout = pytest.mark.skipif(
    not (ROOT / ".github").is_dir(), reason="a source distribution carries no .github"
)


@needs_checkout
def test_dependabot_and_code_owners_cover_the_package() -> None:
    dependabot = (ROOT / ".github" / "dependabot.yml").read_text(encoding="utf-8")
    assert 'package-ecosystem: "pip"' in dependabot
    assert 'package-ecosystem: "github-actions"' in dependabot
    owners = (ROOT / ".github" / "CODEOWNERS").read_text(encoding="utf-8")
    assert "/pyproject.toml" in owners
    assert "/.github/workflows/" in owners


@needs_checkout
def test_ci_runs_lint_types_and_the_tests_at_the_coverage_floor() -> None:
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "uv run poe check" in workflow
