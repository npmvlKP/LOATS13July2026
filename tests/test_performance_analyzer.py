"""
Comprehensive tests for performance_analyzer.py module.
Tests all classes and functions to achieve 100% coverage.
"""

import asyncio
import time
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.loats.database import Database
from src.loats.models import HistoricalData
from src.loats.performance_analyzer import (
    DatabasePerformanceAnalyzer,
    LatencyMeasurement,
    PerformanceAnalyzer,
    performance_analyzer,
    run_comprehensive_analysis,
    run_latency_benchmark,
)


class TestLatencyMeasurement:
    """Test LatencyMeasurement class."""

    def test_latency_measurement_initialization(self):
        """Test LatencyMeasurement initialization."""
        measurement = LatencyMeasurement(
            operation="test_op",
            start_time=1.0,
            end_time=2.0,
            success=True,
            metadata={"key": "value"},
        )

        assert measurement.operation == "test_op"
        assert measurement.start_time == 1.0
        assert measurement.end_time == 2.0
        assert measurement.duration == 1.0
        assert measurement.success is True
        assert measurement.metadata == {"key": "value"}
        assert isinstance(measurement.timestamp, datetime)

    def test_latency_measurement_to_dict(self):
        """Test LatencyMeasurement to_dict method."""
        measurement = LatencyMeasurement(
            operation="test_op",
            start_time=1.0,
            end_time=2.0,
            success=True,
            metadata={"key": "value"},
        )

        result = measurement.to_dict()
        assert result["operation"] == "test_op"
        assert result["start_time"] == 1.0
        assert result["end_time"] == 2.0
        assert result["duration"] == 1.0
        assert result["success"] is True
        assert result["metadata"] == {"key": "value"}
        assert "timestamp" in result

    def test_latency_measurement_default_metadata(self):
        """Test LatencyMeasurement with default metadata."""
        measurement = LatencyMeasurement(
            operation="test_op", start_time=1.0, end_time=2.0, success=True
        )

        assert measurement.metadata == {}


