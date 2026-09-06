#!/usr/bin/env python3
"""Performance benchmark script for LOATS13July2026."""

import asyncio
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Add project root to path for imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.loats.loats_logging import logger
from src.loats.main import db
from src.loats.performance_analyzer import (
    run_comprehensive_analysis,
    run_latency_benchmark,
)


async def main() -> None:
    """Run comprehensive performance benchmarks."""
    print("LOATS13July2026 Performance Benchmark")
    print("=" * 60)

    # Initialize database
    await db.async_initialize()
    logger.info("Database initialized for performance testing")

    # Run comprehensive analysis
    print("\nRunning comprehensive performance analysis...")
    comprehensive_results = await run_comprehensive_analysis(db)

    # Run latency benchmark
    print("\nRunning CMP P1/P5 latency benchmark...")
    benchmark_results = await run_latency_benchmark(db)

    # Generate report
    report = {
        "comprehensive_analysis": comprehensive_results,
        "latency_benchmark": benchmark_results,
        "summary": generate_summary(comprehensive_results, benchmark_results),
    }

    # Save results
    save_results(report)

    # Print summary
    print("\n" + "=" * 60)
    print("PERFORMANCE BENCHMARK SUMMARY")
    print("=" * 60)
    print_summary(report["summary"])

    # Clean up
    await db.async_close_all()
    logger.info("Performance benchmark completed")


def generate_summary(
    comprehensive_results: dict[str, Any],
    benchmark_results: dict[str, Any],
) -> dict[str, Any]:
    """Generate performance summary."""
    # Database operations summary
    db_stats = comprehensive_results["database_operations"]

    # ANALYZE round-trip summary
    analyze_rt = comprehensive_results["analyze_round_trip"]["round_trip"]

    # CMP validation summary
    cmp_validation = comprehensive_results["cmp_validation"]
    benchmark_validation = benchmark_results["validation"]

    # Count passing/failed operations
    total_ops = len(cmp_validation)
    passing_ops = sum(1 for v in cmp_validation.values() if v["overall_pass"])

    benchmark_total = len(benchmark_validation)
    benchmark_passing = sum(
        1 for v in benchmark_validation.values() if v["overall_pass"]
    )

    return {
        "database_operations": {
            "async_write_avg": db_stats.get("async_create_signal", {}).get("mean", 0),
            "async_read_avg": db_stats.get("async_get_signals", {}).get("mean", 0),
            "sync_write_avg": db_stats.get("sync_create_signal", {}).get("mean", 0),
            "sync_read_avg": db_stats.get("sync_get_signals", {}).get("mean", 0),
        },
        "analyze_round_trip": {
            "total_duration": analyze_rt["duration"],
            "ta_percentage": analyze_rt["ta_percentage"],
            "db_percentage": analyze_rt["db_percentage"],
        },
        "cmp_validation": {
            "total_operations": total_ops,
            "passing_operations": passing_ops,
            "pass_rate": passing_ops / total_ops if total_ops > 0 else 0,
        },
        "benchmark_validation": {
            "total_operations": benchmark_total,
            "passing_operations": benchmark_passing,
            "pass_rate": benchmark_passing / benchmark_total
            if benchmark_total > 0
            else 0,
        },
        "overall_status": "PASS" if passing_ops == total_ops else "PARTIAL",
    }


def print_summary(summary: dict[str, Any]) -> None:
    """Print performance summary."""
    db_ops = summary["database_operations"]
    analyze_rt = summary["analyze_round_trip"]
    cmp_val = summary["cmp_validation"]
    bench_val = summary["benchmark_validation"]

    print("Database Operations (ms):")
    print(f"  Async Write: {db_ops['async_write_avg'] * 1000:.3f}ms")
    print(f"  Async Read:  {db_ops['async_read_avg'] * 1000:.3f}ms")
    print(f"  Sync Write:  {db_ops['sync_write_avg'] * 1000:.3f}ms")
    print(f"  Sync Read:   {db_ops['sync_read_avg'] * 1000:.3f}ms")

    print("\nANALYZE Round-Trip:")
    print(f"  Total Duration: {analyze_rt['total_duration']:.4f}s")
    print(f"  TA Processing:  {analyze_rt['ta_percentage']:.1f}%")
    print(f"  DB Operations:  {analyze_rt['db_percentage']:.1f}%")

    print("\nCMP Validation:")
    print(f"  Operations Tested: {cmp_val['total_operations']}")
    print(f"  Operations Passing: {cmp_val['passing_operations']}")
    print(f"  Pass Rate: {cmp_val['pass_rate'] * 100:.1f}%")

    print("\nBenchmark Validation:")
    print(f"  Operations Tested: {bench_val['total_operations']}")
    print(f"  Operations Passing: {bench_val['passing_operations']}")
    print(f"  Pass Rate: {bench_val['pass_rate'] * 100:.1f}%")

    print(f"\nOverall Status: {summary['overall_status']}")


def save_results(report: dict[str, Any]) -> None:
    """Save benchmark results to file."""
    results_dir = project_root / "reports" / "performance"
    results_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    filename = results_dir / f"performance_benchmark_{timestamp}.json"

    with open(filename, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=str)

    logger.info(f"Performance results saved to: {filename}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nBenchmark interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\nBenchmark failed: {e}")
        logger.error(f"Performance benchmark failed: {e}")
        sys.exit(1)
