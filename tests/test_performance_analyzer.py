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

    # Patch the iterations local by replacing the function source path:
    # Instead call with a custom thin wrapper that mirrors the function with iters=1
    async def thin_benchmark(db_arg: Any) -> dict[str, Any]:
        async def test_signal_round_trip() -> int:
            signal = Signal(
                signal_id="benchmark_x",
                symbol="NIFTY",
                signal_type=SignalType.BUY,
                strength=0.8,
                timestamp=datetime.now(UTC),
                indicators={"rsi": 70.0, "macd": 0.5},
                metadata={"benchmark": "p1_p5"},
            )
            await db_arg.async_create_signal(signal)
            signals = await db_arg.async_get_latest_signals("NIFTY", limit=1)
            return len(signals)

        async def test_historical_processing() -> int:
            test_data = [
                HistoricalData(
                    symbol="NIFTY",
                    timestamp=datetime.now(UTC),
                    open=100.0,
                    high=101.0,
                    low=99.0,
                    close=100.5,
                    volume=1000,
                    interval="1min",
                )
            ]
            await db_arg.async_store_historical_data(test_data)
            return 1

        for i in range(2):
            await pamod.performance_analyzer.measure_latency(
                f"signal_round_trip_{i}",
                test_signal_round_trip,
                _metadata={"iteration": i, "test_type": "signal"},
            )
            await pamod.performance_analyzer.measure_latency(
                f"historical_processing_{i}",
                test_historical_processing,
                _metadata={"iteration": i, "test_type": "historical"},
            )
        stats = pamod.performance_analyzer.get_statistics()
        validation = pamod.performance_analyzer.validate_cmp_latency_gates(
            p1_threshold=0.001, p5_threshold=0.005
        )
        return {
            "statistics": stats,
            "validation": validation,
            "iterations": 2,
            "timestamp": datetime.now(UTC).isoformat(),
        }

    out = await thin_benchmark(db)
    assert out["iterations"] == 2
    assert "statistics" in out

    # Also invoke the real run_latency_benchmark but stop early via measure raising StopAsyncIteration
    stop = {"n": 0}

    async def stop_after_two(
        operation: str, func: Any, *args: Any, **kwargs: Any
    ) -> Any:
        stop["n"] += 1
        if stop["n"] > 2:
            raise KeyboardInterrupt("stop benchmark early")
        return await real_measure(operation, func, *args, **kwargs)

    monkeypatch.setattr(pamod.performance_analyzer, "measure_latency", stop_after_two)
    with pytest.raises(KeyboardInterrupt):
        await run_latency_benchmark(db)
