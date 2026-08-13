"""Performance and load testing benchmarks for LOATS13July2026.

This module provides comprehensive performance benchmarks for:
- Database operations latency
- API response times
- Technical analysis calculations
- Cache performance
- Concurrent request handling
"""

import asyncio
import threading
import time
from collections.abc import Generator
from datetime import datetime, timedelta
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

from loats.database import Database
from loats.models import ProductType, Trade, TransactionType
from loats.ta import calculate_rsi, calculate_supertrend
from loats.utils.cache import cache_manager


@pytest.fixture
def test_db() -> Generator[Database, None, None]:
    """Create test database with sample data."""
    import tempfile
    from pathlib import Path

    # Use ignore_cleanup_errors=True to handle file permission issues on Windows
    # when SQLite connections from other threads are still active during cleanup
    temp_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
    try:
        temp_path = Path(temp_dir.name)
        db = Database(
            db_path=temp_path / "test_perf.db",
            audit_log_path=temp_path / "test_audit.log",
        )
        db.retention_days = 30
        db._initialize_database()
        yield db
        # Ensure ALL database connections are properly closed to prevent file permission issues
        # Use ignore_errors=True to handle SQLite thread affinity issues during cleanup
        try:
            db.close_all()
        except Exception:
            pass  # Ignore errors during cleanup

        # Additional cleanup: try to close current thread connection and clear registry
        try:
            db.close()
        except Exception:
            pass

        # Clear thread registry to prevent potential issues
        try:
            with db._registry_lock:
                db._thread_registry.clear()
        except Exception:
            pass
    finally:
        # Clean up the temporary directory
        try:
            temp_dir.cleanup()
        except Exception:
            pass  # Ignore cleanup errors


class TestDatabasePerformance:
    """Benchmark database operations performance."""

    def test_database_insert_performance(self, test_db: Database) -> None:
        """Benchmark trade insert performance."""
        trades = []
        for i in range(1000):
            trade = Trade(
                symbol=f"TEST{i}",
                quantity=10,
                entry_price=100.0 + i,
                entry_time=datetime.now() - timedelta(days=i),
                transaction_type=TransactionType.BUY,
                product_type=ProductType.MIS,
                strategy="test_strategy",
                stop_loss=95.0,
                take_profit=110.0,
                trailing_stop_loss=5.0,
            )
            trades.append(trade)

        start_time = time.time()
        for trade in trades:
            test_db.create_trade(trade)
        end_time = time.time()

        insert_time = end_time - start_time
        inserts_per_second = len(trades) / insert_time

        print(f"Database insert performance: {inserts_per_second:.2f} inserts/sec")
        assert inserts_per_second > 100, (
            f"Database insert performance too slow: {inserts_per_second:.2f} inserts/sec (expected > 100)"
        )

    def test_database_query_performance(self, test_db: Database) -> None:
        """Benchmark trade query performance."""
        # Insert test data
        for i in range(100):
            trade = Trade(
                symbol=f"TEST{i}",
                quantity=10,
                entry_price=100.0 + i,
                entry_time=datetime.now() - timedelta(days=i),
                transaction_type=TransactionType.BUY,
                product_type=ProductType.MIS,
                strategy="test_strategy",
                stop_loss=95.0,
                take_profit=110.0,
                trailing_stop_loss=5.0,
            )
            test_db.create_trade(trade)

        # Benchmark query
        start_time = time.time()
        _ = test_db.get_trades(symbol="TEST50")  # Measure query performance
        end_time = time.time()

        query_time = end_time - start_time
        print(f"Database query performance: {query_time:.4f} seconds")
        assert query_time < 0.05, (
            f"Database query too slow: {query_time:.4f} seconds (expected < 0.05)"
        )


