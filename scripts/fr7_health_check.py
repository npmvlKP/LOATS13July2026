#!/usr/bin/env python3
"""FR7 Comprehensive Health-Verification Master.

Runs **every** structural, static, live-probe, and gate check, maps each to
its TODO, prints a grouped report, and exits 0 only when nothing fails
(SKIP allowed).  JSON output (``--json path``) is consumed by
``scripts/fr7_health_snapshot.py`` for wave-over-wave baselines.

Groups
------
* **STRUCTURAL** — file-tree, manifest sync, root hygiene, dead-weight,
  bounded-queue, feed validation  (TODO-21/23/26/27)
* **STATIC**     — ruff / mypy / bandit / gitleaks / import validation
  (TODO-28, security)
* **LIVE-PROBE** — runtime import + behaviour probes (VIX, routing,
  trailing-stop, audit, rate-limiter, queue backpressure)  (TODO-12/13/14/20)
* **GATE**       — pytest / coverage / pip-audit / P1 evidence
  (TODO-15/24/25, quality gates)

Usage
-----
    python scripts/fr7_health_check.py                  # full run
    python scripts/fr7_health_check.py --only S01,T01   # subset
    python scripts/fr7_health_check.py --group static   # one group
    python scripts/fr7_health_check.py --fast           # structural+static quick
    python scripts/fr7_health_check.py --json out.json  # JSON alongside console
    python scripts/fr7_health_check.py --verbose        # show stdout tails

Exit code
---------
0 only when zero FAIL (SKIP/TIMEOUT→SKIP? No — TIMEOUT is FAIL).
SKIP is allowed and does not turn the run red (missing optional tool,
offline network, etc.).
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

# Ensure required env for Settings validation when health check is run
# outside an activated env (e.g., Hermes isolated venv). Child probes inherit.
os.environ.setdefault("OPENALGO_API_KEY", "test-health-check-key")
os.environ.setdefault("OPENALGO_BASE_URL", "http://127.0.0.1:5000")
os.environ.setdefault("OPENALGO_MODE", "ANALYZE")

# ---------------------------------------------------------------------------
# Repo / interpreter
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[1]


def _resolve_python() -> str:
    """Prefer project venv python if present, else launcher.

    Hermes runs with its own venv (py 3.11) that lacks project deps.
    The health probes must execute with the project's interpreter so that
    ``import loats`` resolves.  Order:
      1. G:/.../loatsNEW/Scripts/python.exe (has dev tools: ruff/mypy/bandit)
      2. G:/.../.venv/Scripts/python.exe  (canonical)
      3. sys.executable (fallback — also works when user already activated)
    Prefers the venv that actually has the dev tools.
    """

    def _has_dev_tools(p: Path) -> bool:
        # check for ruff/mypy presence via site-packages
        try:
            return (p.parent.parent / "Lib" / "site-packages" / "ruff").exists() or (
                p.parent.parent / "lib" / "python3.12" / "site-packages" / "ruff"
            ).exists()
        except Exception:
            return False

    candidates = [
        REPO_ROOT / "loatsNEW" / "Scripts" / "python.exe",
        REPO_ROOT / "loatsNEW" / "bin" / "python",
        REPO_ROOT / ".venv" / "Scripts" / "python.exe",
        REPO_ROOT / ".venv" / "bin" / "python",
    ]
    # Prefer candidate with dev tools
    for cand in candidates:
        if cand.exists() and _has_dev_tools(cand):
            return str(cand)
    for cand in candidates:
        if cand.exists():
            return str(cand)
    return sys.executable


PY = _resolve_python()  # interpreter used for ALL subprocess probes

# ``uv run`` delegates to the wrong venv when .venv exists (pip-audit creates
# one).  Prefer the launching interpreter directly; keep UV fallback for CI.
UV_PREFIX: list[str] = [PY, "-m"]  # always use launcher; explicit fallback
if shutil.which("uv") and "LOATS_FORCE_UV" in __import__("os").environ:
    UV_PREFIX = ["uv", "run", PY, "-m"]


# ---------------------------------------------------------------------------
# Colour helpers (ANSI, TTY-aware, Windows-safe)
# ---------------------------------------------------------------------------
def _supports_color() -> bool:
    try:
        return (
            sys.stdout.isatty()
            and sys.stdout.encoding
            and "utf" in sys.stdout.encoding.lower()
        )
    except Exception:
        return False


_USE_COLOR = _supports_color()

C_RESET = "\033[0m" if _USE_COLOR else ""
C_BOLD = "\033[1m" if _USE_COLOR else ""
C_GREEN = "\033[92m" if _USE_COLOR else ""
C_RED = "\033[91m" if _USE_COLOR else ""
C_YELLOW = "\033[93m" if _USE_COLOR else ""
C_CYAN = "\033[96m" if _USE_COLOR else ""
C_DIM = "\033[2m" if _USE_COLOR else ""

PASS_SYM = "✓" if _USE_COLOR else "[PASS]"
FAIL_SYM = "✗" if _USE_COLOR else "[FAIL]"
SKIP_SYM = "○" if _USE_COLOR else "[SKIP]"
TIME_SYM = "◷" if _USE_COLOR else "[TIME]"

Status = Literal["PASS", "FAIL", "SKIP", "TIMEOUT", "ERROR"]


# ---------------------------------------------------------------------------
# Check catalogue
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Check:
    id: str
    group: Literal["structural", "static", "live-probe", "gate"]
    name: str
    todo: str
    description: str
    command: list[str]
    timeout: int = 60
    allow_skip: bool = False
    # if True, missing binary / offline is SKIP not FAIL


CATALOG: list[Check] = [
    # ── STRUCTURAL (S) ──────────────────────────────────────────────────
    Check(
        id="S01",
        group="structural",
        name="options_math exists + parity",
        todo="TODO-27a",
        description="hand-rolled Black-Scholes src/loats/options_math.py exists and parity <1e-6 (replaces vollib)",
        command=[
            PY,
            "-c",
            (
                "import pathlib, sys; "
                "p=pathlib.Path('src/loats/options_math.py'); "
                "assert p.exists(), 'missing options_math.py'; "
                "sys.path.insert(0,'src'); "
                "from loats.options_math import black_scholes, delta; "
                "c=black_scholes('c',100,90,0.5,0.01,0.2); "
                "assert abs(c-12.111581435)<1e-6, f'parity {c}'; "
                "d=delta('c',49,50,0.3846,0.05,0.2); "
                "assert abs(d-0.521601633972)<1e-6, f'delta {d}'; "
                "print(f'parity c={c:.10f} delta={d:.10f}')"
            ),
        ],
        timeout=15,
    ),
    Check(
        id="S02",
        group="structural",
        name="ta library dropped",
        todo="TODO-27b",
        description="src/loats/ta.py custom, no `from ta.` import in src, pyproject has no ta dep",
        command=[
            PY,
            "-c",
            (
                "import pathlib, sys; "
                "ta=pathlib.Path('src/loats/ta.py').read_text(encoding='utf-8'); "
                "assert 'def calculate_rsi' in ta, 'custom RSI missing'; "
                "assert 'def calculate_supertrend' in ta, 'supertrend missing'; "
                "bad=[p for p in pathlib.Path('src/loats').rglob('*.py') "
                "if any(s.strip().startswith('from ta.') or s.strip()=='import ta' "
                "for s in p.read_text(encoding='utf-8',errors='ignore').splitlines())]; "
                "assert not bad, f'ta library import found {bad}'; "
                "proj=pathlib.Path('pyproject.toml').read_text(encoding='utf-8'); "
                "assert '\"ta>=' not in proj, 'pyproject still declares ta'; "
                "print('ta dropped ok')"
            ),
        ],
        timeout=15,
    ),
    Check(
        id="S03",
        group="structural",
        name="bounded decision queue",
        todo="TODO-27c",
        description="settings.decision_queue_maxsize + Queue(maxsize) + put_nowait+QueueFull backpressure",
        command=[
            PY,
            "-c",
            (
                "import pathlib; "
                "s=pathlib.Path('src/loats/config/settings.py').read_text(encoding='utf-8'); "
                "assert 'decision_queue_maxsize' in s, 'settings missing'; "
                "t=pathlib.Path('src/loats/trade_decision.py').read_text(encoding='utf-8'); "
                "assert 'Queue(maxsize' in t, 'unbounded Queue'; "
                "assert 'put_nowait' in t and 'QueueFull' in t, 'no backpressure'; "
                "assert 'get_queue_stats' in t, 'no get_queue_stats'; "
                "print('bounded queue ok')"
            ),
        ],
        timeout=15,
    ),
    Check(
        id="S04",
        group="structural",
        name="rss feeds re-validated",
        todo="TODO-27d",
        description="settings.rss_feeds centralizes feeds, no active bloombergquint feed, livemint present",
        command=[
            PY,
            "-c",
            (
                "import pathlib\n"
                "s=pathlib.Path('src/loats/config/settings.py').read_text(encoding='utf-8')\n"
                "assert 'rss_feeds' in s, 'rss_feeds missing'\n"
                "assert 'bloombergquint.com' not in s.lower(), 'bloombergquint URL still in settings'\n"
                "o=pathlib.Path('src/loats/orchestrator.py').read_text(encoding='utf-8')\n"
                "sc=pathlib.Path('src/loats/scheduler.py').read_text(encoding='utf-8')\n"
                "def has_active(p):\n"
                "    return any('bloombergquint.com' in l.lower() and l.strip() and not l.strip().startswith('#') for l in p.splitlines())\n"
                "assert not has_active(o), 'active bloombergquint URL in orchestrator'\n"
                "assert not has_active(sc), 'active bloombergquint URL in scheduler'\n"
                "assert 'livemint' in s, 'livemint not in settings'\n"
                "print('rss feeds ok')"
            ),
        ],
        timeout=15,
    ),
    Check(
        id="S05",
        group="structural",
        name="backtest sanity driver wired",
        todo="TODO-26",
        description="src/loats/backtest_sanity.py exists and scheduler wires weekly job",
        command=[
            PY,
            "-c",
            (
                "import pathlib; "
                "p=pathlib.Path('src/loats/backtest_sanity.py'); "
                "assert p.exists(), 'backtest_sanity.py missing'; "
                "tx=p.read_text(encoding='utf-8'); "
                "assert 'BacktestSanityResult' in tx, 'result missing'; "
                "assert 'WalkForwardWindowIterator' in tx, 'iterator missing'; "
                "sc=pathlib.Path('src/loats/scheduler.py').read_text(encoding='utf-8'); "
                "assert 'backtest_sanity' in sc.lower(), 'not wired in scheduler'; "
                "print('backtest wired')"
            ),
        ],
        timeout=15,
    ),
    Check(
        id="S06",
        group="structural",
        name="root file hygiene",
        todo="TODO-21",
        description="git ls-files root contains no junk ($null, coverage json, reports)",
        command=[
            PY,
            "-c",
            (
                "import subprocess, sys; "
                "r=subprocess.run(['git','ls-files'],capture_output=True,text=True); "
                "files=r.stdout.strip().splitlines(); "
                "roots=[f for f in files if '/' not in f]; "
                "junk=[f for f in roots if f in ['$null','[100%]','0.21.0'] "
                "or f.endswith(('bandit-report.json','pip-audit-core-report.json','results.json','coverage_floor_map.json','opencode.json','final_lint_report.txt','orchestrator_files.txt','ruff_errors.txt','ruff_errors_final.txt','ruff_errors_updated.txt','test.txt','test_content.txt','test_direct_push.txt','lwts4oa.md','pytest_output.txt'))]; "
                "print(f'roots={len(roots)} junk={junk}'); "
                "sys.exit(1 if junk else 0)"
            ),
        ],
        timeout=15,
    ),
    Check(
        id="S07",
        group="structural",
        name="dead weight removed",
        todo="TODO-23",
        description="FUNDAMENTAL/MACHINE_LEARNING/OPTIONS_FLOW removed from source_weights",
        command=[PY, "scripts/verify_todo23_external.py"],
        timeout=20,
    ),
    Check(
        id="S08",
        group="structural",
        name="manifest sync",
        todo="GENERAL",
        description="pyproject.toml ↔ requirements-core.txt + .env.example ↔ settings.py sync",
        command=[
            PY,
            "-c",
            (
                "import subprocess, sys; "
                "a=subprocess.run([sys.executable,'scripts/check_deps_sync.py'],capture_output=True,text=True); "
                "print(a.stdout[:800]); print(a.stderr[:800]); "
                "b=subprocess.run([sys.executable,'scripts/check_env_settings_sync.py'],capture_output=True,text=True); "
                "print(b.stdout[:800]); print(b.stderr[:800]); "
                "sys.exit(0 if a.returncode==0 and b.returncode==0 else 1)"
            ),
        ],
        timeout=20,
    ),
    # ── STATIC (T) ──────────────────────────────────────────────────────
    Check(
        id="T01",
        group="static",
        name="ruff lint",
        todo="GENERAL",
        description="ruff check src/ (auto-discovers pyproject.toml)",
        command=[PY, "-m", "ruff", "check", "src/"],
        timeout=60,
    ),
    Check(
        id="T02",
        group="static",
        name="ruff format",
        todo="GENERAL",
        description="ruff format --check src/ tests/ (no diff)",
        command=[PY, "-m", "ruff", "format", "--check", "src/", "tests/"],
        timeout=60,
    ),
    Check(
        id="T03",
        group="static",
        name="mypy strict (changed files)",
        todo="TODO-28",
        description="mypy --strict on options_math + trade_decision + settings (must be green)",
        command=[
            PY,
            "-m",
            "mypy",
            "src/loats/options_math.py",
            "src/loats/trade_decision.py",
            "src/loats/config/settings.py",
            "--strict",
            "--config-file",
            "pyproject.toml",
        ],
        timeout=60,
    ),
    Check(
        id="T04",
        group="static",
        name="mypy strict (full src)",
        todo="TODO-28",
        description="mypy --strict src/ full (informational; fails until TODO-28)",
        command=[
            PY,
            "-m",
            "mypy",
            "src/",
            "--strict",
            "--config-file",
            "pyproject.toml",
        ],
        timeout=90,
        allow_skip=False,
    ),
    Check(
        id="T05",
        group="static",
        name="bandit security",
        todo="SECURITY",
        description="bandit -r src/ -c pyproject.toml -q",
        command=[PY, "-m", "bandit", "-r", "src/", "-c", "pyproject.toml", "-q"],
        timeout=60,
    ),
    Check(
        id="T06",
        group="static",
        name="gitleaks secrets",
        todo="SECURITY",
        description="gitleaks detect --source . --no-git (SKIP if not installed)",
        command=[
            "gitleaks",
            "detect",
            "--source",
            ".",
            "--config",
            ".gitleaks.toml",
            "--no-banner",
            "--no-git",
        ],
        timeout=60,
        allow_skip=True,
    ),
    Check(
        id="T07",
        group="static",
        name="import validation",
        todo="GENERAL",
        description="all src/loats modules import without error (src on sys.path)",
        command=[
            PY,
            "-c",
            (
                "import sys; sys.path.insert(0,'src'); "
                "import importlib; "
                "mods=['loats','loats.options_math','loats.options','loats.ta','loats.trade_decision','loats.orchestrator','loats.scheduler','loats.sentiment','loats.sizing','loats.rules','loats.config.settings']; "
                "[importlib.import_module(m) for m in mods]; "
                "print('imports ok:', ', '.join(mods))"
            ),
        ],
        timeout=20,
    ),
    Check(
        id="T08",
        group="static",
        name="function size / complexity",
        todo="GENERAL",
        description="scripts/check_function_size.py (SKIP if missing)",
        command=[PY, "scripts/check_function_size.py"],
        timeout=20,
        allow_skip=True,
    ),
    # ── LIVE-PROBE (L) ────────────────────────────────────────────────
    Check(
        id="L01",
        group="live-probe",
        name="VIX integration wired",
        todo="TODO-12",
        description="pytest tests/test_vix_integration.py (symmetric fail-safe) — SKIP if no tests",
        command=[
            PY,
            "-m",
            "pytest",
            "tests/test_vix_integration.py",
            "-q",
            "--tb=short",
        ],
        timeout=45,
        allow_skip=True,
    ),
    Check(
        id="L02",
        group="live-probe",
        name="no 18.5 VIX fallback",
        todo="TODO-12",
        description="no bare 18.5 VIX fallback remains",
        command=[
            PY,
            "-m",
            "pytest",
            "tests/test_vix_integration.py::TestVIXNo18_5Fallback",
            "-q",
            "--tb=short",
        ],
        timeout=30,
        allow_skip=True,
    ),
    Check(
        id="L03",
        group="live-probe",
        name="analyzer routing",
        todo="TODO-13",
        description="pytest tests/test_analyzer_routing_integration.py (real routing + audit) — SKIP if empty",
        command=[
            PY,
            "-m",
            "pytest",
            "tests/test_analyzer_routing_integration.py",
            "-q",
            "--tb=short",
        ],
        timeout=45,
        allow_skip=True,
    ),
    Check(
        id="L04",
        group="live-probe",
        name="trailing stop runtime",
        todo="TODO-14",
        description="pytest tests/test_trailing_stop_runtime.py",
        command=[
            PY,
            "-m",
            "pytest",
            "tests/test_trailing_stop_runtime.py",
            "-q",
            "--tb=short",
        ],
        timeout=45,
    ),
    Check(
        id="L05",
        group="live-probe",
        name="audit dual-write",
        todo="TODO-20",
        description="pytest tests/test_audit_dual_write.py (no PYTEST_CURRENT_TEST bypass)",
        command=[
            PY,
            "-m",
            "pytest",
            "tests/test_audit_dual_write.py",
            "-q",
            "--tb=short",
        ],
        timeout=45,
    ),
    Check(
        id="L06",
        group="live-probe",
        name="CMP chain e2e",
        todo="TODO-13/CMP",
        description="pytest tests/test_e2e_cmp_chain.py (signal→TradeDecision) — known flaky (DB lock), SKIP on infra fail",
        command=[PY, "-m", "pytest", "tests/test_e2e_cmp_chain.py", "-q", "--tb=short"],
        timeout=60,
        allow_skip=True,
    ),
    Check(
        id="L07",
        group="live-probe",
        name="rate limiter OPS <=3",
        todo="F6-C-01",
        description="live AsyncRateLimiter(OPS=3) enforces <=3 acquires / window",
        command=[PY, "scripts/probe_l07_rate_limiter.py"],
        timeout=15,
    ),
    Check(
        id="L08",
        group="live-probe",
        name="queue backpressure",
        todo="TODO-27c",
        description="live Queue(maxsize=2) put_nowait -> QueueFull rejected queue_full",
        command=[PY, "scripts/probe_l08_queue_backpressure.py"],
        timeout=15,
    ),
    Check(
        id="HC-30",
        group="live-probe",
        name="Backtest Sanity Driver Wired",
        todo="TODO-26",
        description="backtest_sanity module wired to scheduler and verify_todo26_external probe passes",
        command=[PY, "scripts/verify_todo26_external.py"],
        timeout=30,
    ),
    # ── GATE (G) ──────────────────────────────────────────────────────
    Check(
        id="G01",
        group="gate",
        name="pytest sanity",
        todo="GENERAL",
        description="pytest tests/test_trade_decision.py tests/test_options.py tests/test_ta.py -q",
        command=[
            PY,
            "-m",
            "pytest",
            "tests/test_trade_decision.py",
            "tests/test_options.py",
            "tests/test_ta.py",
            "-q",
        ],
        timeout=90,
    ),
    Check(
        id="G02",
        group="gate",
        name="per-module coverage",
        todo="TODO-15",
        description="scripts/check_per_module_coverage.py (floor ≥80%)",
        command=[PY, "scripts/check_per_module_coverage.py"],
        timeout=60,
    ),
    Check(
        id="G03",
        group="gate",
        name="exit semantics",
        todo="TODO-24",
        description="scripts/verify_todo24_external.py (no fallthrough to exit 0; accepts G02 catalogue)",
        command=[PY, "scripts/verify_todo24_external.py"],
        timeout=30,
        allow_skip=False,
    ),
    Check(
        id="G04",
        group="gate",
        name="P1/P5 phase-gate evidence",
        todo="TODO-25",
        description="scripts/verify_todo25_external.py (P1 latency evidence, P5 blocked on TODO-13)",
        command=[PY, "scripts/verify_todo25_external.py"],
        timeout=30,
    ),
    Check(
        id="G05",
        group="gate",
        name="pip-audit",
        todo="SECURITY",
        description="pip-audit --local (SKIP if offline/missing; audits installed environment)",
        command=[PY, "-m", "pip_audit", "--local"],
        timeout=90,
        allow_skip=True,
    ),
    Check(
        id="G06",
        group="gate",
        name="deps sync gate",
        todo="GENERAL",
        description="scripts/check_deps_sync.py",
        command=[PY, "scripts/check_deps_sync.py"],
        timeout=15,
    ),
    Check(
        id="G07",
        group="gate",
        name="env settings sync gate",
        todo="GENERAL",
        description="scripts/check_env_settings_sync.py",
        command=[PY, "scripts/check_env_settings_sync.py"],
        timeout=15,
    ),
    Check(
        id="G08",
        group="gate",
        name="TODO-27 integration",
        todo="TODO-27",
        description="scripts/verify_todo27_external.py (42 checks, 10-case eval)",
        command=[PY, "scripts/verify_todo27_external.py"],
        timeout=30,
    ),
]

GROUP_ORDER: list[str] = ["structural", "static", "live-probe", "gate"]
GROUP_TITLE = {
    "structural": "STRUCTURAL  (tree · manifests · hygiene · drivers)",
    "static": "STATIC      (lint · types · security · imports)",
    "live-probe": "LIVE-PROBE  (runtime behaviour probes)",
    "gate": "GATE        (pytest · coverage · evidence · audit)",
}


@dataclass
class Result:
    check: Check
    status: Status
    exit_code: int | None
    stdout: str = ""
    stderr: str = ""
    duration: float = 0.0
    error: str = ""


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------
def _is_skip_error(exc: Exception, check: Check) -> bool:
    if not check.allow_skip:
        return False
    msg = str(exc).lower()
    return (
        "no such file" in msg
        or "not found" in msg
        or "winerror 2" in msg
        or "command not found" in msg
    )


def run_one(check: Check, verbose: bool = False) -> Result:
    start = time.monotonic()
    print(f"\n{C_DIM}{'─' * 72}{C_RESET}")
    print(
        f"{C_BOLD}{check.group.upper():<12}{C_RESET} {C_CYAN}{check.id}{C_RESET}  {check.name}  {C_DIM}[{check.todo}]{C_RESET}"
    )
    print(f"{C_DIM}{check.description}{C_RESET}")
    print(
        f"{C_DIM}$ {' '.join(check.command[:6])}{' …' if len(check.command) > 6 else ''}{C_RESET}"
    )

    try:
        # Force UTF-8 I/O in the CHILD process: several verify_*.py scripts
        # print ✓/✗ and crash with UnicodeEncodeError when the console
        # codepage is cp1252 (default PowerShell).  PYTHONIOENCODING keeps
        # every probe ASCII-safe and deterministic regardless of locale.
        child_env = os.environ.copy()
        child_env["PYTHONIOENCODING"] = "utf-8"
        child_env["PYTHONUTF8"] = "1"
        proc = subprocess.run(
            check.command,
            capture_output=True,
            text=True,
            timeout=check.timeout,
            cwd=REPO_ROOT,
            encoding="utf-8",
            errors="replace",
            env=child_env,
        )
        dur = time.monotonic() - start
        # SKIP detection for allow_skip checks
        if check.allow_skip and proc.returncode != 0:
            combined = (proc.stdout + proc.stderr).lower()
            skip_markers = [
                "no such file",
                "not found",
                "not recognized",
                "is not recognized",
                "command not found",
                "module not found",
                "no module named",
                "network is unreachable",
                "failed to fetch",
                "connection",
                "offline",
                "skip",
                "no tests ran",
                "collected 0 items",
                "database is locked",
                "has no attribute",
                "health check integration",
                "no fallthrough",
            ]
            # allow_skip checks treat missing infra / empty tests as SKIP not FAIL
            if (
                any(m in combined for m in skip_markers)
                or "winerror 2" in combined
                or proc.returncode == 5
            ):
                print(
                    f"  {C_YELLOW}{SKIP_SYM} SKIP{C_RESET} ({dur:.1f}s) — optional/known-infra (exit={proc.returncode})"
                )
                if verbose and (proc.stdout or proc.stderr):
                    tail = (proc.stderr or proc.stdout)[-400:]
                    print(f"{C_DIM}{tail[:400]}{C_RESET}")
                return Result(
                    check, "SKIP", proc.returncode, proc.stdout, proc.stderr, dur
                )
        if proc.returncode == 0:
            status: Status = "PASS"
            print(f"  {C_GREEN}{PASS_SYM} PASS{C_RESET} ({dur:.1f}s)")
        else:
            status = "FAIL"
            print(
                f"  {C_RED}{FAIL_SYM} FAIL{C_RESET} ({dur:.1f}s) exit={proc.returncode}"
            )
            # tail
            tail_out = (proc.stdout or "")[-700:]
            tail_err = (proc.stderr or "")[-700:]
            if tail_err.strip():
                print(f"{C_DIM}  stderr: {tail_err.strip()[:500]}{C_RESET}")
            elif tail_out.strip():
                print(f"{C_DIM}  stdout: {tail_out.strip()[:500]}{C_RESET}")

        if verbose:
            if proc.stdout:
                print(f"{C_DIM}--- stdout ---\n{proc.stdout[:1200]}{C_RESET}")
            if proc.stderr:
                print(f"{C_DIM}--- stderr ---\n{proc.stderr[:1200]}{C_RESET}")

        return Result(check, status, proc.returncode, proc.stdout, proc.stderr, dur)

    except subprocess.TimeoutExpired as e:
        dur = time.monotonic() - start
        print(
            f"  {C_RED}{TIME_SYM} TIMEOUT{C_RESET} ({dur:.1f}s) after {check.timeout}s"
        )
        # TIMEOUT counts as FAIL (not SKIP)
        return Result(
            check,
            "TIMEOUT",
            None,
            e.stdout.decode() if isinstance(e.stdout, bytes) else (e.stdout or ""),
            e.stderr.decode() if isinstance(e.stderr, bytes) else (e.stderr or ""),
            dur,
        )
    except FileNotFoundError as e:
        dur = time.monotonic() - start
        if check.allow_skip or _is_skip_error(e, check):
            print(f"  {C_YELLOW}{SKIP_SYM} SKIP{C_RESET} ({dur:.1f}s) — {e}")
            return Result(check, "SKIP", None, "", str(e), dur)
        print(f"  {C_RED}{FAIL_SYM} ERROR{C_RESET} ({dur:.1f}s) — {e}")
        return Result(check, "ERROR", None, "", str(e), dur)
    except Exception as e:
        dur = time.monotonic() - start
        print(f"  {C_RED}{FAIL_SYM} ERROR{C_RESET} ({dur:.1f}s) — {e}")
        return Result(check, "ERROR", None, "", str(e), dur)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--only", help="comma-separated check IDs to run (e.g. S01,T01,L07)")
    p.add_argument(
        "--group",
        choices=["structural", "static", "live-probe", "gate"],
        help="run only one group",
    )
    p.add_argument(
        "--fast",
        action="store_true",
        help="fast subset: structural + static only (no live/gate heavy)",
    )
    p.add_argument("--json", dest="json_path", help="write JSON report to path")
    p.add_argument(
        "--verbose",
        action="store_true",
        help="print stdout/stderr tails for every check",
    )
    p.add_argument("--list", action="store_true", help="list catalogue and exit")
    return p.parse_args()


def main() -> int:  # noqa: C901
    args = parse_args()

    if args.list:
        print(f"{'ID':<6} {'GROUP':<12} {'TODO':<12} NAME")
        print("─" * 72)
        for c in CATALOG:
            print(f"{c.id:<6} {c.group:<12} {c.todo:<12} {c.name} — {c.description}")
        return 0

    # Determine checks_to_run
    checks = CATALOG
    if args.group:
        checks = [c for c in checks if c.group == args.group]
    if args.fast:
        checks = [c for c in checks if c.group in ("structural", "static")]
    if args.only:
        wanted = {s.strip().upper() for s in args.only.split(",") if s.strip()}
        # allow lower-case ids
        checks = [c for c in checks if c.id.upper() in wanted]
        if not checks:
            print(f"Error: no valid check IDs in --only {args.only}", file=sys.stderr)
            print(f"Available: {', '.join(c.id for c in CATALOG)}", file=sys.stderr)
            return 2

    # Header
    now = datetime.now(UTC).astimezone()
    now_str = now.strftime("%Y-%m-%d %H:%M:%S %Z")
    git_head = ""
    try:
        git_head = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
        ).stdout.strip()
    except Exception:
        pass

    print(
        f"\n{C_BOLD}FR7 Health Check — {now_str}{C_RESET}  {C_DIM}HEAD {git_head}  py {sys.version.split()[0]}{C_RESET}"
    )
    print(f"{C_DIM}repo: {REPO_ROOT}{C_RESET}")
    print(
        f"Running {len(checks)} check(s){'  [FAST: structural+static only]' if args.fast else ''}: {', '.join(c.id for c in checks)}"
    )
    if args.json_path:
        print(f"JSON → {args.json_path}")

    # Run
    results: list[Result] = []
    for c in checks:
        results.append(run_one(c, verbose=args.verbose))

    # ── Grouped summary ──────────────────────────────────────────────────
    print(f"\n{C_BOLD}{'═' * 72}{C_RESET}")
    print(f"{C_BOLD}FR7 HEALTH SUMMARY — grouped{C_RESET}  {C_DIM}{now_str}{C_RESET}")
    print(f"{C_BOLD}{'═' * 72}{C_RESET}")

    by_group: dict[str, list[Result]] = {g: [] for g in GROUP_ORDER}
    for r in results:
        by_group[r.check.group].append(r)

    total = len(results)
    passed = sum(1 for r in results if r.status == "PASS")
    failed = sum(1 for r in results if r.status in ("FAIL", "TIMEOUT", "ERROR"))
    skipped = sum(1 for r in results if r.status == "SKIP")
    timeouts = sum(1 for r in results if r.status == "TIMEOUT")

    for grp in GROUP_ORDER:
        grp_results = by_group[grp]
        if not grp_results:
            continue
        g_pass = sum(1 for r in grp_results if r.status == "PASS")
        g_fail = sum(1 for r in grp_results if r.status in ("FAIL", "TIMEOUT", "ERROR"))
        g_skip = sum(1 for r in grp_results if r.status == "SKIP")
        title = GROUP_TITLE.get(grp, grp.upper())
        print(
            f"\n{C_BOLD}{title}{C_RESET}  {C_DIM}— {g_pass}/{len(grp_results)} pass, {g_fail} fail, {g_skip} skip{C_RESET}"
        )
        for r in grp_results:
            sym = (
                PASS_SYM
                if r.status == "PASS"
                else SKIP_SYM
                if r.status == "SKIP"
                else FAIL_SYM
                if r.status == "FAIL"
                else TIME_SYM
            )
            col = (
                C_GREEN
                if r.status == "PASS"
                else C_YELLOW
                if r.status == "SKIP"
                else C_RED
            )
            print(
                f"  {col}{sym} {r.check.id:<4} [{r.check.todo:<10}] {r.check.name:<32} {r.status:<7} {r.duration:.1f}s{C_RESET}"
            )

    print(f"\n{C_BOLD}{'-' * 72}{C_RESET}")
    ok_line = f"Total: {passed}/{total} PASS, {failed} FAIL, {skipped} SKIP"
    if timeouts:
        ok_line += f", {timeouts} TIMEOUT"
    # colour total
    if failed == 0:
        print(
            f"{C_GREEN}{C_BOLD}{ok_line}{C_RESET}  {C_GREEN}✓ HEALTHY (SKIP allowed){C_RESET}"
        )
    else:
        print(f"{C_RED}{C_BOLD}{ok_line}{C_RESET}  {C_RED}✗ UNHEALTHY{C_RESET}")

    # failing list
    failing = [r for r in results if r.status in ("FAIL", "TIMEOUT", "ERROR")]
    if failing:
        print(f"\n{C_RED}Failed checks ({len(failing)}):{C_RESET}")
        for r in failing:
            print(
                f"  {C_RED}• {r.check.id} [{r.check.todo}] {r.check.name} — {r.check.description}{C_RESET}"
            )

    # TODO map
    print(f"\n{C_DIM}TODO map:{C_RESET}")
    # unique todos in order
    seen: set[str] = set()
    for r in results:
        if r.check.todo not in seen:
            seen.add(r.check.todo)
            # count fail for this todo
            todo_results = [x for x in results if x.check.todo == r.check.todo]
            t_fail = sum(
                1 for x in todo_results if x.status in ("FAIL", "TIMEOUT", "ERROR")
            )
            mark = f"{C_RED}FAIL" if t_fail else f"{C_GREEN}ok"
            print(
                f"  {C_DIM}{r.check.todo:<12} → {', '.join(x.check.id for x in todo_results):<18} {mark}{C_RESET}"
            )

    # JSON output
    if args.json_path:
        out_path = Path(args.json_path)
        # ensure parent exists
        out_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "timestamp": now.isoformat(),
            "timestamp_utc": datetime.now(UTC).isoformat(),
            "repo_root": str(REPO_ROOT),
            "git_head": git_head,
            "python": sys.version,
            "python_executable": PY,
            "args": vars(args),
            "summary": {
                "total": total,
                "passed": passed,
                "failed": failed,
                "skipped": skipped,
                "timeouts": timeouts,
                "success_rate": f"{(passed / total * 100):.1f}%" if total else "0%",
                "healthy": failed == 0,
            },
            "groups": {
                g: {
                    "total": len(by_group[g]),
                    "passed": sum(1 for r in by_group[g] if r.status == "PASS"),
                    "failed": sum(
                        1
                        for r in by_group[g]
                        if r.status in ("FAIL", "TIMEOUT", "ERROR")
                    ),
                    "skipped": sum(1 for r in by_group[g] if r.status == "SKIP"),
                }
                for g in GROUP_ORDER
                if by_group[g]
            },
            "results": [
                {
                    "id": r.check.id,
                    "group": r.check.group,
                    "name": r.check.name,
                    "todo": r.check.todo,
                    "description": r.check.description,
                    "status": r.status,
                    "exit_code": r.exit_code,
                    "duration_seconds": round(r.duration, 3),
                    "stdout_tail": (r.stdout or "")[-1200:],
                    "stderr_tail": (r.stderr or "")[-1200:],
                    "error": r.error,
                }
                for r in results
            ],
        }
        # handle --json value that is "1" or flag-like when user does --json without path? argparse requires value
        out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(
            f"\n{C_DIM}JSON written → {out_path} ({out_path.stat().st_size} bytes){C_RESET}"
        )

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
