"""Performance benchmarks for the trading strategy core implementation."""

import datetime
import os
import sys
import time
from pathlib import Path
from typing import Any

import pytest

sys.path.append(str(Path(__file__).parent.parent.resolve()))

from src.loats.config import get_settings
from src.loats.models import Order, OrderType, Signal, Trade
from src.loats.trading_strategy.core import StrategyMode, TradingStrategyCore


def setup_environment() -> None:
    """Set up environment for performance testing."""
    os.environ["OPENALGO_API_KEY"] = "test_key"


def cleanup_environment() -> None:
    """Clean up environment after performance testing."""
    if "OPENALGO_API_KEY" in os.environ:
        del os.environ["OPENALGO_API_KEY"]


def benchmark_trade_validation_performance() -> dict[str, Any]:
    """Benchmark trade validation performance."""
    setup_environment()

    strategy = TradingStrategyCore()

    # Create test trades
    trades = []
    for i in range(1000):
        trade = Trade(
            trade_id=f"benchmark_trade_{i}",
            symbol="NIFTY" if i % 2 == 0 else "BANKNIFTY",
            signal_type="BUY" if i % 3 != 0 else "SELL",
            entry_price=100.0 + (i % 10),
            quantity=25,
            entry_time=datetime.datetime.now(datetime.UTC),
            status="PENDING",
            metadata={"modification_count": i % 30},
            order_value=5000.0 + (i % 1000),
        )
        trades.append(trade)

    # Benchmark validation
    start_time = time.perf_counter()

    for trade in trades:
        strategy.validate_trade(trade)

    end_time = time.perf_counter()

    total_time = end_time - start_time
    avg_time_per_trade = total_time / len(trades)
    trades_per_second = len(trades) / total_time

    cleanup_environment()

    return {
        "test_name": "Trade Validation Performance",
        "total_trades": len(trades),
        "total_time_seconds": total_time,
        "average_time_per_trade_ms": avg_time_per_trade * 1000,
        "trades_per_second": trades_per_second,
        "performance_target_met": avg_time_per_trade < 0.001,  # < 1ms per trade
    }


def benchmark_cmp_compliance_performance() -> dict[str, Any]:
    """Benchmark CMP compliance validation performance."""
    setup_environment()

    strategy = TradingStrategyCore()

    # Create test trades
    trades = []
    for i in range(1000):
        trade = Trade(
            trade_id=f"benchmark_cmp_trade_{i}",
            symbol="NIFTY",
            signal_type="BUY",
            entry_price=100.0,
            quantity=25,
            entry_time=datetime.datetime.now(datetime.UTC),
            status="PENDING",
            metadata={"modification_count": i % 30},
        )
        trades.append(trade)

    # Benchmark CMP compliance validation
    start_time = time.perf_counter()

    for trade in trades:
        strategy.validate_cmp_compliance(trade)

    end_time = time.perf_counter()

    total_time = end_time - start_time
    avg_time_per_trade = total_time / len(trades)
    trades_per_second = len(trades) / total_time

    cleanup_environment()

    return {
        "test_name": "CMP Compliance Validation Performance",
        "total_trades": len(trades),
        "total_time_seconds": total_time,
        "average_time_per_trade_ms": avg_time_per_trade * 1000,
        "trades_per_second": trades_per_second,
        "performance_target_met": avg_time_per_trade < 0.0005,  # < 0.5ms per trade
    }


def benchmark_trailing_stop_performance() -> dict[str, Any]:
    """Benchmark trailing stop calculation performance."""
    setup_environment()

    strategy = TradingStrategyCore()

    # Create test trades
    trades = []
    for i in range(1000):
        trade = Trade(
            trade_id=f"benchmark_trailing_trade_{i}",
            symbol="NIFTY",
            signal_type="BUY" if i % 2 == 0 else "SELL",
            entry_price=100.0 + (i % 20),
            quantity=25,
            entry_time=datetime.datetime.now(datetime.UTC),
            status="ACTIVE",
            metadata={},
        )
        trades.append(trade)

    # Benchmark trailing stop application
    start_time = time.perf_counter()

    for trade in trades:
        # Apply trailing stop with varying prices
        current_price = trade.entry_price + (i % 10)
        strategy.apply_cmp_trailing_stop(trade, current_price)

    end_time = time.perf_counter()

    total_time = end_time - start_time
    avg_time_per_trade = total_time / len(trades)
    trades_per_second = len(trades) / total_time

    cleanup_environment()

    return {
        "test_name": "Trailing Stop Calculation Performance",
        "total_trades": len(trades),
        "total_time_seconds": total_time,
        "average_time_per_trade_ms": avg_time_per_trade * 1000,
        "trades_per_second": trades_per_second,
        "performance_target_met": avg_time_per_trade < 0.0003,  # < 0.3ms per trade
    }


