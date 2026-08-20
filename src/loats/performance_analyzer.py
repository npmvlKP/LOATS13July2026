"""
Performance Analyzer for LOATS13July2026.
Implements comprehensive latency measurement and CMP P1/P5 validation.
"""

import asyncio
import statistics
import time
from collections import deque
from collections.abc import Callable, Coroutine
from datetime import UTC, datetime, timedelta
from typing import Any

import numpy as np

from .database import Database
from .loats_logging import get_logger
from .models import HistoricalData, Signal, SignalType
from .ta import TechnicalAnalysis

logger = get_logger(__name__)


class LatencyMeasurement:
    """Single latency measurement with metadata."""

    def __init__(
        self,
        operation: str,
        start_time: float,
        end_time: float,
        success: bool,
        metadata: dict[str, Any] | None = None,
    ):
        self.operation = operation
        self.start_time = start_time
        self.end_time = end_time
        self.duration = end_time - start_time
        self.success = success
        self.metadata = metadata or {}
        self.timestamp = datetime.now(UTC)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "operation": self.operation,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration": self.duration,
            "success": self.success,
            "metadata": self.metadata,
            "timestamp": self.timestamp.isoformat(),
        }


class PerformanceAnalyzer:
    """Comprehensive performance analyzer for LOATS13July2026."""

    def __init__(self, max_history: int = 1000):
        self.max_history = max_history
        self.latency_history: deque[LatencyMeasurement] = deque(maxlen=max_history)
        self.operation_stats: dict[str, list[float]] = {}
        self.lock = asyncio.Lock()

    async def measure_latency(
        self,
        operation: str,
        func: Callable[..., Coroutine[Any, Any, Any]],
        *args: Any,
        **kwargs: Any,
    ) -> tuple[Any, LatencyMeasurement]:
        """Measure latency of an async function."""
        start_time = time.perf_counter()
        metadata = kwargs.pop("_metadata", {})

        try:
            result = await func(*args, **kwargs)
            end_time = time.perf_counter()
            success = True
        except Exception as e:
            end_time = time.perf_counter()
            result = None
            success = False
            metadata["error"] = str(e)
            logger.warning(f"Operation {operation} failed: {e}")

        measurement = LatencyMeasurement(
            operation=operation,
            start_time=start_time,
            end_time=end_time,
            success=success,
            metadata=metadata,
        )

        async with self.lock:
            self.latency_history.append(measurement)
            if operation not in self.operation_stats:
                self.operation_stats[operation] = []
            self.operation_stats[operation].append(measurement.duration)

        return result, measurement

    async def measure_sync_latency(
        self,
        operation: str,
        func: Callable[..., Any],
        *args: Any,
        **kwargs: Any,
    ) -> tuple[Any, LatencyMeasurement]:
        """Measure latency of a sync function."""
        start_time = time.perf_counter()
        metadata = kwargs.pop("_metadata", {})

        try:
            result = await asyncio.to_thread(func, *args, **kwargs)
            end_time = time.perf_counter()
            success = True
        except Exception as e:
            end_time = time.perf_counter()
            result = None
            success = False
            metadata["error"] = str(e)
            logger.warning(f"Operation {operation} failed: {e}")

        measurement = LatencyMeasurement(
            operation=operation,
            start_time=start_time,
            end_time=end_time,
            success=success,
            metadata=metadata,
        )

        async with self.lock:
            self.latency_history.append(measurement)
            if operation not in self.operation_stats:
                self.operation_stats[operation] = []
            self.operation_stats[operation].append(measurement.duration)

        return result, measurement

    def get_statistics(self, operation: str | None = None) -> dict[str, Any]:
        """Get statistics for a specific operation or all operations."""
        if operation:
            durations = self.operation_stats.get(operation, [])
            if not durations:
                return {"operation": operation, "count": 0}
            return {
                "operation": operation,
                "count": len(durations),
                "min": min(durations),
                "max": max(durations),
                "mean": statistics.mean(durations),
                "median": statistics.median(durations),
                "std_dev": statistics.stdev(durations) if len(durations) > 1 else 0,
                "p95": np.percentile(durations, 95),
                "p99": np.percentile(durations, 99),
            }
        else:
            stats = {}
            for op, durations in self.operation_stats.items():
                if durations:
                    stats[op] = {
                        "count": len(durations),
                        "min": min(durations),
                        "max": max(durations),
                        "mean": statistics.mean(durations),
                        "median": statistics.median(durations),
                        "std_dev": (
                            statistics.stdev(durations) if len(durations) > 1 else 0
                        ),
                        "p95": np.percentile(durations, 95),
                        "p99": np.percentile(durations, 99),
                    }
                else:
                    stats[op] = {"count": 0}
            return stats

    def validate_cmp_latency_gates(
        self,
        p1_threshold: float = 0.001,  # 1ms for P1
        p5_threshold: float = 0.005,  # 5ms for P5
    ) -> dict[str, Any]:
        """Validate CMP P1/P5 latency gates."""
        stats = self.get_statistics()

        validation_results = {}
        for operation, metrics in stats.items():
            if metrics["count"] == 0:
                continue

            p1_pass = metrics["p95"] <= p1_threshold
            p5_pass = metrics["p99"] <= p5_threshold

            validation_results[operation] = {
                "p1_threshold": p1_threshold,
                "p1_actual": metrics["p95"],
                "p1_pass": p1_pass,
                "p5_threshold": p5_threshold,
                "p5_actual": metrics["p99"],
                "p5_pass": p5_pass,
                "overall_pass": p1_pass and p5_pass,
            }

        return validation_results

    def get_recent_measurements(self, limit: int = 100) -> list[dict[str, Any]]:
        """Get recent latency measurements."""
        return [m.to_dict() for m in list(self.latency_history)[:limit]]

    def clear_history(self) -> None:
        """Clear measurement history."""
        self.latency_history.clear()
        self.operation_stats.clear()


