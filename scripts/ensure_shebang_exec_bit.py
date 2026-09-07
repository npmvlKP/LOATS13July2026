#!/usr/bin/env python3
"""Self-healing executable-bit normalizer for shebang'd Python scripts.

Context (ADR-0013): git exec bits are not representable on the Windows
filesystem, so scripts committed from Windows land at mode 100644 even
when they carry a shebang. Windows-local ruff suppresses EXE001, so the
defect is invisible until CI, where both Linux ruff jobs fail
(``EXE001 Shebang is present but file is not executable``) — the exact
recurrence class recorded in ADR-0012 and realized by db5957b's
predecessor on verify_f8m02_m07_external.py.

Decision: a pre-commit local hook that runs this normalizer over the
staged Python files. For every staged ``*.py`` whose index mode is
100644 but whose content starts with a shebang, the bit is flipped to
100755 via ``git update-index --chmod=+x`` (the only Windows-safe
mechanism — it records the mode in the index directly). The hook is
self-healing: it fixes and exits 0 rather than blocking, while the CI
EXE001 gate stays the hard verifier of record. Run with no arguments it
normalizes the whole tracked Python tree (idempotent no-op when clean).

Usage:
    pre-commit hook (staged filenames passed through), or:
    python scripts/ensure_shebang_exec_bit.py [paths...]

Integrated as:
    - pre-commit hook ``shebang-exec-bit`` (.pre-commit-config.yaml)
    - live-tree invariant pinned by tests/test_repo_hygiene.py
      (TestShebangExecBit)
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
EXEC_MODE = "100755"
NON_EXEC_MODE = "100644"


def _git(*args: str) -> str:
    proc = subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        shell=False,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.stdout


def has_shebang(path: Path) -> bool:
    """True when the file's first two bytes are the shebang marker."""
    try:
        with path.open("rb") as fh:
            return fh.read(2) == b"#!"
    except OSError:
        return False


def parse_mode(lsfiles_line: str) -> str:
    """Extract the object mode from a ``git ls-files -s`` row."""
    return lsfiles_line.split(" ", 1)[0]


def tracked_py_modes(paths: list[str] | None = None) -> dict[str, str]:
    """Map tracked .py path -> index mode (all tracked, or the given subset)."""
    if paths:
        args = ["ls-files", "-s", "--", *paths]
    else:
        args = ["ls-files", "-s", "--", "*.py"]
    modes: dict[str, str] = {}
    for line in _git(*args).splitlines():
        if not line.strip():
            continue
        meta, path = line.split("\t", 1)
        modes[path] = parse_mode(meta)
    return modes


def needs_fix(mode: str, path: str) -> bool:
    """True when a shebang'd script sits at the non-executable mode."""
    return mode == NON_EXEC_MODE and has_shebang(REPO_ROOT / path)


def enable_exec_bit(paths: list[str]) -> None:
    _git("update-index", "--chmod=+x", "--", *paths)


def main(argv: list[str] | None = None) -> int:
    paths = list(sys.argv[1:]) if argv is None else list(argv)
    modes = tracked_py_modes(paths or None)
    to_fix = sorted(p for p, m in modes.items() if needs_fix(m, p))
    for path in to_fix:
        print(f"enabled executable bit: {path} (shebang staged at 100644)")
    if to_fix:
        enable_exec_bit(to_fix)
        print(f"fixed {len(to_fix)} file(s); commit now carries mode 100755")
    else:
        print("OK every tracked shebang'd script already carries mode 100755")
    return 0


if __name__ == "__main__":
    sys.exit(main())