def benchmark_sl_m_order_creation_performance() -> dict[str, Any]:
    """Benchmark SL-M order creation performance."""
    setup_environment()

    strategy = TradingStrategyCore()

    # Create test trades with trailing configs
    trades = []
    for i in range(1000):
        trade = Trade(
            trade_id=f"benchmark_slm_trade_{i}",
            symbol="NIFTY",
            signal_type="BUY",
            entry_price=100.0,
            quantity=25,
            entry_time=datetime.datetime.now(datetime.UTC),
            status="ACTIVE",
            metadata={},
        )

        # Apply trailing stop to create config
        strategy.apply_cmp_trailing_stop(trade, 105.0)
        trades.append(trade)

    # Benchmark SL-M order creation
    start_time = time.perf_counter()

    for trade in trades:
        strategy.create_sl_m_order(trade)

    end_time = time.perf_counter()

    total_time = end_time - start_time
    avg_time_per_order = total_time / len(trades)
    orders_per_second = len(trades) / total_time

    cleanup_environment()

    return {
        "test_name": "SL-M Order Creation Performance",
        "total_orders": len(trades),
        "total_time_seconds": total_time,
        "average_time_per_order_ms": avg_time_per_order * 1000,
        "orders_per_second": orders_per_second,
        "performance_target_met": avg_time_per_order < 0.0002,  # < 0.2ms per order
    }


def benchmark_trade_execution_performance() -> dict[str, Any]:
    """Benchmark trade execution performance."""
    setup_environment()

    strategy = TradingStrategyCore()
    strategy.set_mode(StrategyMode.LIVE)

    # Create test signals
    signals = []
    for i in range(100):
        signal = Signal(
            symbol="NIFTY" if i % 2 == 0 else "BANKNIFTY",
            signal_type="BUY" if i % 3 != 0 else "SELL",
            price=100.0 + (i % 20),
            timestamp=datetime.datetime.now(datetime.UTC),
            metadata={"strategy": "benchmark"},
        )
        signals.append(signal)

    # Benchmark trade execution
    start_time = time.perf_counter()

    for signal in signals:
        strategy.execute_trade(signal)

    end_time = time.perf_counter()

    total_time = end_time - start_time
    avg_time_per_trade = total_time / len(signals)
    trades_per_second = len(signals) / total_time

    cleanup_environment()

    return {
        "test_name": "Trade Execution Performance",
        "total_trades": len(signals),
        "total_time_seconds": total_time,
        "average_time_per_trade_ms": avg_time_per_trade * 1000,
        "trades_per_second": trades_per_second,
        "performance_target_met": avg_time_per_trade < 0.005,  # < 5ms per trade
    }


def benchmark_memory_usage() -> dict[str, Any]:
    """Benchmark memory usage with large number of trades."""
    setup_environment()

    strategy = TradingStrategyCore()

    # Add many trades to test memory usage
    num_trades = 1000
    for i in range(num_trades):
        trade = Trade(
            trade_id=f"memory_test_trade_{i}",
            symbol="NIFTY" if i % 2 == 0 else "BANKNIFTY",
            signal_type="BUY" if i % 3 != 0 else "SELL",
            entry_price=100.0 + (i % 50),
            quantity=25,
            entry_time=datetime.datetime.now(datetime.UTC),
            status="ACTIVE",
            metadata={"modification_count": i % 30},
            order_value=5000.0 + (i % 2000),
        )
        strategy.active_trades[f"memory_test_trade_{i}"] = trade

    # Add some orders
    for i in range(100):
        order = Order(
            order_id=f"memory_test_order_{i}",
            symbol="NIFTY",
            quantity=25,
            order_type=OrderType.LIMIT,
            price=100.0 + (i % 20),
        )
        strategy.pending_orders[f"memory_test_order_{i}"] = order

    # Get memory usage (approximate)
    import sys

    memory_usage = sys.getsizeof(strategy.active_trades) + sys.getsizeof(
        strategy.pending_orders
    )

    cleanup_environment()

    return {
        "test_name": "Memory Usage Benchmark",
        "total_trades": num_trades,
        "total_orders": 100,
        "approximate_memory_bytes": memory_usage,
        "memory_per_trade_bytes": memory_usage / num_trades,
        "performance_target_met": memory_usage < 10_000_000,  # < 10MB for 1000 trades
    }