class DatabasePerformanceAnalyzer:
    """Specialized analyzer for database operations."""

    def __init__(self, db: Database):
        self.db = db
        self.analyzer = PerformanceAnalyzer()

    async def measure_database_operations(
        self, iterations: int = 100
    ) -> dict[str, Any]:
        """Measure comprehensive database operation latencies."""

        # Test async operations
        async def test_async_create_signal() -> Any:
            signal = Signal(
                signal_id=f"test_{int(time.time() * 1000)}",
                symbol="NIFTY",
                signal_type=SignalType.BUY,
                strength=0.8,
                timestamp=datetime.now(UTC),
                indicators={"rsi": 70.0},
                metadata={"test": "latency"},
            )
            return await self.db.async_create_signal(signal)

        async def test_async_store_historical() -> Any:
            data = [
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
            return await self.db.async_store_historical_data(data)

        async def test_async_get_signals() -> Any:
            return await self.db.async_get_latest_signals("NIFTY", limit=10)

        # Test sync operations
        def test_sync_create_signal() -> Any:
            signal = Signal(
                signal_id=f"test_{int(time.time() * 1000)}",
                symbol="NIFTY",
                signal_type=SignalType.BUY,
                strength=0.8,
                timestamp=datetime.now(UTC),
                indicators={"rsi": 70.0},
                metadata={"test": "latency"},
            )
            return self.db.create_signal(signal)

        def test_sync_store_historical() -> Any:
            data = [
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
            return self.db.store_historical_data(data)

        def test_sync_get_signals() -> Any:
            return self.db.get_latest_signals("NIFTY", limit=10)

        # Run measurements
        for i in range(iterations):
            # Async operations
            await self.analyzer.measure_latency(
                f"async_create_signal_{i}",
                test_async_create_signal,
                _metadata={"iteration": i, "operation_type": "async_write"},
            )

            await self.analyzer.measure_latency(
                f"async_store_historical_{i}",
                test_async_store_historical,
                _metadata={"iteration": i, "operation_type": "async_write"},
            )

            await self.analyzer.measure_latency(
                f"async_get_signals_{i}",
                test_async_get_signals,
                _metadata={"iteration": i, "operation_type": "async_read"},
            )

            # Sync operations
            await self.analyzer.measure_sync_latency(
                f"sync_create_signal_{i}",
                test_sync_create_signal,
                _metadata={"iteration": i, "operation_type": "sync_write"},
            )

            await self.analyzer.measure_sync_latency(
                f"sync_store_historical_{i}",
                test_sync_store_historical,
                _metadata={"iteration": i, "operation_type": "sync_write"},
            )

            await self.analyzer.measure_sync_latency(
                f"sync_get_signals_{i}",
                test_sync_get_signals,
                _metadata={"iteration": i, "operation_type": "sync_read"},
            )

        return self.analyzer.get_statistics()

    async def measure_analyze_round_trip(self, data_size: int = 1000) -> dict[str, Any]:
        """Measure ANALYZE round-trip latency with realistic data."""
        # Generate test data
        test_data = self._generate_test_data(data_size)

        # Measure TA calculation
        ta = TechnicalAnalysis()

        async def measure_ta_calculation() -> int:
            indicators = await asyncio.to_thread(ta.calculate_indicators, test_data)
            return len(indicators)

        # Measure database operations
        async def measure_db_operations() -> int:
            # Store historical data
            await self.db.async_store_historical_data(test_data)
            # Get signals
            signals = await self.db.async_get_latest_signals("TEST", limit=10)
            return len(signals)

        # Run measurements
        ta_result, ta_measurement = await self.analyzer.measure_latency(
            "ta_calculation", measure_ta_calculation, _metadata={"data_size": data_size}
        )

        db_result, db_measurement = await self.analyzer.measure_latency(
            "db_operations", measure_db_operations, _metadata={"data_size": data_size}
        )

        # Calculate round-trip
        round_trip_duration = ta_measurement.duration + db_measurement.duration

        return {
            "ta_calculation": ta_measurement.to_dict(),
            "db_operations": db_measurement.to_dict(),
            "round_trip": {
                "duration": round_trip_duration,
                "ta_percentage": ta_measurement.duration / round_trip_duration * 100,
                "db_percentage": db_measurement.duration / round_trip_duration * 100,
            },
            "data_size": data_size,
            "ta_result": ta_result,
            "db_result": db_result,
        }

    def _generate_test_data(self, size: int) -> list[HistoricalData]:
        """Generate test historical data."""
        base_time = datetime.now(UTC)
        data = []

        for i in range(size):
            timestamp = base_time - timedelta(minutes=size - i)
            price = 100.0 + np.random.normal(0, 0.5)
            data.append(
                HistoricalData(
                    symbol="TEST",
                    timestamp=timestamp,
                    open=price,
                    high=price + np.random.uniform(0, 0.5),
                    low=price - np.random.uniform(0, 0.5),
                    close=price + np.random.normal(0, 0.1),
                    volume=np.random.randint(1000, 5000),
                    interval="1min",
                )
            )

        return data


# Global performance analyzer instance
performance_analyzer = PerformanceAnalyzer()


async def run_comprehensive_analysis(db: Database) -> dict[str, Any]:
    """Run comprehensive performance analysis."""
    logger.info("Starting comprehensive performance analysis")

    # Create database performance analyzer
    db_performance_analyzer = DatabasePerformanceAnalyzer(db)

    # Database operations analysis
    db_results = await db_performance_analyzer.measure_database_operations(
        iterations=50
    )
    logger.info(f"Database analysis complete: {len(db_results)} operations measured")

    # ANALYZE round-trip analysis
    analyze_results = await db_performance_analyzer.measure_analyze_round_trip(
        data_size=500
    )
    logger.info(
        f"ANALYZE round-trip complete: {analyze_results['round_trip']['duration']:.4f}s"
    )

    # CMP latency validation
    validation_results = performance_analyzer.validate_cmp_latency_gates()
    logger.info(
        f"CMP validation complete: {len(validation_results)} operations validated"
    )

    return {
        "database_operations": db_results,
        "analyze_round_trip": analyze_results,
        "cmp_validation": validation_results,
        "timestamp": datetime.now(UTC).isoformat(),
    }


async def run_latency_benchmark(db: Database) -> dict[str, Any]:
    """Run focused latency benchmark for CMP P1/P5 validation."""
    logger.info("Starting CMP P1/P5 latency benchmark")

    # Test 1: Signal creation and retrieval
    async def test_signal_round_trip() -> int:
        # Create signal
        signal = Signal(
            signal_id=f"benchmark_{int(time.time() * 1000)}",
            symbol="NIFTY",
            signal_type=SignalType.BUY,
            strength=0.8,
            timestamp=datetime.now(UTC),
            indicators={"rsi": 70.0, "macd": 0.5},
            metadata={"benchmark": "p1_p5"},
        )
        await db.async_create_signal(signal)

        # Retrieve signal
        signals = await db.async_get_latest_signals("NIFTY", limit=1)
        return len(signals)

    # Test 2: Historical data processing
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
        await db.async_store_historical_data(test_data)

        # Calculate indicators
        ta = TechnicalAnalysis()
        indicators = await asyncio.to_thread(ta.calculate_indicators, test_data)
        return len(indicators)

    # Run multiple iterations
    iterations = 100
    for i in range(iterations):
        await performance_analyzer.measure_latency(
            f"signal_round_trip_{i}",
            test_signal_round_trip,
            _metadata={"iteration": i, "test_type": "signal"},
        )

        await performance_analyzer.measure_latency(
            f"historical_processing_{i}",
            test_historical_processing,
            _metadata={"iteration": i, "test_type": "historical"},
        )

    # Get statistics
    stats = performance_analyzer.get_statistics()

    # Validate CMP gates
    validation = performance_analyzer.validate_cmp_latency_gates(
        p1_threshold=0.001,  # 1ms
        p5_threshold=0.005,  # 5ms
    )

    return {
        "statistics": stats,
        "validation": validation,
        "iterations": iterations,
        "timestamp": datetime.now(UTC).isoformat(),
    }


# Module-level exports
analyzer = performance_analyzer
