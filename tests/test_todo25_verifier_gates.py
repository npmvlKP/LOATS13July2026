"""Outcome-scoped regression tests for the TODO-25 (P1 latency) gate chain.

Covers three verified defects found in the F8 performance-review wave:

1. Wrong-scope gating (verify_todo25_external.py): when evidence is
   live-endpoint scope, the numeric latency gates read the analysis-scope
   blocks. Proven adversarial artifact: live endpoint at 480 ms mean /
   22% pass rate produced "VERIFICATION: PASSED", exit 0, while the
   printed numbers came from the in-process loop (10.44 ms). The P1
   discharge must be computed from the live scope only.

2. Vacuous --only selection (fr7_health_check.py): an --only value that
   matches zero checks silently exits 0 ("0 PASS / 0 FAIL"), which is
   exactly what masked the silent deletion of the HC-29 block by the
   TODO-28 mypy sweep. A selection that runs nothing must be an error.

3. HC-29 registration: verify_todo25_final.py Stage 6 greps
   fr7_health_check.py for the HC-29 marker and refuses to pass without
   it; the marker (and with it the whole HC-29 check) must be present
   and selectable again.

Also pins the ratchet-lockstep invariant: every tracked-file ratchet
surface (hygiene ceiling, F8-C-02 verifier, both TODO-21 verifiers)
must agree on a single baseline, so re-pinning one surface without the
others cannot pass CI again (the 416-vs-426 split shipped exactly that
way and left two committed gates failing at HEAD).
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
EXTERNAL_VERIFIER = REPO_ROOT / "scripts" / "verify_todo25_external.py"
FINAL_VERIFIER = REPO_ROOT / "scripts" / "verify_todo25_final.py"
HEALTH_CHECK = REPO_ROOT / "scripts" / "fr7_health_check.py"
GENUINE_EVIDENCE = REPO_ROOT / "reports" / "p1_analyze_latency_20260904_040609.json"

_PY_CANDIDATES = (
    REPO_ROOT / "loatsNEW" / "Scripts" / "python.exe",
    REPO_ROOT / ".venv" / "Scripts" / "python.exe",
)


def _python() -> str:
    for cand in _PY_CANDIDATES:
        if cand.exists():
            return str(cand)
    return sys.executable


def _child_env() -> dict[str, str]:
    env = os.environ.copy()
    env.setdefault("PYTHONIOENCODING", "utf-8")
    env.setdefault("PYTHONUTF8", "1")
    env.setdefault("OPENALGO_API_KEY", "verify-todo25-key")
    env.setdefault("OPENALGO_BASE_URL", "http://127.0.0.1:5000")
    env.setdefault("OPENALGO_MODE", "ANALYZE")
    return env


def _run_verifier(
    script: Path, *extra: str, timeout: int = 300
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [_python(), str(script), *extra],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=_child_env(),
        timeout=timeout,
    )


def _analysis_samples(n: int = 100) -> list[dict[str, Any]]:
    return [
        {
            "sample_id": i,
            "timestamp": "2026-09-04T10:00:00+00:00",
            "symbol": "ADV",
            "passes_ta_gate": True,
            "passes_db_gate": True,
            "passes_round_trip_gate": True,
        }
        for i in range(1, n + 1)
    ]


def _live_doc(
    *,
    live_mean: float = 480.0,
    live_pass_rate: float = 22.0,
    live_samples: int = 100,
    live_measurement_points: int = 0,
    scope: str = "live-endpoint",
) -> dict[str, Any]:
    """Live-scope evidence document with a healthy analysis scope.

    The analysis block mirrors the genuine artifact so only the live
    block can decide the verdict; the live block describes a
    catastrophically slow endpoint by default.
    """
    live_measurements = [
        {
            "sample_id": i,
            "timestamp": "2026-09-04T10:00:00+00:00",
            "symbol": "ADV",
            "live_duration_ms": live_mean,
            "passes_live_gate": False,
        }
        for i in range(1, live_measurement_points + 1)
    ]
    return {
        "metadata": {
            "todo_id": "TODO-25",
            "finding_id": "F7-L-05",
            "phase_gate": "P1",
            "description": "synthetic gate-holdout evidence",
            "collected_at": "2026-09-04T10:00:00+00:00",
            "git_commit": "c34adb5",
            "fix_version": "3.0",
            "measurement_scope": scope,
            "p1_discharging": True,
            "scopes": {
                "analysis": "TA calculation + local database operations (in-process)",
                "live": "POST /api/v1/quotes HTTP round trip to the configured OpenAlgo endpoint",
            },
        },
        "evidence": {
            "summary": {
                "total_samples": 100,
                "ta_gate": "80.0ms",
                "db_gate": "20.0ms",
                "round_trip_gate": "100.0ms",
            },
            "ta_statistics": {
                "min": 2.0,
                "max": 6.0,
                "mean": 2.9,
                "median": 3.0,
                "p90": 3.98,
                "p95": 4.0,
                "p99": 6.0,
                "std_dev": 0.66,
            },
            "db_statistics": {
                "min": 2.99,
                "max": 51.04,
                "mean": 7.54,
                "median": 3.0,
                "p90": 36.84,
                "p95": 38.18,
                "p99": 51.04,
                "std_dev": 10.94,
            },
            "round_trip_statistics": {
                "min": 5.0,
                "max": 53.05,
                "mean": 10.44,
                "median": 6.0,
                "p90": 39.85,
                "p95": 41.36,
                "p99": 53.05,
                "std_dev": 11.01,
            },
            "gate_compliance": {
                "ta_gate_pass_rate": 100.0,
                "db_gate_pass_rate": 90.0,
                "round_trip_gate_pass_rate": 100.0,
                "all_gates_pass_rate": 90.0,
            },
            "measurements": _analysis_samples(100),
        },
        "live_evidence": {
            "summary": {
                "total_samples": live_samples,
                "successful_samples": round(live_samples * live_pass_rate / 100),
                "failed_samples": live_samples
                - round(live_samples * live_pass_rate / 100),
                "round_trip_gate": "100.0ms",
            },
            "gate_compliance": {"live_round_trip_gate_pass_rate": live_pass_rate},
            "measurements": live_measurements,
            "round_trip_statistics": {
                "min": live_mean / 2,
                "max": live_mean * 2,
                "mean": live_mean,
                "median": live_mean,
                "p90": live_mean * 1.6,
                "p95": live_mean * 1.9,
                "p99": live_mean * 2,
                "std_dev": live_mean / 4,
            },
            "endpoint": {
                "base_url": "http://127.0.0.1:5000",
                "request_timeout_s": 30.0,
                "method": "POST /api/v1/quotes (read-only, AsyncOpenAlgoClient.get_quotes)",
            },
        },
    }


def _run_external_on(
    doc: dict[str, Any], tmp_path: Path
) -> subprocess.CompletedProcess[str]:
    evidence = tmp_path / "p1_analyze_latency_probe.json"
    evidence.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    try:
        return _run_verifier(EXTERNAL_VERIFIER, "--evidence", str(evidence))
    finally:
        evidence.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# 1. Wrong-scope gating (verify_todo25_external.py)
# ---------------------------------------------------------------------------


class TestWrongScopeGating:
    def test_slow_live_endpoint_must_not_pass(self, tmp_path: Path) -> None:
        """A live scope of 480 ms mean / 22% pass rate must FAIL the P1 gate.

        RED at HEAD: the verifier exited 0 with 'VERIFICATION: PASSED'
        because the numeric gates read the analysis-scope blocks.
        """
        proc = _run_external_on(_live_doc(), tmp_path)
        assert proc.returncode != 0, (
            "P1 gate PASSED a live endpoint averaging 480ms with 22% pass "
            f"rate. Output:\n{proc.stdout}\n{proc.stderr}"
        )
        assert "live" in proc.stdout.lower(), (
            "verdict output must reference the live scope it failed on"
        )

    def test_live_statistics_are_recomputed_from_measurements(
        self, tmp_path: Path
    ) -> None:
        """Live numbers must come from live measurements, not summary blocks.

        RED at HEAD: fabricated live summary blocks were never checked
        against the per-sample data.
        """
        proc = _run_external_on(
            _live_doc(live_mean=480.0, live_measurement_points=50), tmp_path
        )
        assert proc.returncode != 0
        assert (
            "inconsistent" in proc.stdout.lower() or "mismatch" in proc.stdout.lower()
        )

    def test_genuine_live_evidence_still_passes(self, tmp_path: Path) -> None:
        """The genuine 100/100 TCS run must keep discharging P1 (exit 0)."""
        if not GENUINE_EVIDENCE.exists():
            pytest.skip(f"genuine evidence not on disk: {GENUINE_EVIDENCE}")
        proc = _run_verifier(EXTERNAL_VERIFIER, "--evidence", str(GENUINE_EVIDENCE))
        assert proc.returncode == 0, (
            f"genuine live evidence regressed:\n{proc.stdout}\n{proc.stderr}"
        )

    def test_failed_live_scope_never_discharges(self, tmp_path: Path) -> None:
        """Scope 'live-endpoint (FAILED ...)' with a live block must FAIL."""
        doc = _live_doc(scope="live-endpoint (FAILED: endpoint unreachable)")
        proc = _run_external_on(doc, tmp_path)
        assert proc.returncode != 0

    def test_analysis_scope_only_never_discharges(self, tmp_path: Path) -> None:
        """No live_evidence block -> must fail the scope check (F8-L-03)."""
        doc = _live_doc()
        doc["metadata"]["measurement_scope"] = "analysis-scope (client-side only)"
        doc.pop("live_evidence")
        proc = _run_external_on(doc, tmp_path)
        assert proc.returncode != 0


# ---------------------------------------------------------------------------
# 2. Vacuous --only selection (fr7_health_check.py)
# ---------------------------------------------------------------------------


def _load_health_check_module():
    spec = importlib.util.spec_from_file_location(
        "fr7_health_check_under_test", HEALTH_CHECK
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # py3.12 dataclasses resolve the module namespace during @dataclass
    # processing; the module must be importable (in sys.modules) first.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class TestVacuousOnlySelection:
    def test_unknown_only_id_is_an_error(self) -> None:
        """--only matching zero checks must exit 2, not 0.

        RED at HEAD: '--only HC-29' after the block's deletion printed
        'HEALTH SUMMARY: 0 PASS / 0 FAIL / 0 SKIP' and exited 0 — the
        vacuous pass that hid the regression.
        """
        module = _load_health_check_module()
        rc = module.main(["--only", "HC-99"])
        assert rc == 2, f"vacuous --only selection exited {rc} (expected 2)"

    def test_known_only_id_still_selects(self) -> None:
        """A known id must still run exactly its checks (no false error)."""
        module = _load_health_check_module()
        rc = module.main(["--only", "HC-28"])
        assert rc == 0, f"known --only id exited {rc} (expected 0)"


# ---------------------------------------------------------------------------
# 3. HC-29 registration (fr7_health_check.py <-> verify_todo25_final.py)
# ---------------------------------------------------------------------------


class TestHC29Registration:
    def test_hc29_registered_and_wired(self) -> None:
        """HC-29 must be registered as a probe and wired into --only dispatch.

        RED at HEAD: the probe (and the whole check) had been deleted by
        the TODO-28 sweep; only verify_todo25_final.py's marker grep
        still referenced it.
        """
        source = HEALTH_CHECK.read_text(encoding="utf-8")
        assert "def probe_hc29" in source, "HC-29 probe function missing"
        assert 'wants("HC-29")' in source, "HC-29 not wired into --only dispatch"
        assert '"HC-29"' in source, "HC-29 missing from the known-id guard"

    def test_hc29_runs_and_passes(self) -> None:
        """The restored HC-29 probe must run the real external verifier."""
        module = _load_health_check_module()
        rep = module.Report()
        module.probe_hc29(rep)
        results = [r for r in rep.results if r.check_id == "HC-29"]
        assert results, "HC-29 probe produced no result"
        assert all(r.status == "PASS" for r in results), (
            f"HC-29 not passing: {[r.detail for r in results]}"
        )

    def test_final_verifier_passes_on_genuine_evidence(self) -> None:
        """verify_todo25_final.py must be green against the genuine artifact.

        RED at HEAD: Stage 6 failed ('HC-29 registered in health check')
        because the marker had been deleted, failing even genuine runs.
        """
        if not GENUINE_EVIDENCE.exists():
            pytest.skip(f"genuine evidence not on disk: {GENUINE_EVIDENCE}")
        proc = _run_verifier(FINAL_VERIFIER)
        assert proc.returncode == 0, (
            f"final verifier failed:\n{proc.stdout[-2000:]}\n{proc.stderr[-500:]}"
        )


# ---------------------------------------------------------------------------
# 4. Ratchet lockstep (tracked-file baselines agree across surfaces)
# ---------------------------------------------------------------------------


class TestRatchetLockstep:
    def test_all_tracked_file_ratchets_agree(self) -> None:
        """Every tracked-file ratchet surface must pin the same baseline.

        RED at HEAD: check_repo_hygiene.py was re-pinned 416 -> 426 while
        verify_f8c02_external.py and both TODO-21 verifiers stayed at
        416, leaving two committed gates failing on a clean tree.
        """
        pins: dict[str, int] = {}
        guard = (REPO_ROOT / "scripts" / "check_repo_hygiene.py").read_text(
            encoding="utf-8"
        )
        m = re.search(r"TRACKED_FILE_CEILING\s*=\s*(\d+)", guard)
        assert m, "TRACKED_FILE_CEILING not found in hygiene guard"
        pins["check_repo_hygiene"] = int(m.group(1))

        f8c02 = (REPO_ROOT / "scripts" / "verify_f8c02_external.py").read_text(
            encoding="utf-8"
        )
        m = re.search(r"len\(tracked\) <= (\d+)", f8c02)
        assert m, "tracked-count ceiling not found in verify_f8c02_external.py"
        pins["verify_f8c02_external"] = int(m.group(1))

        for name in (
            "verify_todo21_external.py",
            "verify_todo21_root_cleanup.py",
        ):
            text = (REPO_ROOT / "scripts" / name).read_text(encoding="utf-8")
            m = re.search(r"baseline_count\s*=\s*(\d+)", text)
            assert m, f"baseline_count not found in {name}"
            pins[name] = int(m.group(1))

        assert len(set(pins.values())) == 1, (
            f"ratchet surfaces disagree (the 416/426 split class): {pins}"
        )
        value = next(iter(pins.values()))
        assert 350 <= value <= 510, f"ratchet value out of sane band: {value}"

    def test_f8c02_verifier_passes_on_live_tree(self) -> None:
        proc = subprocess.run(
            [_python(), str(REPO_ROOT / "scripts" / "verify_f8c02_external.py")],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=_child_env(),
            timeout=300,
        )
        assert proc.returncode == 0, (
            f"verify_f8c02_external.py fails on the live tree:\n"
            f"{proc.stdout[-1500:]}\n{proc.stderr[-300:]}"
        )

    def test_todo21_root_cleanup_passes_on_live_tree(self) -> None:
        proc = subprocess.run(
            [_python(), str(REPO_ROOT / "scripts" / "verify_todo21_root_cleanup.py")],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=_child_env(),
            timeout=300,
        )
        assert proc.returncode == 0, (
            f"verify_todo21_root_cleanup.py fails on the live tree:\n"
            f"{proc.stdout[-1500:]}\n{proc.stderr[-300:]}"
        )
