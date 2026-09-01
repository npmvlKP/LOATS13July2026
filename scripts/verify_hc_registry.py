#!/usr/bin/env python3
"""HC-Registry Verifier (HC-01..HC-27).

The HC registry is a single, machine-checkable catalogue mapping each
gate (HC-NN) to the TODO that resolves it, the measurement rule and the
expected PASS criterion. Every gate is verified out-of-process so each
consecutive wave can confirm the registry is "healthy" without
ambiguity.

Groups
------
* HC-01..HC-13 : structural + quality gates (delegated to
  ``scripts/verify_hc_all.py`` for parity)
* HC-14..HC-15 : applied-circuit probes (operational math under load)
* HC-16..HC-22 : static-analysis (AST + grep) probes
* HC-23..HC-27 : configuration / runtime invariant probes

The script prints a 27-row table with per-row PASS/FAIL/SKIP verdict
and exits 0 only if every required row is PASS (HC-11 SKIP-tolerant
offline; SKIP is otherwise a FAIL).
"""

from __future__ import annotations

import argparse
import ast
import io
import json
import os
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

# ---------------------------------------------------------------------------
# Windows UTF-8 stdout/stderr fix.
# ---------------------------------------------------------------------------
if sys.platform == "win32":
    try:
        if hasattr(sys.stdout, "buffer") and not isinstance(
            sys.stdout, io.TextIOWrapper
        ):
            sys.stdout = io.TextIOWrapper(
                sys.stdout.buffer,
                encoding="utf-8",
                errors="replace",
                line_buffering=True,
            )
        if hasattr(sys.stderr, "buffer") and not isinstance(
            sys.stderr, io.TextIOWrapper
        ):
            sys.stderr = io.TextIOWrapper(
                sys.stderr.buffer,
                encoding="utf-8",
                errors="replace",
                line_buffering=True,
            )
    except (OSError, ValueError, AttributeError):
        os.environ.setdefault("PYTHONIOENCODING", "utf-8")
        os.environ.setdefault("PYTHONUTF8", "1")

REPO_ROOT = Path(__file__).resolve().parent.parent
PASS_SYM = "[PASS]"
FAIL_SYM = "[FAIL]"
SKIP_SYM = "[SKIP]"


def _has_dev_tools(p: Path) -> bool:
    try:
        return (p.parent.parent / "Lib" / "site-packages" / "ruff").exists() or (
            p.parent.parent / "lib" / "python3.12" / "site-packages" / "ruff"
        ).exists()
    except Exception:
        return False


def _resolve_python() -> str:
    candidates = [
        REPO_ROOT / "loatsNEW" / "Scripts" / "python.exe",
        REPO_ROOT / "loatsNEW" / "bin" / "python",
        REPO_ROOT / ".venv" / "Scripts" / "python.exe",
        REPO_ROOT / ".venv" / "bin" / "python",
    ]
    for cand in candidates:
        if cand.exists() and _has_dev_tools(cand):
            return str(cand)
    for cand in candidates:
        if cand.exists():
            return str(cand)
    return sys.executable


PY = _resolve_python()


def _child_env() -> dict[str, str]:
    env = os.environ.copy()
    env.setdefault("PYTHONIOENCODING", "utf-8")
    env.setdefault("PYTHONUTF8", "1")
    env.setdefault("OPENALGO_API_KEY", "verify-hc-registry-key")
    env.setdefault("OPENALGO_BASE_URL", "http://127.0.0.1:5000")
    env.setdefault("OPENALGO_MODE", "ANALYZE")
    return env


def run_cmd(
    cmd: list[str],
    cwd: Path = REPO_ROOT,
    timeout: int = 300,
) -> tuple[int, str, str]:
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=cwd,
        env=_child_env(),
        timeout=timeout,
    )
    return result.returncode, result.stdout, result.stderr


