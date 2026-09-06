#!/usr/bin/env python3
"""F8-L-05 eval: 10-case before/after benchmark (feed-validation closure).

BEFORE scores are hard-coded from forensic evidence (F6-L-06 carried since
FR1; F8-L-05 re-carried in 01Sep2026-FR.md; TODO-27d removed the defunct
feed but added no validator): the tree had feeds configured but zero
proof artifacts. AFTER scores are measured live against this tree.

Run:  loatsNEW/Scripts/python.exe scripts/eval_f8l05.py
Exit: 0 = all after-cases pass; 1 = at least one fails.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC = PROJECT_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

# ---------------------------------------------------------------------------
# BEFORE (hard-coded forensic baseline, TODO-27d tree @ 2026-08-30)
# ---------------------------------------------------------------------------
# E1 False: validator absent; E2 False: no CI job; E3 False: no startup gate;
# E4 False: no recorded fallback; E5 False: no manifest/lockstep;
# E6 False: no defunct-feed re-entry guard; E7 False: no gate in health check;
# E8 False: no orchestrator wiring; E9 False: no recorded fixtures;
# E10 False: no tests. (Present-day re-measurement of the baseline tree is
# impossible without a worktree rebuild; TODO-27d closure reports + the FR
# carry-forward record document each absent artifact.)
BEFORE = {
    "E1": (False, "no validator existed"),
    "E2": (False, "no CI feed-validation job existed"),
    "E3": (False, "no startup gate existed"),
    "E4": "no recorded fallback existed",
    "E5": "no manifest/settings lockstep existed",
    "E6": "no defunct-feed re-entry guard existed",
    "E7": "no health-check probe existed",
    "E8": "no orchestrator wiring existed",
    "E9": "no recorded fixtures existed",
    "E10": "no closure tests existed",
}


# ---------------------------------------------------------------------------
# Live AFTER checks
# ---------------------------------------------------------------------------
def live_e1() -> tuple[bool, str]:
    """Deterministic offline validator passes against the recorded manifest."""
    import subprocess

    proc = subprocess.run(
        [
            sys.executable,
            str(PROJECT_ROOT / "scripts" / "validate_rss_feeds.py"),
            "--offline",
        ],
        capture_output=True,
        text=True,
        cwd=PROJECT_ROOT,
        timeout=60,
    )
    return proc.returncode == 0, f"exit={proc.returncode}"


def live_e2() -> tuple[bool, str]:
    """CI workflow carries a dedicated rss-feeds job."""
    try:
        import yaml

        jobs = list(
            yaml.safe_load(
                (PROJECT_ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
            )["jobs"]
        )
        return "rss-feeds" in jobs, f"jobs={len(jobs)}"
    except Exception as exc:
        return False, repr(exc)


def live_e3() -> tuple[bool, str]:
    """Startup gate runs at orchestrator start."""
    import inspect

    from loats.orchestrator import TradingOrchestrator

    src = inspect.getsource(TradingOrchestrator.start)
    return "_validate_rss_startup_gate" in src, "wired in start()"


def live_e4() -> tuple[bool, str]:
    """Offline recorded-fallback validation passes from the module API."""
    from loats.rss_validation import run_offline_manifest_validation

    r = run_offline_manifest_validation()
    return r.ok, f"{len(r.results)} sources"


def live_e5() -> tuple[bool, str]:
    """Manifest sources == settings.rss_feeds (lockstep)."""
    from loats.config import get_settings
    from loats.rss_validation import run_offline_manifest_validation

    urls = run_offline_manifest_validation().urls
    settings_urls = list(get_settings().rss_feeds)
    return sorted(urls) == sorted(settings_urls), f"{len(urls)} vs {len(settings_urls)}"


def live_e6() -> tuple[bool, str]:
    """Defunct-feed re-entry guard: validator rejects the old URL class."""
    from loats.rss_validation import (
        DEFUNCT_FEED_MARKER,
        validate_recorded_source,
    )

    result = validate_recorded_source(
        {
            "name": "defunct",
            "url": f"https://www.{DEFUNCT_FEED_MARKER}.com/markets-feed",
            "fixture": "tests/fixtures/rss/whatever.xml",
        },
        repo_root=PROJECT_ROOT,
    )
    return (not result.ok), "marker rejected" if not result.ok else "GUARD HOLE"


def live_e7() -> tuple[bool, str]:
    """Health check carries the HC-28 probe wired into main()."""
    import inspect

    import fr7_health_check as hc  # type: ignore[no-redef] - scripts path prepended below

    src_main = inspect.getsource(hc.main)
    ok = (
        hasattr(hc, "probe_rss_feeds")
        and "HC-28" in src_main
        and "probe_rss_feeds(rep)" in src_main
    )
    return ok, "probe + routing present" if ok else "probe missing"


def live_e8() -> tuple[bool, str]:
    """Gate errors are isolated (startup never crashes on gate failure)."""
    from unittest.mock import AsyncMock, patch

    import anyio

    from loats.orchestrator import TradingOrchestrator

    async def probe() -> bool:
        with patch(
            "loats.rss_validation.run_startup_gate",
            new_callable=AsyncMock,
            side_effect=RuntimeError("boom"),
        ):
            await TradingOrchestrator()._validate_rss_startup_gate()
        return True

    try:
        return anyio.run(probe), "exception isolated"
    except Exception as exc:
        return False, repr(exc)


def live_e9() -> tuple[bool, str]:
    """Recorded fixtures are genuine RSS payloads with items."""
    from loats.rss_validation import load_manifest

    ok_all, counts = True, []
    for source in load_manifest():
        body = (PROJECT_ROOT / str(source["fixture"])).read_text(
            encoding="utf-8", errors="replace"
        )
        items = body.lower().count("<item")
        counts.append(items)
        ok_all = ok_all and items >= 1 and "<rss" in body.lower()
    return ok_all, f"items per fixture: {counts}"


def live_e10() -> tuple[bool, str]:
    """Closure test module passes."""
    import subprocess

    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/test_rss_validation.py",
            "-q",
            "--no-header",
            "-x",
        ],
        capture_output=True,
        text=True,
        cwd=PROJECT_ROOT,
        timeout=300,
    )
    line = next((ln for ln in reversed(proc.stdout.splitlines()) if "passed" in ln), "")
    return proc.returncode == 0, line.strip()


# ---------------------------------------------------------------------------
# Harness
# ---------------------------------------------------------------------------
def main() -> int:
    print("=" * 70)
    print("F8-L-05 EVAL — RSS feed validation closure (10 cases)")
    print("=" * 70)

    before_score = sum(1 for v in BEFORE.values() if v is True)
    after_cases = {
        "E1": live_e1,
        "E2": live_e2,
        "E3": live_e3,
        "E4": live_e4,
        "E5": live_e5,
        "E6": live_e6,
        "E7": live_e7,
        "E8": live_e8,
        "E9": live_e9,
        "E10": live_e10,
    }

    after_results = {}
    after_score = 0
    for case_id, fn in after_cases.items():
        try:
            ok, detail = fn()
        except Exception as exc:
            ok, detail = False, repr(exc)
        after_results[case_id] = {"ok": bool(ok), "detail": detail}
        after_score += 1 if ok else 0
        print(f"  [{case_id}] {'PASS' if ok else 'FAIL'} -- {detail}")

    print("-" * 70)
    print(f"BEFORE (forensic baseline): {before_score}/10")
    print(
        f"AFTER  (measured live):     {after_score}/10   (delta +{after_score - before_score})"
    )

    payload = {
        "timestamp": datetime.now(UTC).isoformat(),
        "before": {k: str(v) for k, v in BEFORE.items()},
        "before_score": before_score,
        "after": after_results,
        "after_score": after_score,
    }
    out = PROJECT_ROOT / "reports" / "f8l05_eval.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(
        f"report -> {out.relative_to(PROJECT_ROOT)} (gitignored by reports/*.json rule)"
    )
    return 0 if after_score == 10 else 1


if __name__ == "__main__":
    sys.exit(main())