class TestTechnicalAnalysisPerformance:
    """Benchmark technical analysis calculations performance."""

    def test_supertrend_performance(self) -> None:
        """Benchmark supertrend calculation with large datasets."""
        data_sizes = [1000, 5000, 10000, 20000]

        for size in data_sizes:
            # Generate test data
            np.random.seed(42)
            prices = np.cumsum(np.random.normal(0, 0.5, size)) + 100.0
            data = {
                "timestamp": pd.date_range("2023-01-01", periods=size, freq="1min"),
                "open": prices,
                "high": prices + np.abs(np.random.normal(0, 0.2, size)),
                "low": prices - np.abs(np.random.normal(0, 0.2, size)),
                "close": prices,
                "volume": np.random.randint(1000, 5000, size),
            }
            df = pd.DataFrame(data)

            # Benchmark calculation
            start_time = time.time()
            supertrend, direction = calculate_supertrend(df)
            end_time = time.time()

            calc_time = end_time - start_time
            time_per_point = (calc_time / size) * 1_000_000  # microseconds

            print(
                f"Supertrend {size} points: {calc_time:.4f}s ({time_per_point:.2f} μs/point)"
            )
            # More precise thresholds based on data size - adjusted for actual performance
            expected_max_time = 1.0 + (
                size / 30000
            )  # Scale with data size, realistic baseline
            assert calc_time < expected_max_time, (
                f"Supertrend calculation too slow for {size} points: {calc_time:.4f}s (expected < {expected_max_time:.4f})"
            )

    def test_rsi_performance(self) -> None:
        """Benchmark RSI calculation performance."""
        data_sizes = [1000, 5000, 10000]

        for size in data_sizes:
            # Generate test data
            np.random.seed(42)
            prices = np.cumsum(np.random.normal(0, 0.5, size)) + 100.0
            data = {
                "timestamp": pd.date_range("2023-01-01", periods=size, freq="1min"),
                "close": prices,
            }
            df = pd.DataFrame(data)

            # Benchmark calculation
            start_time = time.time()
            _ = calculate_rsi(df, period=14)  # Measure RSI calculation time
            end_time = time.time()

            calc_time = end_time - start_time
            time_per_point = (calc_time / size) * 1_000_000  # microseconds

            print(
                f"RSI {size} points: {calc_time:.4f}s ({time_per_point:.2f} μs/point)"
            )
            # More precise thresholds based on data size
            expected_max_time = 0.05 + (size / 50000)  # Scale with data size
            assert calc_time < expected_max_time, (
                f"RSI calculation too slow for {size} points: {calc_time:.4f}s (expected < {expected_max_time:.4f})"
            )


class TestCachePerformance:
    """Benchmark cache operations performance."""

    @pytest.mark.asyncio
    async def test_cache_latency(self) -> None:
        """Benchmark cache read/write latency."""
        await cache_manager.initialize()

        # Test write performance
        start_time = time.time()
        for i in range(1000):
            await cache_manager.set(f"test_key_{i}", {"value": i}, ttl=60)
        end_time = time.time()

        write_time = max(end_time - start_time, 0.001)  # Ensure minimum measurable time
        writes_per_second = 1000 / write_time

        print(f"Cache write performance: {writes_per_second:.2f} writes/sec")

        # Test read performance
        start_time = time.time()
        for i in range(1000):
            await cache_manager.get(f"test_key_{i}")
        end_time = time.time()

        read_time = max(end_time - start_time, 0.001)  # Ensure minimum measurable time
        reads_per_second = 1000 / read_time

        print(f"Cache read performance: {reads_per_second:.2f} reads/sec")

        # Cleanup
        for i in range(1000):
            await cache_manager.delete(f"test_key_{i}")

        assert writes_per_second > 5000, (
            f"Cache write performance too slow: {writes_per_second:.2f} writes/sec (expected > 5000)"
        )
        assert reads_per_second > 10000, (
            f"Cache read performance too slow: {reads_per_second:.2f} reads/sec (expected > 10000)"
        )


