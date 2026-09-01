#!/usr/bin/env python
"""FR7 consolidated health check — LOATS13July2026 build-wave verification.

Derived from 23Aug2026-Consolidated FR.md (FR7 + FR7-R, HEAD 163cdf9).
Each check maps to a TODO in 23Aug2026-FR Sequential TODOs.md.

Exit codes: 0 = no failures (SKIP allowed); 1 = one or more FAIL;
            2 = usage error. ASCII-only output by design.
"""

from __future__ import annotations

import argparse
import ast
import asyncio
import inspect
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "src"
LOATS = SRC / "loats"

# F7-M-03 mitigation: eager module-level settings in up to 11 modules make
# imports crash without OPENALGO_API_KEY. Set a dummy BEFORE importing loats
# and report it (HC-21 fails until TODO-18 lands).
_ENV_INJECTED = False
if not os.environ.get("OPENALGO_API_KEY"):
    os.environ["OPENALGO_API_KEY"] = "fr7-health-probe"
    _ENV_INJECTED = True

# ---------------------------------------------------------------- report ----


@dataclass
class Result:
    check_id: str
    name: str
    todo: str
    status: str  # PASS | FAIL | SKIP
    detail: str = ""
    evidence: list = field(default_factory=list)


class Report:
    def __init__(self) -> None:
        self.results: list[Result] = []
        self.t0 = time.time()

    def add(self, r: Result) -> None:
        self.results.append(r)
        mark = {"PASS": "[PASS]", "FAIL": "[FAIL]", "SKIP": "[SKIP]"}[r.status]
        print(f"{mark} {r.check_id:<7} ({r.todo:<10}) {r.name}")
        if r.detail:
            print(f"         {r.detail}")
        for line in r.evidence[:8]:
            print(f"         - {line}")
        if len(r.evidence) > 8:
            print(f"         - ... +{len(r.evidence) - 8} more")

    def summary(self) -> int:
        p = sum(1 for r in self.results if r.status == "PASS")
        f = sum(1 for r in self.results if r.status == "FAIL")
        s = sum(1 for r in self.results if r.status == "SKIP")
        print("\n" + "=" * 72)
        print(
            f"HEALTH SUMMARY: {p} PASS / {f} FAIL / {s} SKIP "
            f"in {time.time() - self.t0:.1f}s"
        )
        if f:
            print("Failing checks (by TODO):")
            for r in self.results:
                if r.status == "FAIL":
                    print(f"  {r.check_id:<7} {r.todo:<10} {r.name}")
        print("=" * 72)
        return 1 if f else 0

    def to_json(self) -> dict:
        return {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "python": sys.version.split()[0],
            "env_key_injected": _ENV_INJECTED,
            "results": [vars(r) for r in self.results],
            "summary": {
                "pass": sum(1 for r in self.results if r.status == "PASS"),
                "fail": sum(1 for r in self.results if r.status == "FAIL"),
                "skip": sum(1 for r in self.results if r.status == "SKIP"),
            },
        }


# ------------------------------------------------------ filesystem checks ----


def check_structure(rep: Report) -> None:
    # HC-01
    init = SRC / "__init__.py"
    rep.add(
        Result(
            "HC-01",
            "src/__init__.py absent (mypy collision breaker)",
            "TODO-1",
            "PASS" if not init.exists() else "FAIL",
            "mypy strict gate cannot run while src is a package"
            if init.exists()
            else "",
        )
    )

    # HC-02 — strays directly under src/ (anything except the loats/ dir)
    strays = sorted(p.name for p in SRC.glob("*.py"))
    rep.add(
        Result(
            "HC-02",
            "no stray .py files directly in src/",
            "TODO-2",
            "PASS" if not strays else "FAIL",
            f"{len(strays)} stray file(s) break mypy pathing" if strays else "",
            strays,
        )
    )

    # HC-03 — empty CMP-named shells
    shells = []
    for rel in ("connectors", "risk", "risk/manager", "strategy", "strategy/rules"):
        d = LOATS / rel
        if d.is_dir():
            py = list(d.rglob("*.py"))
            non_init = [p for p in py if p.name != "__init__.py"]
            if not non_init and all(p.stat().st_size < 512 for p in py):
                shells.append(rel)
    rep.add(
        Result(
            "HC-03",
            "no empty CMP-named package shells",
            "TODO-2",
            "PASS" if not shells else "FAIL",
            "structure theater" if shells else "",
            shells,
        )
    )

    # HC-26 — root junk artifacts (FR-26 forbidden root names)
    forbidden = (
        "-p",
        "G......",
        "0.21.0",
        "$null",
        "[100%]",
        "tmp_schema.db",
        "pytest_output.txt",
    )
    junk = [n for n in forbidden if (REPO_ROOT / n).exists()]
    rep.add(
        Result(
            "HC-26",
            "root junk artifacts absent",
            "TODO-21",
            "PASS" if not junk else "FAIL",
            "tracked junk at repo root" if junk else "",
            junk,
        )
    )


