"""Unit tests for loats.performance_analyzer (HC-12/13 coverage lift)."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from loats.models import HistoricalData, Signal, SignalType
from loats.performance_analyzer import (
    DatabasePerformanceAnalyzer,
    LatencyMeasurement,
    PerformanceAnalyzer,
    analyzer,
    performance_analyzer,
    run_comprehensive_analysis,
    run_latency_benchmark,
)


def test_latency_measurement_to_dict() -> None:
    m = LatencyMeasurement(
        operation="op",
        start_time=1.0,
        end_time=1.5,
        success=True,
        metadata={"k": "v"},
    )
    d = m.to_dict()
    assert d["operation"] == "op"
    assert d["duration"] == pytest.approx(0.5)
    assert d["success"] is True
    assert d["metadata"]["k"] == "v"
    assert "timestamp" in d


@pytest.mark.asyncio
async def test_measure_latency_success_and_failure() -> None:
    pa = PerformanceAnalyzer(max_history=10)

    async def ok() -> str:
        await asyncio.sleep(0)
        return "ok"

    async def bad() -> None:
        raise RuntimeError("boom")

    result, m_ok = await pa.measure_latency("ok_op", ok, _metadata={"t": 1})
    assert result == "ok"
    assert m_ok.success is True
    assert m_ok.duration >= 0

    result2, m_bad = await pa.measure_latency("bad_op", bad)
    assert result2 is None
    assert m_bad.success is False
    assert "error" in m_bad.metadata

    stats_ok = pa.get_statistics("ok_op")
    assert stats_ok["count"] == 1
    assert "mean" in stats_ok

    stats_missing = pa.get_statistics("missing")
    assert stats_missing["count"] == 0

    all_stats = pa.get_statistics()
    assert "ok_op" in all_stats and "bad_op" in all_stats

    recent = pa.get_recent_measurements(limit=5)
    assert len(recent) >= 2

    # second measurement on same op exercises stats branch with std_dev
    await pa.measure_latency("ok_op", ok)
    stats2 = pa.get_statistics("ok_op")
    assert stats2["count"] == 2
    assert "std_dev" in stats2

    validation = pa.validate_cmp_latency_gates(p1_threshold=10.0, p5_threshold=10.0)
    assert "ok_op" in validation
    assert bool(validation["ok_op"]["overall_pass"]) is True

    pa.clear_history()
    assert pa.get_statistics() == {}
    assert pa.get_recent_measurements() == []


@pytest.mark.asyncio
async def test_measure_sync_latency_success_and_failure() -> None:
    pa = PerformanceAnalyzer()

    def ok_sync(x: int) -> int:
        return x + 1

    def bad_sync() -> None:
        raise ValueError("sync fail")

    result, m = await pa.measure_sync_latency("sync_ok", ok_sync, 41)
    assert result == 42
    assert m.success is True

    result2, m2 = await pa.measure_sync_latency("sync_bad", bad_sync)
    assert result2 is None
    assert m2.success is False


def test_module_level_singletons() -> None:
    assert isinstance(performance_analyzer, PerformanceAnalyzer)
    assert analyzer is performance_analyzer


@pytest.mark.asyncio
async def test_database_performance_analyzer_with_mocks() -> None:
    db = MagicMock()
    db.async_create_signal = AsyncMock(return_value=True)
    db.async_store_historical_data = AsyncMock(return_value=True)
    db.async_get_latest_signals = AsyncMock(return_value=[])
    db.create_signal = MagicMock(return_value=True)
    db.store_historical_data = MagicMock(return_value=True)
    db.get_latest_signals = MagicMock(return_value=[])

    dpa = DatabasePerformanceAnalyzer(db)
    stats = await dpa.measure_database_operations(iterations=1)
    assert isinstance(stats, dict)
    assert len(stats) >= 1

    # generate test data path
    data = dpa._generate_test_data(5)
    assert len(data) == 5
    assert all(isinstance(h, HistoricalData) for h in data)

    # measure_analyze_round_trip with mocked TA + DB
    async def fake_to_thread(func: Any, *args: Any, **kwargs: Any) -> Any:
        return {"rsi": 50.0}

    import loats.performance_analyzer as pamod

    original = pamod.asyncio.to_thread
    pamod.asyncio.to_thread = fake_to_thread  # type: ignore[assignment]
    try:
        result = await dpa.measure_analyze_round_trip(data_size=3)
        assert "round_trip" in result
        assert result["data_size"] == 3
        assert "duration" in result["round_trip"]
    finally:
        pamod.asyncio.to_thread = original  # type: ignore[assignment]


@pytest.mark.asyncio
async def test_run_comprehensive_and_latency_benchmark() -> None:
    db = MagicMock()
    db.async_create_signal = AsyncMock(return_value=True)
    db.async_store_historical_data = AsyncMock(return_value=True)
    db.async_get_latest_signals = AsyncMock(
        return_value=[
            Signal(
                symbol="NIFTY",
                signal_type=SignalType.BUY,
                strength=0.5,
                timestamp=datetime.now(UTC),
            )
        ]
    )
    db.create_signal = MagicMock(return_value=True)
    db.store_historical_data = MagicMock(return_value=True)
    db.get_latest_signals = MagicMock(return_value=[])

    import loats.performance_analyzer as pamod

    # Shrink iterations for speed by patching methods
    async def tiny_db_ops(
        self: DatabasePerformanceAnalyzer, iterations: int = 1
    ) -> dict[str, Any]:
        return {
            "tiny": {
                "count": 1,
                "p95": 0.0001,
                "p99": 0.0002,
                "min": 0,
                "max": 0,
                "mean": 0,
                "median": 0,
                "std_dev": 0,
            }
        }

    async def tiny_rt(
        self: DatabasePerformanceAnalyzer, data_size: int = 10
    ) -> dict[str, Any]:
        return {
            "ta_calculation": {"duration": 0.001},
            "db_operations": {"duration": 0.001},
            "round_trip": {
                "duration": 0.002,
                "ta_percentage": 50.0,
                "db_percentage": 50.0,
            },
            "data_size": data_size,
            "ta_result": 1,
            "db_result": 1,
        }

    original_db = DatabasePerformanceAnalyzer.measure_database_operations
    original_rt = DatabasePerformanceAnalyzer.measure_analyze_round_trip
    DatabasePerformanceAnalyzer.measure_database_operations = tiny_db_ops  # type: ignore[assignment,method-assign]
    DatabasePerformanceAnalyzer.measure_analyze_round_trip = tiny_rt  # type: ignore[assignment,method-assign]
    try:
        out = await run_comprehensive_analysis(db)
        assert "database_operations" in out
        assert "analyze_round_trip" in out
        assert "cmp_validation" in out
        assert "timestamp" in out
    finally:
        DatabasePerformanceAnalyzer.measure_database_operations = original_db  # type: ignore[method-assign]
        DatabasePerformanceAnalyzer.measure_analyze_round_trip = original_rt  # type: ignore[method-assign]

    # latency benchmark with 1 iteration via temporary override of loop
    # Call with patched measure_latency to avoid 100 iterations
    calls = {"n": 0}

    async def fast_measure(
        operation: str, func: Any, *args: Any, **kwargs: Any
    ) -> tuple[Any, LatencyMeasurement]:
        calls["n"] += 1
        result = await func()
        m = LatencyMeasurement(
            operation, 0.0, 0.0001, True, kwargs.get("_metadata", {})
        )
        return result, m

    original_ml = pamod.performance_analyzer.measure_latency
    pamod.performance_analyzer.measure_latency = fast_measure  # type: ignore[method-assign]
    # Also shrink iterations by wrapping run_latency_benchmark body is heavy —
    # patch asyncio loop count by replacing the module function's local iterations:
    # call a reduced custom path instead
    try:
        # Directly exercise the nested helpers by calling once each via Database path
        async def one_signal() -> int:
            signal = Signal(
                signal_id="b1",
                symbol="NIFTY",
                signal_type=SignalType.BUY,
                strength=0.8,
                timestamp=datetime.now(UTC),
                indicators={"rsi": 70.0},
                metadata={"benchmark": "p1_p5"},
            )
            await db.async_create_signal(signal)
            signals = await db.async_get_latest_signals("NIFTY", limit=1)
            return len(signals)

        r, m = await fast_measure("signal_rt", one_signal)
        assert r == 1
        assert m.success is True

        # Seed stats then validate gates
        pamod.performance_analyzer.operation_stats["signal_rt"] = [0.0001, 0.0002]
        validation = pamod.performance_analyzer.validate_cmp_latency_gates(
            p1_threshold=1.0, p5_threshold=1.0
        )
        assert "signal_rt" in validation
    finally:
        pamod.performance_analyzer.measure_latency = original_ml  # type: ignore[method-assign]


@pytest.mark.asyncio
async def test_run_latency_benchmark_short_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cover run_latency_benchmark with reduced iterations via monkeypatch on range."""
    db = MagicMock()
    db.async_create_signal = AsyncMock(return_value=True)
    db.async_store_historical_data = AsyncMock(return_value=True)
    db.async_get_latest_signals = AsyncMock(return_value=[])

    import loats.performance_analyzer as pamod

    async def fake_to_thread(func: Any, *a: Any, **k: Any) -> Any:
        return {"rsi": 1.0}

    monkeypatch.setattr(pamod.asyncio, "to_thread", fake_to_thread)

    # Replace range used in the function by rewriting iterations: patch builtins.range
    # only for the first call site by intercepting measure_latency count.
    real_measure = pamod.performance_analyzer.measure_latency
    count = {"n": 0}

    async def limited_measure(
        operation: str, func: Any, *args: Any, **kwargs: Any
    ) -> Any:
        count["n"] += 1
        if count["n"] > 4:  # allow 2 iterations * 2 ops
            m = LatencyMeasurement(operation, 0.0, 0.0, True)
            return None, m
        return await real_measure(operation, func, *args, **kwargs)

    monkeypatch.setattr(pamod.performance_analyzer, "measure_latency", limited_measure)

    # Shrink the iteration count and exercise the REAL benchmark path.
    monkeypatch.setattr(pamod, "BENCHMARK_ITERATIONS", 1)

    out = await run_latency_benchmark(db)
    assert out["iterations"] == 1
    assert "statistics" in out

    # Regression net (false-green benchmark gate): stable operation names,
    # so percentiles accumulate per operation instead of n=1 buckets.
    assert "signal_round_trip" in out["statistics"]
    assert "historical_processing" in out["statistics"]
    # The gate graded the operations with the phase-gate budgets, not the
    # impossible 1ms/5ms defaults.
    assert out["validation"]["signal_round_trip"]["p1_threshold"] == (pamod.P1_GATE_S)
    assert out["validation"]["signal_round_trip"]["p5_threshold"] == (pamod.P5_GATE_S)
    assert out["validation"]["signal_round_trip"]["samples"] == 1