class TestPerformanceAnalyzer:
    """Test PerformanceAnalyzer class."""

    def test_performance_analyzer_initialization(self):
        """Test PerformanceAnalyzer initialization."""
        analyzer = PerformanceAnalyzer(max_history=100)
        assert analyzer.max_history == 100
        assert len(analyzer.latency_history) == 0
        assert analyzer.operation_stats == {}

    @pytest.mark.asyncio
    async def test_measure_latency_success(self):
        """Test measure_latency with successful async function."""
        analyzer = PerformanceAnalyzer()

        async def test_func(x, y):
            await asyncio.sleep(0.001)
            return x + y

        result, measurement = await analyzer.measure_latency("test_op", test_func, 1, 2)

        assert result == 3
        assert measurement.operation == "test_op"
        assert measurement.success is True
        assert measurement.duration > 0
        assert len(analyzer.latency_history) == 1
        assert "test_op" in analyzer.operation_stats

    @pytest.mark.asyncio
    async def test_measure_latency_failure(self):
        """Test measure_latency with failing async function."""
        analyzer = PerformanceAnalyzer()

        async def test_func():
            raise ValueError("Test error")

        result, measurement = await analyzer.measure_latency("test_op", test_func)

        assert result is None
        assert measurement.operation == "test_op"
        assert measurement.success is False
        assert "error" in measurement.metadata
        assert len(analyzer.latency_history) == 1

    @pytest.mark.asyncio
    async def test_measure_sync_latency_success(self):
        """Test measure_sync_latency with successful sync function."""
        analyzer = PerformanceAnalyzer()

        def test_func(x, y):
            time.sleep(0.001)
            return x + y

        result, measurement = await analyzer.measure_sync_latency(
            "test_op", test_func, 1, 2
        )

        assert result == 3
        assert measurement.operation == "test_op"
        assert measurement.success is True
        assert measurement.duration > 0

    @pytest.mark.asyncio
    async def test_measure_sync_latency_failure(self):
        """Test measure_sync_latency with failing sync function."""
        analyzer = PerformanceAnalyzer()

        def test_func():
            raise ValueError("Test error")

        result, measurement = await analyzer.measure_sync_latency("test_op", test_func)

        assert result is None
        assert measurement.operation == "test_op"
        assert measurement.success is False
        assert "error" in measurement.metadata

    def test_get_statistics_single_operation(self):
        """Test get_statistics for single operation."""
        analyzer = PerformanceAnalyzer()

        # Add some measurements
        for i in range(5):
            measurement = LatencyMeasurement(
                operation="test_op",
                start_time=1.0,
                end_time=1.0 + i * 0.001,
                success=True,
            )
            analyzer.latency_history.append(measurement)
            analyzer.operation_stats["test_op"] = [i * 0.001 for i in range(5)]

        stats = analyzer.get_statistics("test_op")

        assert stats["operation"] == "test_op"
        assert stats["count"] == 5
        assert stats["min"] == 0.0
        assert stats["max"] == 0.004
        assert "mean" in stats
        assert "median" in stats
        assert "std_dev" in stats
        assert "p95" in stats
        assert "p99" in stats

    def test_get_statistics_all_operations(self):
        """Test get_statistics for all operations."""
        analyzer = PerformanceAnalyzer()

        # Add measurements for multiple operations
        for op in ["op1", "op2"]:
            for i in range(3):
                measurement = LatencyMeasurement(
                    operation=op, start_time=1.0, end_time=1.0 + i * 0.001, success=True
                )
                analyzer.latency_history.append(measurement)
                analyzer.operation_stats[op] = [i * 0.001 for i in range(3)]

        stats = analyzer.get_statistics()

        assert "op1" in stats
        assert "op2" in stats
        assert stats["op1"]["count"] == 3
        assert stats["op2"]["count"] == 3

    def test_get_statistics_empty_operation(self):
        """Test get_statistics for operation with no data."""
        analyzer = PerformanceAnalyzer()
        stats = analyzer.get_statistics("nonexistent_op")

        assert stats["operation"] == "nonexistent_op"
        assert stats["count"] == 0

    def test_validate_cmp_latency_gates(self):
        """Test validate_cmp_latency_gates method."""
        analyzer = PerformanceAnalyzer()

        # Add some measurements
        for i in range(10):
            measurement = LatencyMeasurement(
                operation="test_op",
                start_time=1.0,
                end_time=1.0 + i * 0.0001,  # 0.1ms increments
                success=True,
            )
            analyzer.latency_history.append(measurement)
            analyzer.operation_stats["test_op"] = [i * 0.0001 for i in range(10)]

        validation = analyzer.validate_cmp_latency_gates(
            p1_threshold=0.001,
            p5_threshold=0.005,  # 1ms  # 5ms
        )

        assert "test_op" in validation
        assert validation["test_op"]["p1_threshold"] == 0.001
        assert validation["test_op"]["p5_threshold"] == 0.005
        assert "p1_actual" in validation["test_op"]
        assert "p5_actual" in validation["test_op"]
        assert "p1_pass" in validation["test_op"]
        assert "p5_pass" in validation["test_op"]
        assert "overall_pass" in validation["test_op"]

    def test_get_recent_measurements(self):
        """Test get_recent_measurements method."""
        analyzer = PerformanceAnalyzer(max_history=5)

        # Add measurements
        for i in range(10):
            measurement = LatencyMeasurement(
                operation=f"op_{i}", start_time=1.0, end_time=2.0, success=True
            )
            analyzer.latency_history.append(measurement)

        # Should only keep last 5 due to maxlen
        recent = analyzer.get_recent_measurements()
        assert len(recent) == 5
        assert all(isinstance(m, dict) for m in recent)

    def test_get_recent_measurements_limit(self):
        """Test get_recent_measurements with limit."""
        analyzer = PerformanceAnalyzer()

        # Add measurements
        for i in range(10):
            measurement = LatencyMeasurement(
                operation=f"op_{i}", start_time=1.0, end_time=2.0, success=True
            )
            analyzer.latency_history.append(measurement)

        recent = analyzer.get_recent_measurements(limit=3)
        assert len(recent) == 3

    def test_clear_history(self):
        """Test clear_history method."""
        analyzer = PerformanceAnalyzer()

        # Add measurements
        measurement = LatencyMeasurement(
            operation="test_op", start_time=1.0, end_time=2.0, success=True
        )
        analyzer.latency_history.append(measurement)
        analyzer.operation_stats["test_op"] = [1.0]

        analyzer.clear_history()

        assert len(analyzer.latency_history) == 0
        assert analyzer.operation_stats == {}


