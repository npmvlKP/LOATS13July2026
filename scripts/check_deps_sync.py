#!/usr/bin/env python3
"""Reconcile dependency declarations between pyproject.toml and requirements-core.txt.

The Dockerfile installs from ``requirements-core.txt`` while CI and any
``pip install loats13july2026`` consumer resolve from ``pyproject.toml``.
Drift between the two manifests produces an image whose dependency closure
differs from the published wheel. This check fails the build when either
manifest declares a distribution the other omits.
"""

from __future__ import annotations

import re
import sys
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = REPO_ROOT / "pyproject.toml"
REQUIREMENTS_CORE = REPO_ROOT / "requirements-core.txt"

_NAME_END = re.compile(r"[\[<>=!~;@\s]")
_NORMALIZE = re.compile(r"[-_.]+")


def normalize(name: str) -> str:
    """Return the PEP 503 normalized form of a distribution name."""
    return _NORMALIZE.sub("-", name).lower()


def requirement_name(requirement: str) -> str:
    """Extract the normalized distribution name from a requirement string."""
    stripped = requirement.strip()
    match = _NAME_END.search(stripped)
    return normalize(stripped[: match.start()] if match else stripped)


def parse_pyproject(path: Path) -> tuple[set[str], set[str]]:
    """Return (runtime, optional) normalized names declared in pyproject.toml."""
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    project = data.get("project", {})
    runtime = {requirement_name(r) for r in project.get("dependencies", [])}
    optional: set[str] = set()
    for group in project.get("optional-dependencies", {}).values():
        optional.update(requirement_name(r) for r in group)
    return runtime, optional


def parse_requirements(path: Path) -> set[str]:
    """Return normalized names declared in a requirements file."""
    names: set[str] = set()
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line or line.startswith("-"):
            continue
        names.add(requirement_name(line))
    return names


def main() -> int:
    """Compare both manifests and report any one-sided declarations."""
    runtime, optional = parse_pyproject(PYPROJECT)
    core = parse_requirements(REQUIREMENTS_CORE)

    missing_from_core = sorted(runtime - core)
    missing_from_pyproject = sorted(core - runtime - optional)

    if not missing_from_core and not missing_from_pyproject:
        print("Dependency manifests are in sync.")
        return 0

    print("Dependency manifest drift detected.")
    for name in missing_from_core:
        print(
            f"  {name}: declared in pyproject.toml [project.dependencies] "
            f"but missing from requirements-core.txt"
        )
    for name in missing_from_pyproject:
        print(
            f"  {name}: declared in requirements-core.txt but missing from "
            f"pyproject.toml [project.dependencies] and [project.optional-dependencies]"
        )
    return 1


if __name__ == "__main__":
    sys.exit(main())