def test_phase_gate_budgets_match_authoritative_collector() -> None:
    """The validator defaults must mirror the authoritative P1/P5 gates.

    Regression net: the original 1ms/5ms defaults were impossible for full
    round-trip operations; the authoritative budgets live in
    scripts/collect_p1_phase_gate_evidence.py (DB_GATE_MS, ROUND_TRIP_GATE_MS).
    """
    import re
    from pathlib import Path

    import loats.performance_analyzer as pamod

    collector = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "collect_p1_phase_gate_evidence.py"
    )
    src = collector.read_text(encoding="utf-8")
    db_match = re.search(r"DB_GATE_MS\s*=\s*([0-9.]+)", src)
    rt_match = re.search(r"ROUND_TRIP_GATE_MS\s*=\s*([0-9.]+)", src)
    assert db_match is not None and rt_match is not None
    assert pamod.P1_GATE_S * 1000 == pytest.approx(float(db_match.group(1)))
    assert pamod.P5_GATE_S * 1000 == pytest.approx(float(rt_match.group(1)))


def _load_benchmark_script_module() -> Any:
    """Load scripts/benchmark_performance.py as a module for unit probes."""
    import importlib.util
    from pathlib import Path

    script = (
        Path(__file__).resolve().parents[1] / "scripts" / "benchmark_performance.py"
    )
    spec = importlib.util.spec_from_file_location(
        "loats_benchmark_performance_probe", script
    )
    assert spec is not None and spec.loader is not None
    mod: Any = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _summary_inputs(
    cmp_validation: dict[str, Any], bench_validation: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    comprehensive = {
        "database_operations": {},
        "analyze_round_trip": {
            "round_trip": {
                "duration": 0.1,
                "ta_percentage": 50.0,
                "db_percentage": 50.0,
            }
        },
        "cmp_validation": cmp_validation,
    }
    benchmark = {"validation": bench_validation}
    return comprehensive, benchmark


def test_generate_summary_fails_closed_on_empty_measurement_set() -> None:
    """A run that measured nothing must FAIL, never grade 0 == 0 as PASS."""
    mod = _load_benchmark_script_module()
    comprehensive, benchmark = _summary_inputs({}, {})
    with pytest.raises(ValueError, match=r"fail-closed|empty"):
        mod.generate_summary(comprehensive, benchmark)


def test_generate_summary_grades_union_of_validations() -> None:
    """The verdict must include benchmark validations the registry misses.

    Regression net: the original code graded only the (empty) production
    registry, hiding 200 failing benchmark operations behind a PASS.
    """
    mod = _load_benchmark_script_module()
    bench = {
        "good_op": {"overall_pass": True},
        "bad_op": {"overall_pass": False},
    }
    comprehensive, benchmark = _summary_inputs({}, bench)
    summary = mod.generate_summary(comprehensive, benchmark)
    assert summary["overall_status"] == "PARTIAL"
    assert summary["cmp_validation"]["total_operations"] == 2
    assert summary["cmp_validation"]["passing_operations"] == 1
    assert summary["benchmark_validation"]["total_operations"] == 2
    assert summary["benchmark_validation"]["passing_operations"] == 1


def test_generate_summary_passes_only_when_all_checks_pass() -> None:
    mod = _load_benchmark_script_module()
    cmp_val = {"registry_op": {"overall_pass": True}}
    bench = {"bench_op": {"overall_pass": True}}
    comprehensive, benchmark = _summary_inputs(cmp_val, bench)
    summary = mod.generate_summary(comprehensive, benchmark)
    assert summary["overall_status"] == "PASS"
    assert summary["cmp_validation"]["pass_rate"] == pytest.approx(1.0)


def test_measure_database_operations_stats_keys_are_stable() -> None:
    """Per-iteration operation names fragment samples into n=1 buckets.

    Regression net: the summary reads stable keys (``async_create_signal``,
    ``sync_get_signals``); fragmented names made every lookup miss and the
    benchmark printed ``0.000ms`` for every operation.
    """
    import tempfile
    from pathlib import Path

    from loats.database import Database

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        tmp_db = Database(
            db_path=Path(td) / "bench.db",
            audit_log_path=Path(td) / "bench_audit.jsonl",
        )
        dpa = DatabasePerformanceAnalyzer(tmp_db)

        async def run() -> dict[str, Any]:
            await tmp_db.async_initialize()
            try:
                return await dpa.measure_database_operations(iterations=1)
            finally:
                await tmp_db.async_close_all()

        stats = asyncio.run(run())
        for key in (
            "async_create_signal",
            "async_store_historical",
            "async_get_signals",
            "sync_create_signal",
            "sync_store_historical",
            "sync_get_signals",
        ):
            assert key in stats, f"missing stable stats key: {key}"
            assert stats[key]["count"] == 1


def test_validate_gates_grade_the_registry_they_measured() -> None:
    """run_comprehensive_analysis must validate the registry it populated.

    Regression net: it measured into DatabasePerformanceAnalyzer's own
    PerformanceAnalyzer but validated the module singleton, so the graded
    registry was always empty (the ``Operations Tested: 0`` false-green).
    """
    import loats.performance_analyzer as pamod

    dpa = DatabasePerformanceAnalyzer(MagicMock())
    empty = dpa.analyzer.validate_cmp_latency_gates()
    assert empty == {}
    # The run's writer is the DPA-local analyzer, not the singleton:
    # simulate a measurement and confirm it lands in the DPA registry and
    # NOT in the singleton the old code graded.

    async def seed() -> None:
        await dpa.analyzer.measure_latency("probe_op", _noop_probe)

    asyncio.run(seed())
    assert dpa.analyzer.get_statistics("probe_op")["count"] == 1
    assert pamod.performance_analyzer.get_statistics("probe_op")["count"] == 0


async def _noop_probe() -> int:
    return 1


def test_benchmark_script_isolates_data_from_production() -> None:
    """The standalone benchmark must never bind the production DB singleton.

    Subprocess probe: a pre-import env probe prints the resolved paths;
    the assertion is that they resolve inside the run's scratch dir, not
    the repo's live data directory.
    """
    import os
    import subprocess
    import sys
    from pathlib import Path

    repo = Path(__file__).resolve().parents[1]
    env = dict(os.environ)
    env.setdefault("ENVIRONMENT", "test")
    env.setdefault("OPENALGO_API_KEY", "test_api_key")
    env.setdefault("OPENALGO_BASE_URL", "https://test.openalgo.com")
    env.setdefault("TELEGRAM_BOT_TOKEN", "test_bot_token")
    env.setdefault("TELEGRAM_CHAT_ID", "123456789")
    env.setdefault("LOATS_SUPPRESS_NLTK_WARNING", "1")
    probe = (
        "import os, sys;"
        "sys.path.insert(0, r'" + str(repo) + "');"
        "import scripts.benchmark_performance as bp;"
        "print(bp.os.environ['SQLITE_DB_PATH']);"
        "print(bp.os.environ['AUDIT_LOG_PATH'])"
    )
    proc = subprocess.run(
        [sys.executable, "-c", probe],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(repo),
        timeout=120,
    )
    assert proc.returncode == 0, proc.stderr[-500:]
    db_path, audit_path = proc.stdout.strip().splitlines()[-2:]
    assert "loats_benchmark_" in db_path, db_path
    assert "loats_benchmark_" in audit_path, audit_path
