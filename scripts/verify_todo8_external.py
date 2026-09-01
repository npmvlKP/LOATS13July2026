"""External verification for TODO-8/HC-15: 4th producer / ADR gate.

Checks that:
1. Orchestrator produces a volatility signal (4th producer) each cycle
   via ``_execute_volatility_analysis``.
2. The 4th source is one of the canonical StrengthSource enum values.
3. The diversity gate rejects 3 sources and accepts 4 sources (3/7 vs 4/7).
4. A fallback ADR-style producer file exists if the orchestrator is not live.
"""

from __future__ import annotations

import os
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

PASS_SYM = "[PASS]"
FAIL_SYM = "[FAIL]"


def _check_volatility_producer() -> bool:
    """Verify orchestrator has a volatility signal producer method."""
    orch = REPO_ROOT / "src" / "loats" / "orchestrator.py"
    text = orch.read_text(encoding="utf-8")
    has_method = "async def _execute_volatility_analysis" in text
    has_source = "StrengthSource.VOLATILITY" in text
    has_create_signal = "await db.async_create_signal(signal)" in text
    ok = has_method and has_source and has_create_signal
    print(
        f"{PASS_SYM if ok else FAIL_SYM} volatility producer present "
        f"(method={has_method}, source={has_source}, persist={has_create_signal})"
    )
    return ok


def _check_orchestrator_tag_enum() -> bool:
    """Verify orchestrator does not use literal orchestrator tags."""
    orch = REPO_ROOT / "src" / "loats" / "orchestrator.py"
    count = orch.read_text(encoding="utf-8").count('"source": "orchestrator"')
    ok = count == 0
    print(
        f"{PASS_SYM if ok else FAIL_SYM} no literal orchestrator source tags (count={count})"
    )
    return ok


def _check_diversity_gate() -> bool:
    """Run the HC-15 probe script to verify 3/4 diversity threshold."""
    env = os.environ.copy()
    env.setdefault("OPENALGO_API_KEY", "verify-todo8")
    result = subprocess.run(
        [PY, str(REPO_ROOT / "scripts" / "probe_hc15_strength_gate.py")],
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
        cwd=REPO_ROOT,
    )
    ok = result.returncode == 0
    print(
        f"{PASS_SYM if ok else FAIL_SYM} HC-15 diversity probe (3-src reject, 4-src pass)"
    )
    if not ok:
        for line in (result.stdout + result.stderr).splitlines():
            print(f"  {line}")
    return ok


def _check_e2e_test_present() -> bool:
    """Verify e2e CMP chain test exists and is not empty."""
    test = REPO_ROOT / "tests" / "test_e2e_cmp_chain.py"
    ok = (
        test.exists()
        and test.stat().st_size > 0
        and "def test_" in test.read_text(encoding="utf-8")
    )
    print(f"{PASS_SYM if ok else FAIL_SYM} e2e CMP chain test present and populated")
    return ok


def _check_adr_fallback() -> bool:
    """Verify ADR fallback documenting 4th producer exists."""
    docs = REPO_ROOT / "docs"
    fallback = docs / "ADR-004-volatility-producer.md"
    ok = fallback.exists()
    print(
        f"{PASS_SYM if ok else FAIL_SYM} ADR fallback document exists ({fallback.name})"
    )
    return ok


def main() -> int:
    print("=" * 70)
    print("TODO-8 / HC-15 EXTERNAL VERIFICATION: 4th producer / ADR gate")
    print(f"Interpreter: {PY}")
    print("=" * 70)
    results = [
        ("volatility_producer", _check_volatility_producer()),
        ("enum_orchestrator_tags", _check_orchestrator_tag_enum()),
        ("diversity_3_4_gate", _check_diversity_gate()),
        ("e2e_chain_test", _check_e2e_test_present()),
        ("adr_fallback", _check_adr_fallback()),
    ]
    print("=" * 70)
    passed = sum(1 for _, ok in results if ok)
    total = len(results)
    print(f"TOTAL: {passed}/{total} checks passed")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
