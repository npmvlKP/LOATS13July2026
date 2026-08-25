#!/usr/bin/env python
"""Write a timestamped FR7 health snapshot to reports/health/ for trend tracking.

Usage (clean venv):
  python scripts/fr7_health_snapshot.py            # full run
  python scripts/fr7_health_snapshot.py --fast     # quick structural pass
  python scripts/fr7_health_snapshot.py --label baseline   # custom label
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
HEALTH_DIR = REPO_ROOT / "reports" / "health"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--fast", action="store_true")
    ap.add_argument("--label", default="", help="baseline | stage-a | final | ...")
    args = ap.parse_args()

    HEALTH_DIR.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    label = f"-{args.label}" if args.label else ""
    out = HEALTH_DIR / f"health{label}-{stamp}.json"

    cmd = [sys.executable, "scripts/fr7_health_check.py", "--json", str(out)]
    if args.fast:
        cmd.append("--fast")
    print("Running:", " ".join(cmd))
    rc = subprocess.run(cmd, cwd=REPO_ROOT).returncode

    print(f"\nSnapshot: {out.name}  (master exit={rc})")
    prev = sorted(HEALTH_DIR.glob("health*.json"))
    if len(prev) > 1:
        print(
            f"{len(prev) - 1} earlier snapshot(s) in reports/health/ — "
            "compare summary.fail counts to track wave progress."
        )
    return rc


if __name__ == "__main__":
    sys.exit(main())
