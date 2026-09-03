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

Class-wide hostile names (F8-M-04)
----------------------------------
The pinned name list below enumerates PAST artifacts only; a new shell
redirection mishap produces a NEW junk name (the F8-M-04 incident
artifact was a 7-byte capture at the repo root whose name was a
drive-letter prefix plus trailing dots). Names whose final component
is hostile to the Win32 namespace are therefore detected class-wide,
evaluated against ``os.scandir`` verbatim names only (never
path-parsed -- the same soundness argument as above). Win32 strips
trailing dots and spaces from the final component before stat/open,
so such entries are unopenable and undeletable through normal Win32
paths -- exactly the property that made ``G......`` invisible to
exists-probing. The hostile classes:

* trailing dot(s) or space(s) -- ``G......``, ``out.txt.``, ``x ``;
* a colon anywhere in the name (NT stream separator -- creatable on
  POSIX, uncheckoutable on Windows clones);
* reserved device names, optionally dot-extensioned -- ``NUL``,
  ``NUL.txt`` (``> NUL`` redirection mishaps).

Patterns are lowercase and matched against ``os.path.normcase``-folded
verbatim names. On POSIX the fold is identity, so reserved-name
matching is exact-case there; the class-wide scan still runs on POSIX
(a ``G......`` created on Windows and committed to git materializes
verbatim in a Linux clone -- CI on ubuntu must catch it too).

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
``is_hostile_root_name(name)``
    True if a verbatim on-disk name matches any Win32-hostile class
    (F8-M-04).
``hostile_root_names(root)``
    Sorted verbatim on-disk root entry names matching the hostile
    classes above (F8-M-04).
``root_junk_findings(root)``
    Deduplicated, sorted union of the pinned-name and hostile-class
    findings -- the entry point the three HC-26 implementations use.
"""

from __future__ import annotations

import os
import re
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

# F8-M-04: class-wide Win32-hostile final-component patterns,
# evaluated against os.scandir VERBATIM names (never Path-parsed --
# parsing/exists-probing is exactly what hides trailing-dot entries).
# Patterns are lowercase; callers match against os.path.normcase-folded
# names (fold is identity on POSIX, so matching there is exact-case).
# Hostile classes:
# * trailing dot(s)/space(s): Win32 strips them before stat/open, so
#   the entry is invisible to exists-probing and undeletable via
#   normal Win32 paths (the F8-M-04 "G......" artifact's class).
# * colon anywhere: NT alternate-data-stream separator; a file created
#   on POSIX with a colon in its name cannot be checked out on
#   Windows (invalid path character).
# * reserved device names, optionally dot-extensioned: "NUL", "NUL.txt"
#   etc. (" > NUL" redirection mishaps); legacy Win32 resolves these to
#   devices regardless of directory.
_WIN32_RESERVED_BASENAMES: frozenset[str] = frozenset(
    {
        "con",
        "prn",
        "aux",
        "nul",
        "com1",
        "com2",
        "com3",
        "com4",
        "com5",
        "com6",
        "com7",
        "com8",
        "com9",
        "lpt1",
        "lpt2",
        "lpt3",
        "lpt4",
        "lpt5",
        "lpt6",
        "lpt7",
        "lpt8",
        "lpt9",
    }
)
_HOSTILE_TAIL_RE = re.compile(r"[. ]$")
_HOSTILE_RESERVED_RE = re.compile(r"^(?P<base>[a-z0-9]+)(?P<ext>\.[.a-z0-9]*)$")


def is_hostile_root_name(name: str) -> bool:
    """True if a verbatim on-disk name is Win32-hostile (F8-M-04).

    ``name`` must be a final path component as returned by directory
    enumeration (``DirEntry.name`` / ``os.listdir``) -- never a parsed
    or normalized Path. Matched against ``os.path.normcase``-folded
    input. Class-wide complement to the pinned ``ROOT_JUNK_NAMES``
    list: catches FUTURE shell-redirection mishaps, not just past
    artifacts.
    """
    folded = os.path.normcase(name)
    if _HOSTILE_TAIL_RE.search(folded):
        return True  # trailing dot(s)/space(s): Win32 dot-strip class
    if ":" in folded:
        return True  # NT alternate-data-stream separator
    if folded in _WIN32_RESERVED_BASENAMES:
        return True  # bare reserved device name ("nul", "con", ...)
    match = _HOSTILE_RESERVED_RE.match(folded)
    if match and match.group("base") in _WIN32_RESERVED_BASENAMES:
        return True  # reserved device name, optionally dot-extensioned
    return False


def hostile_root_names(root: str | os.PathLike[str] | None = None) -> list[str]:
    """Return verbatim on-disk root entry names matching the hostile
    classes (F8-M-04). Same enumeration semantics as
    :func:`forbidden_root_junk`; raises ``RuntimeError`` if ``root``
    cannot be enumerated (fail closed).
    """
    directory = Path(root) if root is not None else Path(__file__).parent.parent
    try:
        with os.scandir(directory) as entries:
            listing = [entry.name for entry in entries]
    except OSError as exc:
        raise RuntimeError(f"cannot enumerate root {directory}: {exc}") from exc
    return sorted(name for name in listing if is_hostile_root_name(name))


def root_junk_findings(root: str | os.PathLike[str] | None = None) -> list[str]:
    """Deduplicated, sorted union of pinned-name and hostile-class
    findings (F8-M-04 entry point for the HC-26 implementations).
    Raises ``RuntimeError`` if ``root`` cannot be enumerated (fail
    closed).
    """
    directory = Path(root) if root is not None else Path(__file__).parent.parent
    pinned = forbidden_root_junk(directory)
    hostile = hostile_root_names(directory)
    return sorted(set(pinned) | set(hostile))


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