def benchmark_strategy_metrics_performance() -> dict[str, Any]:
    """Benchmark strategy metrics calculation performance."""
    setup_environment()

    strategy = TradingStrategyCore()

    # Add many trades to test metrics calculation performance
    num_trades = 500
    for i in range(num_trades):
        trade = Trade(
            trade_id=f"metrics_test_trade_{i}",
            symbol="NIFTY" if i % 2 == 0 else "BANKNIFTY",
            signal_type="BUY" if i % 3 != 0 else "SELL",
            entry_price=100.0 + (i % 50),
            quantity=25,
            entry_time=datetime.datetime.now(datetime.UTC),
            status="ACTIVE",
            metadata={"modification_count": i % 30},
            order_value=5000.0 + (i % 2000),
        )
        strategy.active_trades[f"metrics_test_trade_{i}"] = trade

    # Add some orders
    for i in range(50):
        order = Order(
            order_id=f"metrics_test_order_{i}",
            symbol="NIFTY",
            quantity=25,
            order_type=OrderType.LIMIT,
            price=100.0 + (i % 20),
        )
        strategy.pending_orders[f"metrics_test_order_{i}"] = order

    # Benchmark metrics calculation
    start_time = time.perf_counter()

    for _ in range(100):  # Calculate metrics 100 times
        strategy.get_strategy_metrics()

    end_time = time.perf_counter()

    total_time = end_time - start_time
    avg_time_per_calculation = total_time / 100

    cleanup_environment()

    return {
        "test_name": "Strategy Metrics Calculation Performance",
        "total_trades": num_trades,
        "total_orders": 50,
        "total_calculations": 100,
        "total_time_seconds": total_time,
        "average_time_per_calculation_ms": avg_time_per_calculation * 1000,
        "calculations_per_second": 100 / total_time,
        "performance_target_met": avg_time_per_calculation
        < 0.001,  # < 1ms per calculation
    }


def run_all_performance_benchmarks() -> list[dict[str, Any]]:
    """Run all performance benchmarks and return results."""
    print("Running LOATS13July2026 Trading Strategy Core Performance Benchmarks...")
    print("=" * 80)

    benchmarks = [
        benchmark_trade_validation_performance,
        benchmark_cmp_compliance_performance,
        benchmark_trailing_stop_performance,
        benchmark_sl_m_order_creation_performance,
        benchmark_trade_execution_performance,
        benchmark_memory_usage,
        benchmark_strategy_metrics_performance,
    ]

    results = []
    for benchmark in benchmarks:
        print(f"\nRunning {benchmark.__name__}...")
        result = benchmark()
        results.append(result)
        print(f"  [OK] {result['test_name']}")
        print(f"    Total Time: {result['total_time_seconds']:.4f}s")
        if "average_time_per_trade_ms" in result:
            print(f"    Avg Time/Trade: {result['average_time_per_trade_ms']:.4f}ms")
        if "trades_per_second" in result:
            print(f"    Throughput: {result['trades_per_second']:.2f}/sec")
        if "performance_target_met" in result:
            status = "[PASS]" if result["performance_target_met"] else "[FAIL]"
            print(f"    Performance Target: {status}")

    print("\n" + "=" * 80)
    print("Performance Benchmark Summary:")

    all_passed = True
    for result in results:
        if "performance_target_met" in result:
            if not result["performance_target_met"]:
                all_passed = False
                break

    overall_status = "[ALL TESTS PASSED]" if all_passed else "[SOME TESTS FAILED]"
    print(f"Overall Result: {overall_status}")

    return results


def test_performance_benchmarks() -> None:
    """Test that performance benchmarks run successfully."""
    results = run_all_performance_benchmarks()

    # Verify we got results for all benchmarks
    assert len(results) == 7

    # Verify each result has expected structure
    for result in results:
        assert "test_name" in result
        assert "total_time_seconds" in result
        if "performance_target_met" in result:
            # For now, we just verify the benchmarks run, not that they pass
            # performance targets (which may vary by environment)
            assert isinstance(result["performance_target_met"], bool)


if __name__ == "__main__":
    # Run performance benchmarks
    results = run_all_performance_benchmarks()

    # Optionally save results to file
    import json

    with open("trading_strategy_performance_results.json", "w") as f:
        json.dump(results, f, indent=2)

    print(f"\nPerformance results saved to trading_strategy_performance_results.json")
