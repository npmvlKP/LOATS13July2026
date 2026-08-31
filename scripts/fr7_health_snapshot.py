#!/usr/bin/env python3
"""FR7 Health Snapshot — wave-over-wave baselines.

Wraps ``scripts/fr7_health_check.py`` with ``--json`` and writes a
timestamped baseline to ``reports/health/`` for trend comparison.

Each snapshot is a JSON file ``health[-<label>]-YYYYMMDD-HHMMSS.json``
containing the full master report (timestamp, summary, groups, results).
On every run the wrapper prints a trend table of the last 5 snapshots so
wave progress is visible at a glance.

Usage
-----
    python scripts/fr7_health_snapshot.py                 # full run → reports/health/health-20260830-211500.json
    python scripts/fr7_health_snapshot.py --fast          # structural+static only
    python scripts/fr7_health_snapshot.py --label baseline  # health-baseline-20260830-...json
    python scripts/fr7_health_snapshot.py --only S01,T01  # subset baseline
    python scripts/fr7_health_snapshot.py --group static  # one group

Exit code mirrors the master (0 only when zero FAIL, SKIP allowed).
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
HEALTH_DIR = REPO_ROOT / "reports" / "health"


def _resolve_python() -> str:
    for cand in [
        REPO_ROOT / "loatsNEW" / "Scripts" / "python.exe",
        REPO_ROOT / "loatsNEW" / "bin" / "python",
        REPO_ROOT / ".venv" / "Scripts" / "python.exe",
        REPO_ROOT / ".venv" / "bin" / "python",
    ]:
        if cand.exists():
            return str(cand)
    return sys.executable


PY = _resolve_python()


def _load_summary(p: Path) -> dict:
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data.get("summary", {})
    except Exception:
        return {}


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument(
        "--fast",
        action="store_true",
        help="pass --fast to master (structural+static only)",
    )
    ap.add_argument(
        "--label",
        default="",
        help="optional label inserted in filename: health-<label>-<stamp>.json",
    )
    ap.add_argument(
        "--only", default="", help="comma-separated check IDs to pass to master"
    )
    ap.add_argument(
        "--group",
        choices=["structural", "static", "live-probe", "gate"],
        help="pass --group to master",
    )
    ap.add_argument("--verbose", action="store_true", help="pass --verbose to master")
    args = ap.parse_args()

    HEALTH_DIR.mkdir(parents=True, exist_ok=True)
    # Ensure .gitkeep so directory tracks even when empty
    gitkeep = HEALTH_DIR / ".gitkeep"
    if not gitkeep.exists():
        gitkeep.write_text("", encoding="utf-8")

    # Timestamp in IST-aware fashion but file name uses UTC-like sortable stamp
    # Use local time for readability, but also include UTC in JSON.
    now_local = datetime.now().astimezone()
    stamp = now_local.strftime("%Y%m%d-%H%M%S")
    # Also include UTC timestamp for JSON
    utc_iso = datetime.now(UTC).isoformat()

    label_seg = f"-{args.label}" if args.label else ""
    out = HEALTH_DIR / f"health{label_seg}-{stamp}.json"

    cmd: list[str] = [PY, "scripts/fr7_health_check.py", "--json", str(out)]
    if args.fast:
        cmd.append("--fast")
    if args.only:
        cmd.extend(["--only", args.only])
    if args.group:
        cmd.extend(["--group", args.group])
    if args.verbose:
        cmd.append("--verbose")

    print(f"[snapshot] {now_local.strftime('%Y-%m-%d %H:%M:%S %Z')}  UTC {utc_iso}")
    print(f"[snapshot] repo: {REPO_ROOT}")
    print(f"[snapshot] master: {' '.join(cmd)}")
    print(f"[snapshot] baseline → {out.relative_to(REPO_ROOT)}")

    # Run master
    rc = subprocess.run(cmd, cwd=REPO_ROOT).returncode

    # Verify file was written (master may have failed to write JSON on crash)
    if not out.exists():
        print(
            f"[snapshot] WARNING: master did not write {out} (exit={rc})",
            file=sys.stderr,
        )
        # Try to create a minimal placeholder so trend isn't broken
        try:
            out.write_text(
                json.dumps(
                    {
                        "timestamp": utc_iso,
                        "error": "master did not write baseline",
                        "exit_code": rc,
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
        except Exception:
            pass
    else:
        print(
            f"[snapshot] wrote {out.name} ({out.stat().st_size} bytes)  master exit={rc}"
        )

    # Trend comparison
    snapshots = sorted(HEALTH_DIR.glob("health*.json"), key=lambda p: p.stat().st_mtime)
    # Exclude the just-written file from "previous" count for delta message
    prev = [p for p in snapshots if p != out]
    print(
        f"[snapshot] {len(snapshots)} baseline(s) in reports/health/ (including this one)"
    )

    if snapshots:
        # Build trend table of last 5
        print("\n[snapshot] Wave-over-wave trend (last 5):")
        print(
            f"{'FILE':<38} {'TOTAL':>5} {'PASS':>5} {'FAIL':>5} {'SKIP':>5} {'HEALTHY':>7}"
        )
        print("─" * 72)
        for p in snapshots[-5:]:
            s = _load_summary(p)
            total = s.get("total", "?")
            passed = s.get("passed", "?")
            failed = s.get("failed", "?")
            skipped = s.get("skipped", "?")
            healthy = s.get("healthy", None)
            healthy_str = (
                "yes" if healthy is True else "no" if healthy is False else "?"
            )
            marker = " ← current" if p == out else ""
            print(
                f"{p.name:<38} {total!s:>5} {passed!s:>5} {failed!s:>5} {skipped!s:>5} {healthy_str:>7}{marker}"
            )

        if prev:
            # Compare current vs most recent previous
            try:
                cur_sum = _load_summary(out)
                prev_sum = _load_summary(prev[-1])
                if cur_sum and prev_sum:
                    df = (cur_sum.get("failed", 0) or 0) - (
                        prev_sum.get("failed", 0) or 0
                    )
                    dp = (cur_sum.get("passed", 0) or 0) - (
                        prev_sum.get("passed", 0) or 0
                    )
                    if df < 0:
                        print(
                            f"\n[snapshot] Trend: FAIL count improved by {abs(df)} vs {prev[-1].name}  ({prev_sum.get('failed')} → {cur_sum.get('failed')})"
                        )
                    elif df > 0:
                        print(
                            f"\n[snapshot] Trend: FAIL count regressed by {df} vs {prev[-1].name}  ({prev_sum.get('failed')} → {cur_sum.get('failed')})"
                        )
                    else:
                        print(
                            f"\n[snapshot] Trend: FAIL count unchanged ({cur_sum.get('failed')}) vs {prev[-1].name}"
                        )
                    if dp != 0:
                        print(
                            f"[snapshot]           PASS delta {dp:+d}  ({prev_sum.get('passed')} → {cur_sum.get('passed')})"
                        )
            except Exception as e:
                print(f"[snapshot] Trend compare error: {e}", file=sys.stderr)

        print("─" * 72)
        print(
            "[snapshot] Compare summaries with:  python -c \"import json, pathlib; print(json.dumps(json.loads(pathlib.Path('reports/health/<file>').read_text())['summary'], indent=2))\""
        )

    # Mirror master exit code (0 only when healthy)
    if rc == 0:
        print("\n[snapshot] HEALTHY — baseline captured, no FAIL (SKIP allowed).")
    else:
        print(
            f"\n[snapshot] UNHEALTHY — master exit {rc}; baseline still written for trend tracking.",
            file=sys.stderr,
        )

    return rc


if __name__ == "__main__":
    sys.exit(main())