# ---------------------------------------------------------- static AST -------


def _is_test_file(p: Path) -> bool:
    return "tests" in p.parts or p.stem.startswith("test_") or p.stem == "conftest"


def _iter_py(exclude_tests: bool = True):
    for p in LOATS.rglob("*.py"):
        rel = p.relative_to(REPO_ROOT).as_posix()
        if rel.startswith("src/loats/config/"):
            continue
        if exclude_tests and _is_test_file(p):
            continue
        yield p


def _parse(p: Path):
    try:
        return ast.parse(p.read_text(encoding="utf-8"), filename=str(p))
    except SyntaxError:
        return None


def _find_attr_callers(attr_name: str, skip_files: tuple[str, ...] = ()):
    """Production call sites of `*.attr_name(...)` under src/loats (no tests)."""
    hits = []
    for p in _iter_py():
        if p.name in skip_files:
            continue
        tree = _parse(p)
        if tree is None:
            continue
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == attr_name
            ):
                hits.append(f"{p.relative_to(REPO_ROOT).as_posix()}:{node.lineno}")
    return hits


def check_eager_settings(rep: Report) -> None:
    """HC-21 — eager module-level `settings = get_settings()` (Assign or AnnAssign)."""
    offenders = []
    for p in _iter_py():
        tree = _parse(p)
        if tree is None:
            continue
        for node in tree.body:  # module level only
            if isinstance(node, ast.Assign):
                call = node.value
            elif isinstance(node, ast.AnnAssign) and node.value is not None:
                call = node.value  # `settings: Settings = get_settings()`
            else:
                continue
            if (
                isinstance(call, ast.Call)
                and isinstance(call.func, ast.Name)
                and call.func.id == "get_settings"
            ):
                offenders.append(f"{p.relative_to(REPO_ROOT).as_posix()}:{node.lineno}")
    rep.add(
        Result(
            "HC-21",
            "no module-level eager get_settings() (lazy access)",
            "TODO-18",
            "PASS" if not offenders else "FAIL",
            f"{len(offenders)} module(s) crash import without OPENALGO_API_KEY"
            if offenders
            else "",
            offenders,
        )
    )


def check_wiring(rep: Report) -> None:
    """HC-18 / HC-20 — runtime drivers wired (VIX setter, trailing ratchet)."""
    callers = _find_attr_callers("set_vix_level", skip_files=("rules.py",))
    rep.add(
        Result(
            "HC-18",
            "set_vix_level has >=1 production caller",
            "TODO-12",
            "PASS" if callers else "FAIL",
            "VIX gate runs on fallback constant — decorative" if not callers else "",
            callers,
        )
    )

    drivers = _find_attr_callers(
        "update_trailing_stop", skip_files=("trailing_stop.py",)
    )
    rep.add(
        Result(
            "HC-20",
            "update_trailing_stop has >=1 production caller",
            "TODO-14",
            "PASS" if drivers else "FAIL",
            "ratchet initialized but never driven (Rule 12 dormant)"
            if not drivers
            else "",
            drivers,
        )
    )