class TestDatabasePerformanceAnalyzer:
    """Test DatabasePerformanceAnalyzer class."""

    @pytest.fixture
    def mock_db(self):
        """Create mock database."""
        mock_db = MagicMock(spec=Database)

        # Mock async methods
        mock_db.async_create_signal = AsyncMock()
        mock_db.async_store_historical_data = AsyncMock()
        mock_db.async_get_latest_signals = AsyncMock(return_value=[])

        # Mock sync methods
        mock_db.create_signal = MagicMock()
        mock_db.store_historical_data = MagicMock()
        mock_db.get_latest_signals = MagicMock(return_value=[])

        return mock_db

    def test_database_performance_analyzer_initialization(self, mock_db):
        """Test DatabasePerformanceAnalyzer initialization."""
        analyzer = DatabasePerformanceAnalyzer(mock_db)
        assert analyzer.db == mock_db
        assert isinstance(analyzer.analyzer, PerformanceAnalyzer)

    @pytest.mark.asyncio
    async def test_measure_database_operations(self, mock_db):
        """Test measure_database_operations method."""
        analyzer = DatabasePerformanceAnalyzer(mock_db)

        # Mock the database methods to return successfully
        mock_db.async_create_signal.return_value = True
        mock_db.async_store_historical_data.return_value = True
        mock_db.async_get_latest_signals.return_value = []
        mock_db.create_signal.return_value = True
        mock_db.store_historical_data.return_value = True
        mock_db.get_latest_signals.return_value = []

        # Run with small iterations for testing
        result = await analyzer.measure_database_operations(iterations=2)

        # Should have statistics for all operations
        assert "async_create_signal_0" in result
        assert "async_store_historical_0" in result
        assert "async_get_signals_0" in result
        assert "sync_create_signal_0" in result
        assert "sync_store_historical_0" in result
        assert "sync_get_signals_0" in result

        # Check that database methods were called
        assert mock_db.async_create_signal.call_count == 2
        assert mock_db.async_store_historical_data.call_count == 2
        assert mock_db.async_get_latest_signals.call_count == 2
        assert mock_db.create_signal.call_count == 2
        assert mock_db.store_historical_data.call_count == 2
        assert mock_db.get_latest_signals.call_count == 2

    @pytest.mark.asyncio
    async def test_measure_analyze_round_trip(self, mock_db):
        """Test measure_analyze_round_trip method."""
        analyzer = DatabasePerformanceAnalyzer(mock_db)

        # Mock database methods
        mock_db.async_store_historical_data.return_value = True
        mock_db.async_get_latest_signals.return_value = []

        result = await analyzer.measure_analyze_round_trip(data_size=10)

        assert "ta_calculation" in result
        assert "db_operations" in result
        assert "round_trip" in result
        assert "data_size" in result
        assert result["data_size"] == 10

        # Check that round trip calculation is correct
        ta_duration = result["ta_calculation"]["duration"]
        db_duration = result["db_operations"]["duration"]
        round_trip = result["round_trip"]["duration"]

        assert (
            abs(round_trip - (ta_duration + db_duration)) < 0.001
        )  # Allow small floating point difference

    def test_generate_test_data(self, mock_db):
        """Test _generate_test_data method."""
        analyzer = DatabasePerformanceAnalyzer(mock_db)
        test_data = analyzer._generate_test_data(size=5)

        assert len(test_data) == 5
        assert all(isinstance(item, HistoricalData) for item in test_data)

        # Check that data has reasonable values
        for item in test_data:
            assert item.symbol == "TEST"
            assert isinstance(item.timestamp, datetime)
            assert item.open > 0
            assert item.high >= item.open
            assert item.low <= item.open
            assert item.volume > 0
            assert item.interval == "1min"


@pytest.mark.asyncio
async def test_run_comprehensive_analysis():
    """Test run_comprehensive_analysis function."""
    # Mock the database methods
    mock_db = MagicMock(spec=Database)
    mock_db.async_create_signal = AsyncMock(return_value=True)
    mock_db.async_store_historical_data = AsyncMock(return_value=True)
    mock_db.async_get_latest_signals = AsyncMock(return_value=[])

    result = await run_comprehensive_analysis(mock_db)

    assert "database_operations" in result
    assert "analyze_round_trip" in result
    assert "cmp_validation" in result
    assert "timestamp" in result

    # Check that database operations were measured
    db_ops = result["database_operations"]
    assert len(db_ops) > 0  # Should have measured multiple operations

    # Check that analyze round trip was measured
    analyze = result["analyze_round_trip"]
    assert "round_trip" in analyze
    assert "ta_calculation" in analyze
    assert "db_operations" in analyze

    # Check that CMP validation was performed
    validation = result["cmp_validation"]
    assert isinstance(validation, dict)