class Verdict(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    SKIP = "SKIP"


@dataclass(frozen=True)
class Row:
    hcid: str
    title: str
    todo: str
    skip_tolerated: bool
    verdict: Verdict
    detail: str


# ---------------------------------------------------------------------------
# HC-01..HC-13: structural + quality gates (delegated to verify_hc_all.py)
# ---------------------------------------------------------------------------
def _delegate_verify_hc_all() -> tuple[Verdict, str]:
    rc, _, err = run_cmd([PY, "scripts/verify_hc_all.py"], cwd=REPO_ROOT, timeout=600)
    if rc == 0:
        return Verdict.PASS, "delegate: verify_hc_all.py rc=0"
    return Verdict.FAIL, f"delegate: verify_hc_all.py rc={rc} :: {err.strip()[:200]}"


def _check_hc14() -> tuple[Verdict, str]:
    probe = REPO_ROOT / "scripts" / "probe_hc14_ops_limiter.py"
    if not probe.exists():
        return Verdict.FAIL, "probe script missing"
    rc, out, err = run_cmd([PY, str(probe)], timeout=15)
    if rc == 0:
        return Verdict.PASS, "3 of 10 acquires accepted (max_ops=3)"
    return Verdict.FAIL, f"probe rc={rc} :: {err.strip()[:200] or out.strip()[:200]}"


def _check_hc15() -> tuple[Verdict, str]:
    probe = REPO_ROOT / "scripts" / "probe_hc15_strength_gate.py"
    if not probe.exists():
        return Verdict.FAIL, "probe script missing"
    rc, out, err = run_cmd([PY, str(probe)], timeout=15)
    if rc == 0:
        return Verdict.PASS, "3 sources reject / 4 sources pass"
    return Verdict.FAIL, f"probe rc={rc} :: {err.strip()[:200] or out.strip()[:200]}"


def _check_hc16() -> tuple[Verdict, str]:
    probe = REPO_ROOT / "scripts" / "probe_hc16_unknown_source.py"
    if probe.exists():
        rc, out, err = run_cmd([PY, str(probe)], timeout=15)
        if rc == 0:
            return Verdict.PASS, "unknown source string rejected loudly"
        return (
            Verdict.FAIL,
            f"probe rc={rc} :: {err.strip()[:200] or out.strip()[:200]}",
        )
    sr = (REPO_ROOT / "src" / "loats" / "strength.py").read_text(encoding="utf-8")
    has_phrase = "Reject unknown source strings loudly" in sr
    has_validate = "validate_signal_sources" in sr
    if has_phrase and has_validate:
        return Verdict.PASS, "strength.validate_signal_sources rejects unknowns"
    return Verdict.FAIL, "no unknown-source rejection code-path found"


def _check_hc17() -> tuple[Verdict, str]:
    op = REPO_ROOT / "src" / "loats" / "orchestrator.py"
    text = op.read_text(encoding="utf-8")
    needles = ('"source": "orchestrator"', '"source":"orchestrator"')
    count = sum(text.count(n) for n in needles)
    if count == 0:
        return Verdict.PASS, f"{count} occurrences (expect 0)"
    return Verdict.FAIL, f"{count} occurrences (expect 0)"


def _check_hc18() -> tuple[Verdict, str]:
    src = REPO_ROOT / "src"
    callers: list[str] = []
    for py in src.rglob("*.py"):
        if "__pycache__" in str(py):
            continue
        text = py.read_text(encoding="utf-8")
        if "set_vix_level" not in text:
            continue
        if py.name == "rules.py":
            continue
        for ln, line in enumerate(text.splitlines(), 1):
            if "set_vix_level" in line and "def set_vix_level" not in line:
                callers.append(f"{py.relative_to(REPO_ROOT)}:{ln}")
    if callers:
        return Verdict.PASS, f"callers={len(callers)} ({', '.join(callers[:2])}...)"
    return Verdict.FAIL, "callers=0 (expect >=1)"


def _check_hc19() -> tuple[Verdict, str]:
    src = (REPO_ROOT / "src" / "loats" / "trade_decision.py").read_text(
        encoding="utf-8"
    )
    settings_txt = (REPO_ROOT / "src" / "loats" / "config" / "settings.py").read_text(
        encoding="utf-8"
    )
    if "AsyncOpenAlgoClient" not in src or "place_analyzer_request" not in src:
        return (
            Verdict.FAIL,
            "no AsyncOpenAlgoClient.place_analyzer_request in trade_decision.py",
        )
    # Default analyzer_routing_enabled must be False (or `Field(False, ...)`)
    tree = ast.parse(settings_txt)
    found_disabled = False
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == "analyzer_routing_enabled"
        ):
            v = node.value
            # Direct: angle `bool = False`
            if isinstance(v, ast.Constant) and v.value is False:
                found_disabled = True
                break
            # `Field(False, ...)`: the first positional arg of Field call
            if (
                isinstance(v, ast.Call)
                and isinstance(v.func, ast.Name)
                and v.func.id == "Field"
            ):
                if (
                    v.args
                    and isinstance(v.args[0], ast.Constant)
                    and v.args[0].value is False
                ):
                    found_disabled = True
                    break
    if not found_disabled:
        return Verdict.FAIL, "analyzer_routing_enabled default is not False"
    itest = REPO_ROOT / "tests" / "test_analyzer_routing_integration.py"
    if not itest.exists() or itest.stat().st_size == 0:
        return Verdict.FAIL, "integration test file empty or missing"
    body = itest.read_text(encoding="utf-8")
    if "def test_" not in body:
        return Verdict.FAIL, "integration test has no test_ function"
    return Verdict.PASS, (
        "real HTTP routing (place_analyzer_request), default-on=False, integration test populated"
    )