def check_decision_code(rep: Report) -> None:
    """HC-17 / HC-19 / HC-22 / HC-24 / HC-25 / HC-27 — decision-layer conformance."""
    # HC-22 — audit bypass
    db = LOATS / "database.py"
    bypass = db.exists() and "PYTEST_CURRENT_TEST" in db.read_text(encoding="utf-8")
    rep.add(
        Result(
            "HC-22",
            "no PYTEST_CURRENT_TEST bypass in database.py",
            "TODO-20",
            "FAIL" if bypass else "PASS",
            "JSONL-first dual-write untested by suite" if bypass else "",
        )
    )

    # HC-17 — untagged orchestrator source metadata
    orch = LOATS / "orchestrator.py"
    n = (
        orch.read_text(encoding="utf-8").count('"source": "orchestrator"')
        if orch.exists()
        else -1
    )
    rep.add(
        Result(
            "HC-17",
            'zero "source": "orchestrator" tags in orchestrator.py',
            "TODO-7",
            "PASS" if n == 0 else "FAIL",
            f"{n} occurrence(s): Gate 1 sees 1 unique source, chain dead" if n else "",
        )
    )

    # HC-19 — routing stub detection in trade_decision.py
    td = LOATS / "trade_decision.py"
    sim_sleep, default_on, integrates = False, False, False
    if td.exists():
        tree = _parse(td)
        text = td.read_text(encoding="utf-8")
        # Detect default-on: assignment to True at module or class scope only.
        # Explicit `enable_analyzer_routing(self)` instance toggles inside a
        # function body are legitimate and must be ignored. AST scope checking is
        # used because regex context is too fragile to distinguish them.
        default_on = False
        if tree is not None:
            # Build parent map so we can tell whether an assignment is inside a function
            parent_map = {}
            for parent in ast.walk(tree):
                for child in ast.iter_child_nodes(parent):
                    parent_map[child] = parent
            for node in ast.walk(tree):
                if not isinstance(node, (ast.Assign, ast.AnnAssign)):
                    continue
                # Reject any assignment inside a function/async def body.
                parent = parent_map.get(node)
                inside_func = False
                while parent is not None:
                    if isinstance(parent, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        inside_func = True
                        break
                    parent = parent_map.get(parent)
                if inside_func:
                    continue
                # Determine target name.
                target = None
                if isinstance(node, ast.AnnAssign):
                    target = node.target
                else:
                    for t in node.targets:
                        if (
                            isinstance(t, ast.Name)
                            and t.id == "analyzer_routing_enabled"
                        ):
                            target = t
                            break
                        if (
                            isinstance(t, ast.Attribute)
                            and t.attr == "analyzer_routing_enabled"
                        ):
                            target = t
                            break
                if target is None:
                    continue
                if isinstance(node.value, ast.Constant) and node.value.value is True:
                    default_on = True
                    break

            for node in ast.walk(tree):
                if isinstance(node, ast.AsyncFunctionDef) and (
                    node.name == "route_to_analyzer"
                ):
                    body_src = ast.get_source_segment(text, node) or ""
                    # Only actual `await asyncio.sleep(...)` calls count as simulation,
                    # not docstring mentions or exception-loop backoff elsewhere.
                    sim_sleep = bool(
                        re.search(r"await\s+asyncio\.sleep\s*\(", body_src)
                    )
                    integrates = bool(
                        re.search(
                            r"client|openalgo|httpx|place_analyzer", body_src, re.I
                        )
                    )
        ok = (not sim_sleep) and (not default_on) and integrates
    else:
        ok = False
    rep.add(
        Result(
            "HC-19",
            "Analyzer routing real (no sim-sleep, default-off, integration)",
            "TODO-13",
            "PASS" if ok else "FAIL",
            f"sleep-sim={sim_sleep}, default_on={default_on}, integrated={integrates}",
        )
    )

    # HC-24 — rules thresholds
    rules = LOATS / "rules.py"
    buy_iv = sell_iv = None
    if rules.exists():
        text = rules.read_text(encoding="utf-8")
        m = re.search(r"iv_rank\s*<\s*(\d+)", text)
        buy_iv = int(m.group(1)) if m else None
        m = re.search(r"iv_rank\s*>\s*(\d+)", text)
        sell_iv = int(m.group(1)) if m else None
    rep.add(
        Result(
            "HC-24",
            "IV-rank thresholds BUY<30 / SELL>40 (CMP)",
            "TODO-16",
            "PASS" if buy_iv == 30 and sell_iv == 40 else "FAIL",
            f"found BUY<{buy_iv} / SELL>{sell_iv} — CMP says <30 / >40",
        )
    )

    # HC-25 — bare 18.5 VIX fallback
    has_fallback = rules.exists() and re.search(
        r"18\.5", rules.read_text(encoding="utf-8")
    )
    rep.add(
        Result(
            "HC-25",
            "no bare 18.5 VIX fallback (symmetric fail-safe)",
            "TODO-12",
            "FAIL" if has_fallback else "PASS",
            "fallback biases BUY/SELL gating — wire real VIX (TODO-12)"
            if has_fallback
            else "",
        )
    )

    # HC-27 — decision queue bounded
    td_text = td.read_text(encoding="utf-8") if td.exists() else ""
    m = re.search(r"asyncio\.Queue\(([^)]*)\)", td_text)
    bounded = bool(m and m.group(1).strip())  # non-empty args => maxsize present
    rep.add(
        Result(
            "HC-27",
            "decision queue bounded (maxsize set)",
            "TODO-27c",
            "PASS" if bounded else "FAIL",
            "unbounded queue + lazy processor = unbounded memory"
            if not bounded
            else "",
        )
    )


# ---------------------------------------------------------- live probes ------


def _norm(v):
    """Normalize validate_signal_sources return to (bool, reason-ish)."""
    if isinstance(v, tuple) and v:
        ok = bool(v[0])
        info = v[1] if len(v) > 1 else {}
        if isinstance(info, dict):
            reason = info.get("reason", json.dumps(info)[:120])
        else:
            reason = str(info)[:120]
        return ok, reason
    return bool(v), ""


def _sig(sources: list[str]):
    return [
        SimpleNamespace(metadata={"source": s, "scan_type": "probe"}) for s in sources
    ]


def probe_strength_gate(rep: Report) -> None:
    """HC-15 / HC-16 — drive the source gates directly (gate-math regression net)."""
    try:
        import loats.strength as st
    except Exception as exc:  # pragma: no cover
        rep.add(
            Result(
                "HC-15",
                "strength-gate math probe",
                "TODO-8",
                "SKIP",
                f"import failed: {exc!r}",
            )
        )
        rep.add(
            Result(
                "HC-16",
                "unknown-source loud rejection",
                "TODO-9",
                "SKIP",
                "loats.strength unimportable",
            )
        )
        return

    engine = None
    for name in ("StrengthEngine", "CompositeStrengthEngine", "get_strength_engine"):
        obj = getattr(st, name, None)
        if obj is None:
            continue
        engine = obj() if callable(obj) else obj
        break
    fn = getattr(engine, "validate_signal_sources", None) or getattr(
        st, "validate_signal_sources", None
    )
    if fn is None:
        rep.add(
            Result(
                "HC-15",
                "strength-gate math probe",
                "TODO-8",
                "SKIP",
                "validate_signal_sources not found",
            )
        )
        rep.add(
            Result(
                "HC-16",
                "unknown-source loud rejection",
                "TODO-9",
                "SKIP",
                "validator not found",
            )
        )
        return

    def call(srcs):
        try:
            return _norm(fn(_sig(srcs)))
        except Exception as exc:
            return False, f"probe error: {exc!r}"

    three = call(["ta", "sentiment", "price_action"])
    four = call(["ta", "sentiment", "price_action", "volatility"])
    ok15 = (three[0] is False) and (four[0] is True)
    rep.add(
        Result(
            "HC-15",
            "source-gate math: 3 distinct -> reject, 4 -> pass",
            "TODO-8",
            "PASS" if ok15 else "FAIL",
            f"3-src={three[1]} | 4-src={four[1]}",
            [
                f"3 distinct sources accepted: {three[0]} (expect False — diversity 0.4286)",
                f"4 distinct sources accepted: {four[0]} (expect True — diversity 0.5714)",
            ],
        )
    )

    bogus = call(["banana", "ta", "sentiment", "price_action"])
    loud = (bogus[0] is False) and (
        "unknown" in bogus[1].lower() or "invalid" in bogus[1].lower()
    )
    rep.add(
        Result(
            "HC-16",
            "unknown source string loudly rejected",
            "TODO-9",
            "PASS" if loud else "FAIL",
            f"reason: {bogus[1]} — expected explicit unknown/invalid rejection;"
            " silent TECHNICAL_ANALYSIS collapse fails this check",
        )
    )


def probe_rate_limiter(rep: Report) -> None:
    """HC-14 — F6-C-01 regression net: singleton, max_ops=3, burst 3/10."""
    try:
        from loats.openalgo import (
            get_order_rate_limiter,
            get_smart_order_rate_limiter,
        )
    except Exception as exc:
        rep.add(
            Result(
                "HC-14",
                "OPS limiter probe (<=3/s, singleton)",
                "F6-C-01",
                "SKIP",
                f"import failed: {exc!r}",
            )
        )
        return

    async def burst(lim, n=10):
        passed = 0
        for _ in range(n):
            r = lim.acquire()
            if inspect.iscoroutine(r):
                r = await r
            if r:
                passed += 1
        return passed

    try:
        a, b = get_order_rate_limiter(), get_order_rate_limiter()
        smart = get_smart_order_rate_limiter()
        ident = a is b
        eff = getattr(a, "max_ops", None)
        if eff is None:
            eff = getattr(a, "_max_ops", None)
        try:
            from loats.config import get_settings

            cfg = get_settings().max_ops
        except Exception:
            cfg = None
        ordn = asyncio.run(burst(a))
        smartn = asyncio.run(burst(smart))
        ok = ident and eff == 3 and cfg == 3 and ordn == 3 and smartn == 3
        rep.add(
            Result(
                "HC-14",
                "OPS limiter: singleton, max_ops=3, 3/10 burst",
                "F6-C-01",
                "PASS" if ok else "FAIL",
                f"identity={ident} effective={eff} settings={cfg} "
                f"order={ordn}/10 smart={smartn}/10 (expect 3)",
            )
        )
    except Exception as exc:
        rep.add(
            Result(
                "HC-14",
                "OPS limiter probe (<=3/s, singleton)",
                "F6-C-01",
                "FAIL",
                f"probe error: {exc!r}",
            )
        )


def probe_config(rep: Report) -> None:
    """HC-23 — CMP zero-assumption config values."""
    try:
        from loats.config import get_settings

        s = get_settings()
    except Exception as exc:
        rep.add(
            Result(
                "HC-23",
                "config conformance (Rule 1/4/5/7/11)",
                "TODO-17",
                "SKIP",
                f"import failed: {exc!r}",
            )
        )
        return
    checks = {
        "nifty_lot_size=25": getattr(s, "nifty_lot_size", None) == 25,
        "max_modifications=25 (Rule 7)": getattr(s, "max_modifications", None) == 25,
        "max_nifty_positions=5 (Rule 11)": getattr(s, "max_nifty_positions", None) == 5,
        "max_banknifty_positions=3": getattr(s, "max_banknifty_positions", None) == 3,
        "max_ops=3 (Rule 4)": getattr(s, "max_ops", None) == 3,
        "openalgo_mode=ANALYZE (Rule 5)": getattr(s, "openalgo_mode", None)
        == "ANALYZE",
        "sentiment_threshold=0.05 (Rule 9)": getattr(s, "sentiment_threshold", None)
        == 0.05,
    }
    bad = [k for k, ok in checks.items() if not ok]
    rep.add(
        Result(
            "HC-23",
            "config conformance (CMP zero-assumption rules)",
            "TODO-17",
            "PASS" if not bad else "FAIL",
            "all conform" if not bad else "non-conformant: " + ", ".join(bad),
            [f"{k}: {'ok' if v else 'MISMATCH'}" for k, v in checks.items()],
        )
    )


# ------------------------------------------------------------ gate runner ----


def run_gate(rep: Report, check_id, todo, name, cmd, timeout=300, allow_skip=None):
    env = os.environ.copy()
    # pip-audit on Windows fails if USERPROFILE/HOMEDRIVE are stripped by the
    # runner; ensure HOME-like variables are present so Path.home() works.
    env.setdefault("USERPROFILE", os.environ.get("USERPROFILE", r"C:\Users\npmvl-KP"))
    env.setdefault("HOMEDRIVE", os.environ.get("HOMEDRIVE", "C:"))
    env.setdefault("HOMEPATH", os.environ.get("HOMEPATH", r"\Users\npmvl-KP"))
    env.setdefault("HOME", env["USERPROFILE"])
    try:
        proc = subprocess.run(
            cmd, cwd=REPO_ROOT, capture_output=True, text=True, timeout=timeout, env=env
        )
    except subprocess.TimeoutExpired:
        status = "SKIP" if allow_skip else "FAIL"
        rep.add(
            Result(
                check_id,
                name,
                todo,
                status,
                f"timeout after {timeout}s"
                + (f" ({allow_skip})" if allow_skip else ""),
            )
        )
        return None
    tail = (proc.stdout or "").strip().splitlines()[-3:]
    tail += (proc.stderr or "").strip().splitlines()[-2:]
    rep.add(
        Result(
            check_id,
            name,
            todo,
            "PASS" if proc.returncode == 0 else "FAIL",
            f"exit {proc.returncode}",
            [t[:160] for t in tail if t.strip()],
        )
    )
    return proc.returncode


def check_gates(rep: Report, fast: bool) -> dict:
    py = sys.executable
    run_gate(rep, "HC-04", "gate", "deps-sync", [py, "scripts/check_deps_sync.py"], 120)
    run_gate(
        rep,
        "HC-05",
        "gate",
        "ruff check",
        [
            py,
            "-m",
            "ruff",
            "check",
            "src/",
            "tests/",
            "scripts/",
            "--config",
            "pyproject.toml",
        ],
        180,
    )
    run_gate(
        rep,
        "HC-06",
        "gate",
        "ruff format --check",
        [py, "-m", "ruff", "format", "--check", "src/", "tests/", "scripts/"],
        180,
    )
    run_gate(
        rep,
        "HC-07",
        "gate",
        "isort --check-only",
        [
            py,
            "-m",
            "isort",
            "--check-only",
            "src/",
            "tests/",
            "scripts/",
            "--settings-path",
            "pyproject.toml",
        ],
        180,
    )
    run_gate(
        rep,
        "HC-08",
        "gate",
        "flake8 (.flake8)",
        [py, "-m", "flake8", "src/", "tests/", "scripts/"],
        180,
    )
    run_gate(
        rep,
        "HC-09",
        "TODO-1",
        "mypy src/ --strict",
        [py, "-m", "mypy", "src/", "--strict", "--config-file", "pyproject.toml"],
        300,
    )
    run_gate(
        rep,
        "HC-10",
        "gate",
        "bandit",
        [py, "-m", "bandit", "-r", "src/", "-c", "pyproject.toml", "-q"],
        180,
    )

    rc: dict[str, int | None] = {"pip_audit": None, "pytest": None}
    if not fast:
        run_gate(
            rep,
            "HC-11",
            "TODO-4",
            "pip-audit (vuln DB)",
            [
                py,
                "-m",
                "pip_audit",
                "--format=json",
                "-o",
                "reports/health/pip_audit.json",
            ],
            240,
            allow_skip="network-blocked offline",
        )
        rc["pip_audit"] = 0

        # HC-12 — pytest with aggregate coverage gate
        rc["pytest"] = run_gate(
            rep,
            "HC-12",
            "TODO-3",
            "pytest --cov-fail-under=80 (aggregate)",
            [
                py,
                "-m",
                "pytest",
                "tests/",
                "--cov=src",
                "--cov-branch",
                "--cov-report=term-missing:skip-covered",
                "--cov-report=json:"
                + (REPO_ROOT / "reports/health/coverage.json").as_posix(),
                "--cov-fail-under=80",
                "-q",
            ],
            900,
        )
        check_module_floors(rep)
    else:
        rep.add(Result("HC-11", "pip-audit (vuln DB)", "TODO-4", "SKIP", "--fast mode"))
        rep.add(
            Result(
                "HC-12",
                "pytest aggregate coverage >=80%",
                "TODO-3",
                "SKIP",
                "--fast mode",
            )
        )
        rep.add(
            Result(
                "HC-13",
                "per-module coverage floors",
                "TODO-3/15",
                "SKIP",
                "--fast mode",
            )
        )
    return rc


PER_MODULE_FLOORS = {
    "src/loats/trailing_stop.py": 80,
    "src/loats/trade_decision.py": 80,
    "src/loats/orchestrator.py": 80,
    "src/loats/options.py": 85,
    "src/loats/database.py": 80,
    "src/loats/database_async_additions.py": 80,
}


def check_module_floors(rep: Report) -> None:
    """HC-13 — per-module coverage floors from coverage.json (written by HC-12 run)."""
    cj = REPO_ROOT / "reports/health/coverage.json"
    if not cj.exists():
        rep.add(
            Result(
                "HC-13",
                "per-module coverage floors",
                "TODO-3/15",
                "SKIP",
                "coverage.json not found",
            )
        )
        return
    try:
        data = json.loads(cj.read_text(encoding="utf-8"))
    except Exception as exc:
        rep.add(
            Result(
                "HC-13",
                "per-module coverage floors",
                "TODO-3/15",
                "SKIP",
                f"unparsable coverage.json: {exc!r}",
            )
        )
        return
    files = data.get("files", {})
    evidence, failures = [], []
    for rel, floor in sorted(PER_MODULE_FLOORS.items()):
        key = next(
            (k for k in files if k.replace("\\", "/").endswith(rel.replace("\\", "/"))),
            None,
        )
        if key is None:
            failures.append(f"{rel}: NOT MEASURED")
            continue
        pct = files[key].get("summary", {}).get("percent_covered", 0.0)
        line = f"{rel}: {pct:.1f}% (floor {floor})"
        (evidence if pct >= floor else failures).append(line)
    rep.add(
        Result(
            "HC-13",
            "per-module coverage floors (key modules)",
            "TODO-3/15",
            "PASS" if not failures else "FAIL",
            f"{len(failures)} module(s) below floor" if failures else "all floors met",
            failures + evidence,
        )
    )


# ------------------------------------------------------------------ main ----


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--fast",
        action="store_true",
        help="skip pytest / pip-audit / per-module floors",
    )
    ap.add_argument(
        "--only", default="", help="comma-separated check IDs to run (e.g. HC-14,HC-15)"
    )
    ap.add_argument(
        "--json", default="", help="write machine-readable report to this path"
    )
    args = ap.parse_args()

    only = {x.strip().upper() for x in args.only.split(",") if x.strip()}
    rep = Report()
    print(
        f"# FR7 health check — {REPO_ROOT.name} @ {os.environ.get('COMPUTERNAME', '')}"
    )
    if _ENV_INJECTED:
        print("# NOTE: OPENALGO_API_KEY injected (dummy) — HC-21 tracks why (TODO-18)")
    print()

    def wants(*ids):
        return not only or any(i.upper() in only for i in ids)

    if wants("HC-01", "HC-02", "HC-03", "HC-26"):
        check_structure(rep)
    if wants("HC-21"):
        check_eager_settings(rep)
    if wants("HC-18", "HC-20"):
        check_wiring(rep)
    if wants("HC-17", "HC-19", "HC-22", "HC-24", "HC-25", "HC-27"):
        check_decision_code(rep)
    if wants("HC-14"):
        probe_rate_limiter(rep)
    if wants("HC-15", "HC-16"):
        probe_strength_gate(rep)
    if wants("HC-23"):
        probe_config(rep)
    if not only or wants(
        "HC-04",
        "HC-05",
        "HC-06",
        "HC-07",
        "HC-08",
        "HC-09",
        "HC-10",
        "HC-11",
        "HC-12",
        "HC-13",
    ):
        check_gates(rep, fast=args.fast)

    if args.json:
        out = Path(args.json)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(rep.to_json(), indent=2), encoding="utf-8")
        print(f"\nJSON report -> {out}")
    return rep.summary()


if __name__ == "__main__":
    sys.exit(main())