@pytest.mark.asyncio
async def test_run_latency_benchmark():
    """Test run_latency_benchmark function."""
    # Mock the database methods
    mock_db = MagicMock(spec=Database)
    mock_db.async_create_signal = AsyncMock(return_value=True)
    mock_db.async_store_historical_data = AsyncMock(return_value=True)
    mock_db.async_get_latest_signals = AsyncMock(return_value=[])

    # Mock TechnicalAnalysis
    with patch("src.loats.performance_analyzer.TechnicalAnalysis") as mock_ta:
        mock_ta_instance = MagicMock()
        mock_ta.return_value = mock_ta_instance
        mock_ta_instance.calculate_indicators.return_value = {}

        result = await run_latency_benchmark(mock_db)

        assert "statistics" in result
        assert "validation" in result
        assert "iterations" in result
        assert "timestamp" in result
        assert result["iterations"] == 100

        # Check that statistics were collected
        stats = result["statistics"]
        assert len(stats) > 0

        # Check that validation was performed
        validation = result["validation"]
        assert isinstance(validation, dict)


def test_global_performance_analyzer_instance():
    """Test that global performance_analyzer instance exists."""
    from src.loats.performance_analyzer import performance_analyzer

    assert isinstance(performance_analyzer, PerformanceAnalyzer)


def test_analyzer_alias():
    """Test that analyzer alias points to performance_analyzer."""
    from src.loats.performance_analyzer import analyzer

    assert analyzer is performance_analyzer


class TestPerformanceAnalyzerEdgeCases:
    """Test edge cases for PerformanceAnalyzer."""

    @pytest.mark.asyncio
    async def test_measure_latency_with_metadata(self):
        """Test measure_latency with custom metadata."""
        analyzer = PerformanceAnalyzer()

        async def test_func():
            return "success"

        result, measurement = await analyzer.measure_latency(
            "test_op", test_func, _metadata={"custom": "metadata"}
        )

        assert result == "success"
        assert measurement.metadata["custom"] == "metadata"

    @pytest.mark.asyncio
    async def test_measure_latency_with_args_kwargs(self):
        """Test measure_latency with various args and kwargs."""
        analyzer = PerformanceAnalyzer()

        async def test_func(a, b, c=10, d=20):
            return a + b + c + d

        result, measurement = await analyzer.measure_latency(
            "test_op", test_func, 1, 2, c=30, d=40
        )

        assert result == 73  # 1 + 2 + 30 + 40
        assert measurement.success is True

    def test_get_statistics_empty_analyzer(self):
        """Test get_statistics with empty analyzer."""
        analyzer = PerformanceAnalyzer()
        stats = analyzer.get_statistics()
        assert stats == {}

    def test_validate_cmp_latency_gates_no_data(self):
        """Test validate_cmp_latency_gates with no data."""
        analyzer = PerformanceAnalyzer()
        validation = analyzer.validate_cmp_latency_gates()
        assert validation == {}

    def test_get_recent_measurements_empty(self):
        """Test get_recent_measurements with empty history."""
        analyzer = PerformanceAnalyzer()
        recent = analyzer.get_recent_measurements()
        assert recent == []


class TestPerformanceAnalyzerConcurrency:
    """Test concurrency aspects of PerformanceAnalyzer."""

    @pytest.mark.asyncio
    async def test_concurrent_measurements(self):
        """Test that concurrent measurements work correctly."""
        analyzer = PerformanceAnalyzer()

        async def test_func():
            await asyncio.sleep(0.001)
            return "success"

        # Run multiple measurements concurrently
        tasks = []
        for i in range(10):
            task = analyzer.measure_latency(f"op_{i}", test_func)
            tasks.append(task)

        results = await asyncio.gather(*tasks)

        # All should succeed
        for result, measurement in results:
            assert result == "success"
            assert measurement.success is True

        # Should have 10 measurements
        assert len(analyzer.latency_history) == 10

    @pytest.mark.asyncio
    async def test_lock_protects_shared_state(self):
        """Test that lock protects shared state during concurrent access."""
        analyzer = PerformanceAnalyzer()

        async def add_measurement(i):
            async def dummy_func():
                return i

            await analyzer.measure_latency(f"op_{i}", dummy_func)

        # Run many concurrent operations
        await asyncio.gather(*[add_measurement(i) for i in range(100)])

        # Should have exactly 100 measurements
        assert len(analyzer.latency_history) == 100
        assert len(analyzer.operation_stats) == 100  # Each has unique operation name
