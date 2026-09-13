"""Bandit ``# nosec`` annotation currency tests.

Risk-register item 4 (13Sep2026): four ``# nosec B110`` annotations in
``src/loats/database.py`` emitted ``nosec encountered (B110), but no
failed test`` warnings on every scan. Probe-verified root cause: the
annotations were LOAD-BEARING (removing them yields four real B110
findings), but bandit 1.9.4 attributes B110 to the ``try:`` statement
line while the token sits on the ``except`` line, so its used-token
accounting misses and it emits the note anyway. Remediated by
refactoring the four ``try: conn.rollback() / except: pass`` blocks to
``contextlib.suppress(Exception)`` -- behaviorally identical, and the
B110 pattern (hence the token, hence the note) disappears entirely.

Contract pinned here:

1. The ``src/`` bandit scan must produce ZERO ``nosec encountered``
   notes: every ``# nosec`` token in ``src/`` must be consuming a real
   finding under the pinned bandit (1.9.4). A note means either a dead
   token or this same attribution quirk -- both are scan noise.
2. The ``src/`` bandit scan must stay at ZERO findings. This is the
   assertion that caught the misdiagnosis: B110 genuinely fires on
   try/except/pass in this tree, so any regression there (or any new
   finding anywhere) fails here.
3. The one proven-load-bearing crypto annotation (``utils/retry.py``
   B311 on ``random.uniform``) must stay: removing it introduces a
   real LOW-severity finding (verified by probe: bare
   ``random.uniform`` fires B311 on bandit 1.9.4).

Runs bandit as a subprocess against the real tree (house style: the
pip-audit waiver-currency tests in test_format_surface_contract.py
shell out the same way). Skipped only if bandit is not importable in
the active environment.
"""

from __future__ import annotations

import functools
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"

pytest.importorskip("bandit", reason="bandit not installed in this environment")


@functools.lru_cache(maxsize=1)
def _run_src_scan() -> tuple[subprocess.CompletedProcess[str], dict]:
    """Scan ``src/`` with the project config; return process + JSON payload.

    Cached module-level: one scan serves every test in this module. The
    JSON report goes to the system temp dir -- never the repo root, where
    an untracked artifact can trip the hygiene ceiling.
    """
    report_path = Path(tempfile.gettempdir()) / "bandit-currency-check.json"
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "bandit",
            "-r",
            str(SRC_DIR),
            "-c",
            str(REPO_ROOT / "pyproject.toml"),
            "-f",
            "json",
            "-o",
            str(report_path),
        ],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        check=False,
    )
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    return proc, payload


class TestBanditNosecCurrency:
    """Every ``# nosec`` in src/ must suppress a real finding."""

    def test_no_inert_nosec_annotations_anywhere_in_src(self) -> None:
        """Zero 'nosec encountered, but no failed test' notes on the src scan.

        Each note is a dead suppression token: it documents a finding the
        pinned bandit does not produce. Remove it (or, after a bandit bump
        makes the block fire, re-add it deliberately).
        """
        proc, _payload = _run_src_scan()
        inert_notes = [
            line for line in proc.stderr.splitlines() if "nosec encountered" in line
        ]
        assert inert_notes == [], (
            "Inert '# nosec' annotations detected -- these suppress nothing "
            f"under the pinned bandit and emit scan noise: {inert_notes}"
        )

    def test_src_scan_has_zero_findings(self) -> None:
        """The scan itself stays clean (CI gates on this via JSON metrics)."""
        _proc, payload = _run_src_scan()
        findings = payload.get("results", [])
        assert findings == [], (
            "bandit findings appeared in src/: "
            f"{[(r['test_id'], r['filename']) for r in findings]}"
        )

    def test_retry_b311_annotation_stays_load_bearing(self) -> None:
        """retry.py's B311 suppression is the one proven load-bearing token.

        Probe-verified on bandit 1.9.4: ``random.uniform`` fires B311
        (standard pseudo-random generators in a security context), so the
        ``# nosec: B311`` token MUST remain on the jitter line. If this
        test fails, someone removed a suppression that keeps a real
        finding dark.
        """
        retry_src = (REPO_ROOT / "src" / "loats" / "utils" / "retry.py").read_text(
            encoding="utf-8"
        )
        assert "# nosec: B311" in retry_src, (
            "src/loats/utils/retry.py lost its '# nosec: B311' annotation; "
            "random.uniform triggers a real B311 finding without it"
        )
