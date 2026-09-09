#!/usr/bin/env python3
"""Performance benchmark script for LOATS13July2026."""

import asyncio
import json
import os
import shutil
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Add project root to path for imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Data isolation: point the DB singleton at a per-run scratch directory
# BEFORE importing src.loats.main. The previous script bound the
# production database singleton, so every benchmark run wrote ~150
# benchmark_* signals and historical rows into the live database the
# supervised P5 forward test is measuring (test-to-production leakage).
# Override the location with LOATS_BENCHMARK_DATA_DIR when needed.
_BENCHMARK_DATA_DIR = Path(
    os.environ.get("LOATS_BENCHMARK_DATA_DIR")
    or tempfile.mkdtemp(prefix="loats_benchmark_")
)
_BENCHMARK_DATA_DIR_IS_EPHEMERAL = "LOATS_BENCHMARK_DATA_DIR" not in os.environ
os.environ["SQLITE_DB_PATH"] = str(_BENCHMARK_DATA_DIR / "benchmark.db")
os.environ["AUDIT_LOG_PATH"] = str(_BENCHMARK_DATA_DIR / "benchmark_audit.jsonl")

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
    logger.info(f"Benchmark data directory: {_BENCHMARK_DATA_DIR}")

    verdict_error: Exception | None = None
    try:
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

        # Exit-code contract: a non-PASS verdict must fail the process, not
        # just print a summary the caller can ignore.
        summary = report["summary"]
        if summary["overall_status"] != "PASS":
            verdict_error = RuntimeError(
                "Performance benchmark verdict: "
                f"{summary['overall_status']} "
                f"({summary['cmp_validation']['passing_operations']}/"
                f"{summary['cmp_validation']['total_operations']} latency-gate "
                "checks passing)"
            )
    finally:
        # Cleanup runs on EVERY exit path: the aiosqlite worker threads are
        # non-daemon, so skipping async_close_all keeps the interpreter
        # alive after a raise (previously observed as a post-verdict hang).
        await db.async_close_all()
        logger.info("Performance benchmark completed")
        if _BENCHMARK_DATA_DIR_IS_EPHEMERAL:
            shutil.rmtree(_BENCHMARK_DATA_DIR, ignore_errors=True)

    if verdict_error is not None:
        raise verdict_error


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

    # Count passing/failed operations. The gate grades the UNION of both
    # validation sets (production registry + this run's benchmark
    # operations), so a run that measured nothing can never grade as a
    # vacuous pass (`0 == 0`). Fail-closed on an empty measurement set.
    cmp_validation_items = list(cmp_validation.items())
    benchmark_validation_items = list(benchmark_validation.items())
    total_ops = len(cmp_validation_items) + len(benchmark_validation_items)
    passing_ops = sum(1 for _, v in cmp_validation_items if v["overall_pass"]) + sum(
        1 for _, v in benchmark_validation_items if v["overall_pass"]
    )

    benchmark_total = len(benchmark_validation_items)
    benchmark_passing = sum(
        1 for _, v in benchmark_validation_items if v["overall_pass"]
    )

    if total_ops == 0:
        raise ValueError(
            "No latency measurements were recorded in either the production "
            "registry or the benchmark run; refusing to grade an empty "
            "measurement set as PASS (fail-closed)."
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
            "pass_rate": passing_ops / total_ops,
        },
        "benchmark_validation": {
            "total_operations": benchmark_total,
            "passing_operations": benchmark_passing,
            "pass_rate": (
                benchmark_passing / benchmark_total if benchmark_total > 0 else 0
            ),
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
