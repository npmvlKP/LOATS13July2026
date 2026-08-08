"""Regression tests for the dependency manifest reconciliation check."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = REPO_ROOT / "scripts" / "check_deps_sync.py"


def _load_module() -> ModuleType:
    """Load the standalone script as a module for direct testing."""
    spec = importlib.util.spec_from_file_location("check_deps_sync", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_deps_sync"] = module
    spec.loader.exec_module(module)
    return module


check_deps_sync = _load_module()


@pytest.mark.parametrize(
    ("requirement", "expected"),
    [
        ("lxml>=6.1.1", "lxml"),
        ("lxml-html-clean>=0.4.5", "lxml-html-clean"),
        ("lxml_html_clean", "lxml-html-clean"),
        ("pydantic-settings>=2.7.0", "pydantic-settings"),
        ("newspaper4k[nlp]>=0.9.6", "newspaper4k"),
        ("cryptography ; python_version >= '3.12'", "cryptography"),
        ("  APScheduler>=3.10  ", "apscheduler"),
    ],
)
def test_requirement_name_normalizes(requirement: str, expected: str) -> None:
    """Requirement strings reduce to PEP 503 normalized distribution names."""
    assert check_deps_sync.requirement_name(requirement) == expected


def test_parse_requirements_skips_comments_and_flags(tmp_path: Path) -> None:
    """Comments, blank lines, and pip flags are excluded from the name set."""
    req_file = tmp_path / "requirements-core.txt"
    req_file.write_text(
        "# comment line\n\nlxml>=6.1.1\nhttpx>=0.28  # inline comment\n"
        "-r other.txt\n--index-url https://example.invalid\n",
        encoding="utf-8",
    )
    assert check_deps_sync.parse_requirements(req_file) == {"lxml", "httpx"}


def test_parse_pyproject_splits_runtime_and_optional(tmp_path: Path) -> None:
    """Runtime and optional dependency groups are returned separately."""
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        '[project]\nname = "x"\ndependencies = ["httpx>=0.28", "lxml>=6.1.1"]\n'
        '[project.optional-dependencies]\ndev = ["pytest>=8.0.0"]\n',
        encoding="utf-8",
    )
    runtime, optional = check_deps_sync.parse_pyproject(pyproject)
    assert runtime == {"httpx", "lxml"}
    assert optional == {"pytest"}


def test_main_detects_drift(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """A dependency present in only one manifest fails the check."""
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        '[project]\nname = "x"\ndependencies = ["httpx>=0.28"]\n', encoding="utf-8"
    )
    req_file = tmp_path / "requirements-core.txt"
    req_file.write_text("httpx>=0.28\ncryptography>=50.0.0\n", encoding="utf-8")

    monkeypatch.setattr(check_deps_sync, "PYPROJECT", pyproject)
    monkeypatch.setattr(check_deps_sync, "REQUIREMENTS_CORE", req_file)

    assert check_deps_sync.main() == 1


def test_repository_manifests_are_in_sync() -> None:
    """pyproject.toml and requirements-core.txt declare the same distributions."""
    runtime, optional = check_deps_sync.parse_pyproject(check_deps_sync.PYPROJECT)
    core = check_deps_sync.parse_requirements(check_deps_sync.REQUIREMENTS_CORE)

    assert not runtime - core
    assert not core - runtime - optional
