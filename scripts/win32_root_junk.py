"""Shared Win32-safe root junk detection (F8-M-03).

Single source of truth for the HC-26 "forbidden root junk names"
probe, used by all three implementations of the check:

* ``scripts/check_repo_hygiene.py``   (CI job ``repo-hygiene``,
  pre-commit hook, delegated by fr7_health_check HC-26)
* ``scripts/fr7_health_check.py``     (inline HC-26 forbidden-name scan)
* ``scripts/verify_hc_registry.py``   (``_check_hc26``)

Why not ``Path.exists()`` / ``os.path.exists()``
-----------------------------------------------
On Windows, Win32 path normalization makes exists-probing unreliable
in BOTH directions for the junk names this check hunts. Both behaviors
were live-verified 2026-09-03 (Python 3.11, Windows 11, NTFS):

* A trailing-dot name that IS on disk (created by NT-native APIs --
  e.g. ``G......`` captured at this repo's root) is INVISIBLE to
  exists-probing: Win32 strips trailing dots before probing, so
  ``Path.exists()`` returns False for a file that is present. The
  pre-F8-M-03 probe was green while the artifact existed (the
  F8-M-03 false-green).
* Conversely, ``os.open("G......")`` SUCCEEDS on Win32 because the
  kernel silently creates the dot-stripped name ``G``; an
  exists-probe for ``G......`` then returns True by aliasing onto
  that phantom sibling -- a false positive.

``os.listdir`` never normalizes: it returns on-disk names verbatim
from the NT namespace in both scenarios. Directory-enumeration
membership is therefore the ONLY sound presence test for this probe,
in either direction.

Case handling
-------------
Windows filesystems are case-insensitive but case-preserving, so the
membership comparison normalizes BOTH sides with ``os.path.normcase``
(fold-cases to lowercase on Windows; identity on POSIX, where the
comparison degenerates to exact case-sensitive matching).

Failure semantics
-----------------
If the root cannot be enumerated (``OSError`` from the directory
enumeration)
the check cannot be performed, so this helper raises ``RuntimeError``
-- callers must fail closed, never silently pass.

Public API
----------
``forbidden_root_junk(root)``
    Returns the sorted subset of ``ROOT_JUNK_NAMES`` present at
    ``root`` (by on-disk name). ``root`` defaults to the repository
    root of THIS repo (``scripts/..``) so guard scripts need no
    argument; the HC tests pass an explicit temp dir.
``ROOT_JUNK_NAMES``
    The forbidden-name tuple, mirrored from check_repo_hygiene.py
    (kept in lockstep by the HC test suite).
"""

from __future__ import annotations

import os
from pathlib import Path

# Forbidden junk artifact names at the repo root (F8-C-02 / TODO-21 /
# FR-26). Mirrored in scripts/check_repo_hygiene.py ROOT_JUNK_NAMES;
# tests/test_repo_hygiene.py pins the two in lockstep.
ROOT_JUNK_NAMES: tuple[str, ...] = (
    "-p",
    "G......",
    "0.21.0",
    "$null",
    "[100%]",
    "tmp_schema.db",
    "pytest_output.txt",
)


def forbidden_root_junk(root: str | os.PathLike[str] | None = None) -> list[str]:
    """Return the forbidden root junk names present at ``root``.

    Win32-safe: on-disk name membership via directory enumeration
    (``os.scandir``; ``os.listdir`` semantics -- verbatim NT names)
    with normcased comparison on both sides. Never path-probes: on
    Windows exists-probing both misses real trailing-dot files and
    aliases onto dot-stripped phantom siblings (see module docstring).

    Raises ``RuntimeError`` if ``root`` cannot be enumerated so the
    calling check fails closed.
    """
    directory = Path(root) if root is not None else Path(__file__).parent.parent
    try:
        # os.scandir (like os.listdir, which wraps it) returns on-disk
        # names VERBATIM from the NT namespace -- unlike pathlib parsing,
        # which is subject to Windows path normalization. DirEntry.name
        # is the raw final component; never construct Paths from it.
        with os.scandir(directory) as entries:
            listing = {os.path.normcase(entry.name) for entry in entries}
    except OSError as exc:
        raise RuntimeError(f"cannot enumerate root {directory}: {exc}") from exc

    return sorted(name for name in ROOT_JUNK_NAMES if os.path.normcase(name) in listing)