class TestConcurrentPerformance:
    """Benchmark concurrent operations performance."""

    def test_concurrent_database_operations(self, test_db: Database) -> None:
        """Benchmark concurrent database operations."""

        def insert_trades(db: Database, start_id: int, count: int) -> None:
            for i in range(start_id, start_id + count):
                trade = Trade(
                    symbol=f"CONC{i}",
                    quantity=10,
                    entry_price=100.0 + i,
                    entry_time=datetime.now() - timedelta(days=i),
                    transaction_type=TransactionType.BUY,
                    product_type=ProductType.MIS,
                    strategy="concurrent_test",
                    stop_loss=95.0,
                    take_profit=110.0,
                    trailing_stop_loss=5.0,
                )
                db.create_trade(trade)

        # Run concurrent inserts
        threads = []
        start_time = time.time()

        for thread_id in range(4):
            thread = threading.Thread(
                target=insert_trades, args=(test_db, thread_id * 250, 250)
            )
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join()

        end_time = time.time()

        concurrent_time = end_time - start_time
        total_inserts = 1000
        inserts_per_second = total_inserts / concurrent_time

        print(f"Concurrent database operations: {inserts_per_second:.2f} inserts/sec")
        assert inserts_per_second > 200, (
            f"Concurrent database performance too slow: {inserts_per_second:.2f} inserts/sec (expected > 200)"
        )

    @pytest.mark.asyncio
    async def test_concurrent_cache_operations(self) -> None:
        """Benchmark concurrent cache operations."""
        await cache_manager.initialize()

        async def cache_operations(start_id: int, count: int) -> None:
            for i in range(start_id, start_id + count):
                await cache_manager.set(f"concurrent_key_{i}", {"value": i}, ttl=60)
                await cache_manager.get(f"concurrent_key_{i}")

        # Run concurrent cache operations
        tasks = []
        start_time = time.time()

        for task_id in range(4):
            task = asyncio.create_task(cache_operations(task_id * 250, 250))
            tasks.append(task)

        await asyncio.gather(*tasks)
        end_time = time.time()

        concurrent_time = end_time - start_time
        total_operations = 2000  # 1000 writes + 1000 reads
        operations_per_second = total_operations / concurrent_time

        print(f"Concurrent cache operations: {operations_per_second:.2f} ops/sec")

        # Cleanup
        for i in range(1000):
            await cache_manager.delete(f"concurrent_key_{i}")

        assert operations_per_second > 10000, (
            f"Concurrent cache performance too slow: {operations_per_second:.2f} ops/sec (expected > 10000)"
        )


class TestAPILatency:
    """Benchmark API response times."""

    @pytest.mark.asyncio
    async def test_api_response_time(self) -> None:
        """Benchmark API response times with mock data."""
        from loats.openalgo import async_client

        # Mock the async client
        with patch("loats.openalgo.async_client.get_quotes") as mock_get_quotes:
            mock_get_quotes.return_value = {
                "status": "success",
                "data": {
                    "NIFTY": {"last_price": 19500.25},
                    "BANKNIFTY": {"last_price": 43200.50},
                },
            }

            start_time = time.time()
            result = await async_client.get_quotes(["NIFTY", "BANKNIFTY"])
            end_time = time.time()

            response_time = end_time - start_time
            print(f"API response time: {response_time:.4f} seconds")

            assert response_time < 0.1, (
                f"API response too slow: {response_time:.4f} seconds (expected < 0.1)"
            )
            assert result["status"] == "success"

    @pytest.mark.asyncio
    async def test_batch_api_performance(self) -> None:
        """Benchmark batch API operations."""
        from loats.openalgo import async_client

        # Mock multiple API calls
        with patch("loats.openalgo.async_client.get_history") as mock_get_history:
            mock_get_history.return_value = {"status": "success", "data": []}

            symbols = [f"TEST{i}" for i in range(10)]
            start_time = time.time()

            # Simulate batch requests
            tasks = []
            for symbol in symbols:
                task = asyncio.create_task(
                    async_client.get_history(symbol, "1min", "100")
                )
                tasks.append(task)

            _ = await asyncio.gather(*tasks)  # Execute concurrent API requests
            end_time = time.time()

            batch_time = end_time - start_time
            requests_per_second = len(symbols) / max(
                batch_time, 0.001
            )  # Avoid division by zero

            print(f"Batch API performance: {requests_per_second:.2f} requests/sec")
            assert requests_per_second > 50, (
                f"Batch API performance too slow: {requests_per_second:.2f} requests/sec (expected > 50)"
            )