def _check_hc20() -> tuple[Verdict, str]:
    src = REPO_ROOT / "src"
    callers: list[str] = []
    for py in src.rglob("*.py"):
        if "__pycache__" in str(py):
            continue
        text = py.read_text(encoding="utf-8")
        if "update_trailing_stop" not in text:
            continue
        for ln, line in enumerate(text.splitlines(), 1):
            if "update_trailing_stop" in line and "def " not in line:
                callers.append(f"{py.relative_to(REPO_ROOT)}:{ln}")
    if callers:
        return Verdict.PASS, f"callers={len(callers)} ({', '.join(callers[:2])}...)"
    return Verdict.FAIL, "callers=0 (expect >=1)"


def _check_hc21() -> tuple[Verdict, str]:
    src = REPO_ROOT / "src"
    sites: list[tuple[str, str, int]] = []
    for py in src.rglob("*.py"):
        if "__pycache__" in str(py) or "__init__" in py.name:
            continue
        try:
            tree = ast.parse(py.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in tree.body:
            value: ast.AST | None = None
            if isinstance(node, ast.Assign):
                value = node.value
            elif isinstance(node, ast.AnnAssign) and node.value is not None:
                value = node.value
            else:
                continue
            if value is None or not isinstance(value, ast.Call):
                continue
            f = value.func
            is_get_settings = (isinstance(f, ast.Name) and f.id == "get_settings") or (
                isinstance(f, ast.Attribute) and f.attr == "get_settings"
            )
            if not is_get_settings:
                continue
            names: list[str] = []
            if isinstance(node, ast.Assign):
                for t in node.targets:
                    if isinstance(t, ast.Name):
                        names.append(t.id)
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                names.append(node.target.id)
            if any(n in ("__all__", "__version__") for n in names):
                continue
            sites.append((str(py.relative_to(REPO_ROOT)), ",".join(names), node.lineno))
    if not sites:
        return Verdict.PASS, "0 module-level eager get_settings() sites"
    sample = ", ".join(f"{p}:{ln}({n})" for p, n, ln in sites[:5])
    return Verdict.FAIL, f"{len(sites)} eager sites ({sample}...)"


def _check_hc22() -> tuple[Verdict, str]:
    src = REPO_ROOT / "src"
    rc, out, _ = run_cmd(
        [
            "rg",
            "--hidden",
            "--no-ignore",
            "-l",
            "PYTEST_CURRENT_TEST",
            str(src),
        ],
        cwd=REPO_ROOT,
        timeout=15,
    )
    files = [line for line in (out or "").strip().splitlines() if line]
    if not files:
        return Verdict.PASS, "0 references in src/"
    return Verdict.FAIL, f"{len(files)} files reference PYTEST_CURRENT_TEST"


def _check_hc23() -> tuple[Verdict, str]:
    sp = REPO_ROOT / "src" / "loats" / "config" / "settings.py"
    tree = ast.parse(sp.read_text(encoding="utf-8"))
    settings_cls: ast.ClassDef | None = None
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "Settings":
            settings_cls = node
            break
    if settings_cls is None:
        return Verdict.FAIL, "Settings class not found"
    fields: dict[str, ast.AST] = {}
    for node in settings_cls.body:
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            fields[node.target.id] = node.value

    def _int(name: str, expected: int) -> tuple[bool, str]:
        if name not in fields:
            return False, f"missing '{name}'"
        v = fields[name]
        if (
            isinstance(v, ast.Constant)
            and isinstance(v.value, int)
            and v.value == expected
        ):
            return True, f"{name}={expected}"
        if (
            isinstance(v, ast.Call)
            and isinstance(v.func, ast.Name)
            and v.func.id == "Field"
        ):
            if (
                v.args
                and isinstance(v.args[0], ast.Constant)
                and v.args[0].value == expected
            ):
                return True, f"{name}=Field({expected})"
        return False, f"{name}={ast.unparse(v)!r} (expect {expected})"

    def _str(name: str, expected: str) -> tuple[bool, str]:
        if name not in fields:
            return False, f"missing '{name}'"
        v = fields[name]
        if (
            isinstance(v, ast.Constant)
            and isinstance(v.value, str)
            and v.value == expected
        ):
            return True, f"{name}={expected!r}"
        if (
            isinstance(v, ast.Call)
            and isinstance(v.func, ast.Name)
            and v.func.id == "Field"
        ):
            if (
                v.args
                and isinstance(v.args[0], ast.Constant)
                and v.args[0].value == expected
            ):
                return True, f"{name}=Field({expected!r})"
        return False, f"{name}={ast.unparse(v)!r} (expect {expected!r})"

    def _decimal(name: str, expected_str: str) -> tuple[bool, str]:
        if name not in fields:
            return False, f"missing '{name}'"
        v = fields[name]
        if (
            isinstance(v, ast.Call)
            and isinstance(v.func, ast.Name)
            and v.func.id == "Decimal"
        ):
            if (
                v.args
                and isinstance(v.args[0], ast.Constant)
                and v.args[0].value == expected_str
            ):
                return True, f"{name}=Decimal({expected_str!r})"
        if (
            isinstance(v, ast.Call)
            and isinstance(v.func, ast.Name)
            and v.func.id == "Field"
        ):
            if (
                v.args
                and isinstance(v.args[0], ast.Call)
                and isinstance(v.args[0].func, ast.Name)
            ):
                inner = v.args[0]
                if (
                    inner.func.id == "Decimal"
                    and inner.args
                    and isinstance(inner.args[0], ast.Constant)
                    and inner.args[0].value == expected_str
                ):
                    return True, f"{name}=Field(Decimal({expected_str!r}))"
        return False, f"{name}={ast.unparse(v)!r} (expect Decimal({expected_str!r}))"

    failures: list[str] = []
    for name, expected in (
        ("nifty_lot_size", 25),
        ("max_ops", 3),
        ("mods", 25),
        ("max_open_positions", 5),
        ("min_open_positions", 3),
    ):
        ok, msg = _int(name, expected)
        if not ok:
            failures.append(msg)
    ok, msg = _str("openalgo_mode", "ANALYZE")
    if not ok:
        failures.append(msg)
    ok, msg = _decimal("circuit_limit_pct", "0.05")
    if not ok:
        failures.append(msg)
    if failures:
        return Verdict.FAIL, "; ".join(failures)
    return Verdict.PASS, "all required fields match expected defaults"


def _check_hc24() -> tuple[Verdict, str]:
    rp = REPO_ROOT / "src" / "loats" / "rules.py"
    text = rp.read_text(encoding="utf-8")
    tree = ast.parse(text)
    found_buy = False
    found_sell = False
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "apply_gating_rules":
            local = "\n".join(text.splitlines()[node.lineno - 1 : node.end_lineno])
            import re as _re

            buy_pat = _re.search(r"iv_pass\s*=\s*iv_rank\s*<\s*(\d+)", local)
            sell_pat = _re.search(r"iv_pass\s*=\s*iv_rank\s*>\s*(\d+)", local)
            if buy_pat and int(buy_pat.group(1)) == 30:
                found_buy = True
            if sell_pat and int(sell_pat.group(1)) == 40:
                found_sell = True
            break
    if found_buy and found_sell:
        return Verdict.PASS, "BUY<30 / SELL>40 thresholds enforced"
    return Verdict.FAIL, f"BUY<30={found_buy}, SELL>40={found_sell}"


def _check_hc25() -> tuple[Verdict, str]:
    rp = REPO_ROOT / "src" / "loats" / "rules.py"
    rc, out, _ = run_cmd(
        ["rg", "-n", r"\b18\.5\b", str(rp)],
        cwd=REPO_ROOT,
        timeout=10,
    )
    if not out.strip():
        return Verdict.PASS, "no bare 18.5 VIX fallback in rules.py"
    return Verdict.FAIL, f"bare 18.5 references: {out.strip()[:140]}"


def _check_hc26() -> tuple[Verdict, str]:
    root = REPO_ROOT
    forbidden_names = {
        "$null",
        "[100%]",
        "0.21.0",
        "G......",
        "-p",
        "tmp_schema.db",
        "pytest_output.txt",
    }
    present = [n for n in forbidden_names if (root / n).exists()]
    t19 = root / "TODO19_VERIFICATION_REPORT.md"
    if t19.exists() and t19.stat().st_size == 0:
        present.append("TODO19_VERIFICATION_REPORT.md(0B)")
    if not present:
        return Verdict.PASS, "no root-level junk files"
    return Verdict.FAIL, f"junk present: {present}"


def _check_hc27() -> tuple[Verdict, str]:
    sp = (REPO_ROOT / "src" / "loats" / "config" / "settings.py").read_text(
        encoding="utf-8"
    )
    tp = (REPO_ROOT / "src" / "loats" / "trade_decision.py").read_text(encoding="utf-8")
    if "decision_queue_maxsize" not in sp:
        return Verdict.FAIL, "settings.decision_queue_maxsize missing"
    if "Queue(maxsize" not in tp:
        return Verdict.FAIL, "asyncio.Queue(maxsize=...) not used"
    if "put_nowait" not in tp:
        return Verdict.FAIL, "put_nowait missing"
    if "QueueFull" not in tp:
        return Verdict.FAIL, "QueueFull handler missing"
    if "get_queue_stats" not in tp:
        return Verdict.FAIL, "get_queue_stats missing"
    return (
        Verdict.PASS,
        "bounded queue (maxsize) + put_nowait + QueueFull + get_queue_stats",
    )


HC_CATALOG: list[tuple[str, str, str, bool, Callable[[], tuple[Verdict, str]]]] = [
    ("HC-01", "src/__init__.py absent", "TODO-23", False, _delegate_verify_hc_all),
    ("HC-02", "no stray src/*.py", "TODO-23", False, _delegate_verify_hc_all),
    ("HC-03", "no empty package shells", "TODO-23", False, _delegate_verify_hc_all),
    ("HC-04", "deps-sync script exists", "TODO-19", False, _delegate_verify_hc_all),
    ("HC-05", "ruff lint clean", "TODO-28", False, _delegate_verify_hc_all),
    ("HC-06", "ruff format clean", "TODO-22", False, _delegate_verify_hc_all),
    ("HC-07", "isort clean", "TODO-22", False, _delegate_verify_hc_all),
    ("HC-08", "flake8 clean", "TODO-22", False, _delegate_verify_hc_all),
    ("HC-09", "mypy strict clean", "TODO-28", False, _delegate_verify_hc_all),
    ("HC-10", "bandit clean", "TODO-28", False, _delegate_verify_hc_all),
    ("HC-11", "openalgo live", "GENERAL", True, _delegate_verify_hc_all),
    ("HC-12", "coverage aggregate >=80%", "TODO-24", False, _delegate_verify_hc_all),
    ("HC-13", "coverage per-module floors", "TODO-24", False, _delegate_verify_hc_all),
    ("HC-14", "OPS limiter probe (max_ops=3)", "F6-C-01", False, _check_hc14),
    ("HC-15", "strength-gate math probe", "TODO-8", False, _check_hc15),
    ("HC-16", "unknown source loudly rejected", "TODO-9", False, _check_hc16),
    ("HC-17", "zero orchestrator source literals", "TODO-7", False, _check_hc17),
    ("HC-18", "set_vix_level has >=1 caller", "TODO-12", False, _check_hc18),
    (
        "HC-19",
        "routing real (no sleep-sim, no default-on, integration)",
        "TODO-13",
        False,
        _check_hc19,
    ),
    ("HC-20", "update_trailing_stop has >=1 caller", "TODO-14", False, _check_hc20),
    ("HC-21", "zero module-level eager get_settings()", "TODO-18", False, _check_hc21),
    ("HC-22", "no PYTEST_CURRENT_TEST in src/", "TODO-20", False, _check_hc22),
    (
        "HC-23",
        "config conformance mods/lot/positions/max_ops/mode",
        "TODO-17",
        False,
        _check_hc23,
    ),
    ("HC-24", "rules BUY<30 / SELL>40", "TODO-16", False, _check_hc24),
    ("HC-25", "no bare 18.5 VIX fallback", "TODO-12", False, _check_hc25),
    ("HC-26", "root junk files absent", "TODO-21", False, _check_hc26),
    ("HC-27", "decision queue bounded", "TODO-27c", False, _check_hc27),
]


def _print_row(row: Row) -> None:
    sym = (
        _colour(PASS_SYM, "92")
        if row.verdict == Verdict.PASS
        else _colour(SKIP_SYM, "93")
        if row.verdict == Verdict.SKIP
        else _colour(FAIL_SYM, "91")
    )
    print(f"{sym} {row.hcid:<7} {row.todo:<10} {row.title:<55} {row.detail}")


def _colour(text: str, color_code: str) -> str:
    if not sys.stdout.isatty():
        return text
    return f"\033[{color_code}m{text}\033[0m"


def run_catalog(
    only: list[str] | None = None,
    fast: bool = False,
) -> list[Row]:
    by_id = {row[0]: row for row in HC_CATALOG}
    if only:
        order = [by_id[i] for i in only if i in by_id]
    else:
        order = HC_CATALOG
    rows: list[Row] = []
    if fast:
        fast_ids = {
            "HC-01",
            "HC-02",
            "HC-03",
            "HC-04",
            "HC-05",
            "HC-06",
            "HC-07",
            "HC-08",
            "HC-09",
            "HC-10",
            "HC-12",
            "HC-13",
            "HC-21",
            "HC-22",
            "HC-26",
        }
        order = [r for r in order if r[0] in fast_ids]
    for hcid, title, todo, skip_tolerated, check_fn in order:
        try:
            verdict, detail = check_fn()
            rows.append(Row(hcid, title, todo, skip_tolerated, verdict, detail))
        except Exception as e:
            rows.append(
                Row(
                    hcid,
                    title,
                    todo,
                    skip_tolerated,
                    Verdict.FAIL,
                    f"exception: {type(e).__name__}: {e}",
                )
            )
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description="HC Registry Verifier (HC-01..HC-27)")
    parser.add_argument("--only", help="comma-separated subset of HC IDs")
    parser.add_argument(
        "--fast",
        action="store_true",
        help="structural + critical static only (skip probes)",
    )
    parser.add_argument("--json", help="write JSON report to PATH")
    args = parser.parse_args()
    only = [s.strip() for s in args.only.split(",")] if args.only else None
    print("=" * 95)
    print("HC REGISTRY VERIFIER (HC-01..HC-27)")
    print(f"Interpreter: {PY}")
    print("=" * 95)
    rows = run_catalog(only=only, fast=args.fast)
    for r in rows:
        _print_row(r)
    print("=" * 95)
    passed = sum(1 for r in rows if r.verdict == Verdict.PASS)
    failed = sum(1 for r in rows if r.verdict == Verdict.FAIL)
    skipped = sum(1 for r in rows if r.verdict == Verdict.SKIP)
    print(
        f"TOTAL: PASS={passed} FAIL={failed} SKIP={skipped} ({len(rows)} of {len(HC_CATALOG)})"
    )
    if args.json:
        out = [
            {
                "hcid": r.hcid,
                "title": r.title,
                "todo": r.todo,
                "verdict": r.verdict,
                "detail": r.detail,
            }
            for r in rows
        ]
        Path(args.json).write_text(json.dumps(out, indent=2), encoding="utf-8")
        print(f"JSON report written to {args.json}")
    yellow = sum(1 for r in rows if r.verdict == Verdict.SKIP and not r.skip_tolerated)
    if failed or yellow:
        print(f"REGISTRY UNHEALTHY: failures={failed} intolerant-skips={yellow}")
        return 1
    print("REGISTRY HEALTHY")
    return 0


if __name__ == "__main__":
    sys.exit(main())
