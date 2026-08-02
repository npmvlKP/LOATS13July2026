#!/usr/bin/env python3
"""Benchmark script for Supertrend indicator performance."""
import time
import numpy as np
import pandas as pd
import sys
from pathlib import Path

# Add project root to path for imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.loats.ta import calculate_supertrend

def generate_test_data(n_points: int = 10000) -> pd.DataFrame:
    """Generate synthetic market data for benchmarking."""
    np.random.seed(42)  # For reproducible results

    # Generate realistic price data with trends and volatility
    base_price = 100.0
    prices = np.cumsum(np.random.normal(0, 0.5, n_points)) + base_price

    # Add some trends
    trend = np.linspace(0, 10, n_points)
    prices += trend

    # Create OHLC data
    data = {
        "timestamp": pd.date_range("2023-01-01", periods=n_points, freq="1min"),
        "open": prices,
        "high": prices + np.abs(np.random.normal(0, 0.2, n_points)),
        "low": prices - np.abs(np.random.normal(0, 0.2, n_points)),
        "close": prices,
        "volume": np.random.randint(1000, 5000, n_points),
    }

    return pd.DataFrame(data)

def benchmark_supertrend(df: pd.DataFrame, n_runs: int = 5) -> dict:
    """Benchmark supertrend calculation performance."""
    times = []

    for _ in range(n_runs):
        start_time = time.time()
        supertrend, direction = calculate_supertrend(df)
        end_time = time.time()
        times.append(end_time - start_time)

    avg_time = np.mean(times)
    std_time = np.std(times)
    min_time = np.min(times)
    max_time = np.max(times)

    return {
        "n_points": len(df),
        "avg_time": avg_time,
        "std_time": std_time,
        "min_time": min_time,
        "max_time": max_time,
        "times": times,
    }

def main() -> None:
    """Run benchmark tests with different data sizes."""
    print("Supertrend Performance Benchmark")
    print("=" * 50)

    # Test with different data sizes
    data_sizes = [1000, 5000, 10000, 20000, 50000]

    results = []

    for size in data_sizes:
        print(f"\nGenerating test data with {size} points...")
        df = generate_test_data(size)

        print(f"Benchmarking with {size} data points...")
        result = benchmark_supertrend(df, n_runs=3)
        results.append(result)

        print(f"  Average time: {result['avg_time']:.4f}s")
        print(f"  Std dev: {result['std_time']:.4f}s")
        print(f"  Min time: {result['min_time']:.4f}s")
        print(f"  Max time: {result['max_time']:.4f}s")

    # Print summary
    print("\n" + "=" * 50)
    print("SUMMARY")
    print("=" * 50)
    print(f"{'Data Points':<12} {'Avg Time (s)':<15} {'Time/Point (us)':<18}")
    print("-" * 50)

    for result in results:
        n_points = result['n_points']
        avg_time = result['avg_time']
        time_per_point = (avg_time / n_points) * 1_000_000  # Convert to microseconds

        print(f"{n_points:<12} {avg_time:<15.4f} {time_per_point:<18.2f}")

if __name__ == "__main__":
    main()