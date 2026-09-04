#!/usr/bin/env python3
"""External verification for F8-C-02 repo-hygiene remediation.

Run from anywhere (resolves the repo root from this file's location):

    loatsNEW\\Scripts\\python.exe scripts\\verify_f8c02_external.py

Checks (12):
 1.  tracked file count <= 415 (ratchet ceiling re-pinned by the F8-M-02
     hygiene follow-up; 411 measured after untracking session-agent files)
 2.  no tracked path under loatsNEW/ (the 9,939-file venv)
 3.  no tracked path under a literal `~/` directory
 4.  no tracked pyvenv.cfg / Scripts/python.exe anywhere
 5.  .env.test untracked, .env.example still tracked
 6.  package.json / package-lock.json / uv.lock / mypy-report/ untracked
 7.  reports/health/ tracks only health-final-*.json
 8.  only the canonical P1 evidence file is tracked
 9.  .gitignore ignores the F8-C-02 classes (live check-ignore probes)
10.  hygiene guard script passes on the live tree (exit 0)
11.  guard wired into CI, pre-commit, and HC-26 (source greps)
12.  TODO-21 verifiers re-baselined to 415 (source grep)

Exit 0 = all checks pass; 1 = failure. ASCII-only output, shell=False,
absolute interpreter paths (Windows-safe per project conventions).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def _resolve_python() -> str:
    candidates = [
        REPO_ROOT / "loatsNEW" / "Scripts" / "python.exe",
        REPO_ROOT / ".venv" / "Scripts" / "python.exe",
    ]
    for cand in candidates:
        if cand.exists():
            return str(cand)
    return sys.executable


PY = _resolve_python()


def _git(*args: str) -> tuple[int, str]:
    proc = subprocess.run(
        ["git", *args], cwd=REPO_ROOT, capture_output=True, text=True, shell=False
    )
    return proc.returncode, proc.stdout


def _tracked() -> list[str]:
    _, out = _git("ls-files")
    return [line for line in out.splitlines() if line.strip()]


def _read(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8", errors="replace")


PASS_SYM, FAIL_SYM = "[PASS]", "[FAIL]"


def main() -> int:
    results: list[tuple[bool, str, str]] = []

    def record(ok: bool, name: str, detail: str = "") -> None:
        results.append((ok, name, detail))

    tracked = _tracked()

    # 1. tracked count ceiling (2026-09-04 re-pin: 429 — TODO-25 gate-
    # integrity wave + F8-L-03 discharge evidence, benchmark artifacts
    # untracked; lockstep with scripts/check_repo_hygiene.py
    # TRACKED_FILE_CEILING and both TODO-21 verifiers)
    record(
        len(tracked) <= 429,
        "1. tracked files <= 429",
        f"count={len(tracked)}",
    )

    # 2. no loatsNEW/
    loats = [p for p in tracked if p.startswith("loatsNEW/")]
    record(not loats, "2. no tracked loatsNEW/ venv", f"found={len(loats)}")

    # 3. no literal ~/
    tilde = [p for p in tracked if p.startswith("~/")]
    record(not tilde, "3. no tracked ~/ junk dir", f"found={len(tilde)}")

    # 4. no pyvenv.cfg / venv interpreter anywhere
    venv_markers = [
        p
        for p in tracked
        if p.endswith(("pyvenv.cfg", "Scripts/python.exe", "Scripts/pythonw.exe"))
    ]
    record(
        not venv_markers,
        "4. no tracked pyvenv.cfg / venv python",
        f"found={len(venv_markers)}",
    )

    # 5. env files
    record(
        ".env.test" not in tracked and ".env.example" in tracked,
        "5. .env.test untracked / .env.example tracked",
        f"env.test={'in' if '.env.test' in tracked else 'out'} "
        f"env.example={'in' if '.env.example' in tracked else 'out'}",
    )

    # 6. tool artifacts
    bad_artifacts = [
        p
        for p in tracked
        if p
        in (
            "package.json",
            "package-lock.json",
            "uv.lock",
            "coverage.json",
        )
        or p.startswith(("mypy-report/", "node_modules/", "htmlcov/"))
    ]
    record(
        not bad_artifacts,
        "6. npm/uv/mypy-report artifacts untracked",
        f"found={len(bad_artifacts)}",
    )

    # 7. reports/health only finals
    health = [p for p in tracked if p.startswith("reports/health/")]
    non_final = [p for p in health if not p.startswith("reports/health/health-final-")]
    record(
        not non_final and bool(health),
        "7. reports/health tracks only health-final-*",
        f"tracked={len(health)} non-final={len(non_final)}",
    )

    # 8. canonical P1 evidence only (2026-09-04: + the F8-L-03 discharge
    # artifact — the genuine 100/100 live TCS round-trip run, whitelisted
    # in .gitignore so HC-29 passes from a fresh clone)
    p1 = [p for p in tracked if p.startswith("reports/p1_analyze_latency_")]
    record(
        p1
        == [
            "reports/p1_analyze_latency_20260828_084822.json",
            "reports/p1_analyze_latency_20260904_040609.json",
        ],
        "8. only canonical P1 evidence tracked",
        f"tracked={p1}",
    )

    # 9. .gitignore live probes
    ignore_ok = True
    ignore_detail = []
    for path in (
        "loatsNEW/Scripts/python.exe",
        "loatsNEW/pyvenv.cfg",
        "~/AppData/Local/x",
        ".env.test",
        "package.json",
        "package-lock.json",
        "uv.lock",
        "mypy-report/index.html",
        "coverage.json",
        "htmlcov/index.html",
        "reports/health/run.json",
    ):
        rc, _ = _git("check-ignore", "-q", path)
        ok = rc == 0
        ignore_ok = ignore_ok and ok
        if not ok:
            ignore_detail.append(path)
    record(
        ignore_ok, "9. .gitignore covers all F8-C-02 classes", f"misses={ignore_detail}"
    )

    # 10. guard passes live
    guard = subprocess.run(
        [PY, str(REPO_ROOT / "scripts" / "check_repo_hygiene.py")],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=60,
        shell=False,
    )
    record(
        guard.returncode == 0,
        "10. hygiene guard passes live tree",
        (guard.stdout.strip().splitlines() or [""])[-1][:90],
    )

    # 11. wiring
    ci = _read(".github/workflows/ci.yml")
    pc = _read(".pre-commit-config.yaml")
    hc = _read("scripts/fr7_health_check.py")
    wired = (
        "check_repo_hygiene.py" in ci
        and "check_repo_hygiene.py" in pc
        and "check_repo_hygiene.py" in hc
    )
    record(
        wired,
        "11. guard wired into CI + pre-commit + HC-26",
        f"ci={'y' if 'check_repo_hygiene.py' in ci else 'n'} "
        f"precommit={'y' if 'check_repo_hygiene.py' in pc else 'n'} "
        f"health={'y' if 'check_repo_hygiene.py' in hc else 'n'}",
    )

    # 12. TODO-21 ratchet re-baseline (kept in lockstep: the TODO-21
    # verifiers and this verifier must pin the same measured count;
    # 2026-09-03 re-pin: 416 — +1 F8-L-03 closure doc)
    t21a = _read("scripts/verify_todo21_external.py")
    t21b = _read("scripts/verify_todo21_root_cleanup.py")
    rebased = "baseline_count = 429" in t21a and "baseline_count = 429" in t21b
    record(rebased, "12. TODO-21 ratchet re-baselined to 429")

    # Summary
    print("=" * 72)
    print("F8-C-02 EXTERNAL VERIFICATION (repo hygiene remediation)")
    print("=" * 72)
    for ok, name, detail in results:
        mark = PASS_SYM if ok else FAIL_SYM
        line = f"{mark} {name}"
        if detail:
            line += f"  [{detail}]"
        print(line)
    passed = sum(1 for ok, _, _ in results if ok)
    print("-" * 72)
    print(f"RESULT: {passed}/{len(results)} checks passed")
    if passed != len(results):
        print("STATUS: FAIL")
        return 1
    print("STATUS: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
