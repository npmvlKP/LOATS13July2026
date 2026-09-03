#!/usr/bin/env python3
"""
P1 Phase-Gate Evidence Collector: Live ANALYZE Round-Trip Latency Measurements

TODO-25 (F7-L-05) — Collect P1/P5 phase-gate evidence
P1: live ANALYZE round-trip latency measurements (log to reports/)
P5: begin 2-week forward test (BLOCKED - requires TODO-13 routing)

Usage:
    python scripts/collect_p1_phase_gate_evidence.py --samples 100
    python scripts/collect_p1_phase_gate_evidence.py --samples 1000 --output reports/p1_analyze_latency_20260828.json

This script measures two scopes and records which one produced the numbers:

1. analysis-scope (always): TA calculation + local database operations.
   This is the in-process analysis loop. It is indicative only and is NOT
   sufficient on its own to discharge P1.

2. live-endpoint scope (optional, --live-endpoint): a real HTTP round trip
   to the configured OpenAlgo endpoint using
   AsyncOpenAlgoClient.get_quotes (read-only), measured in isolation.
   Combined with the analysis scope it approximates the full ANALYZE
   round trip; this is the measurement P1 requires: a live OpenAlgo
   round trip.

The evidence JSON reports per-scope statistics and an explicit
"measurement_scope" field so downstream verifiers and humans cannot mistake
client-side-only numbers for live-endpoint evidence.

Gate semantics:
- With --live-endpoint: the P1 verdict is taken from the LIVE scope only.
- Without it: the P1 verdict is NOT claimable; the script reports PASS (P1)
  for the analysis scope but exits 2 (verdict "INDETERMINATE") and the
  metadata marks evidence as NOT discharging.

FIXED (F8-L-03): the previous version timed only TA + local SQLite and
labelled the result "Live ANALYZE round-trip latency". Those numbers
(mean ~13 ms) measured the in-process analysis loop, not an OpenAlgo
round trip.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.loats.database import Database
from src.loats.models import HistoricalData
from src.loats.ta import TechnicalAnalysis


class P1EvidenceCollector:
    """Collector for P1 phase-gate evidence: ANALYZE round-trip latency."""

    # Performance gates from CMP specification
    ROUND_TRIP_GATE_MS = 100.0
    TA_GATE_MS = 80.0
    DB_GATE_MS = 20.0

    def __init__(self, output_dir: Path = Path("reports")):
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.measurements: list[dict[str, Any]] = []
        self.live_measurements: list[dict[str, Any]] = []
        self.db = None  # Reuse DB instance
        self.ta = None  # Reuse TA instance

    async def collect_samples(self, num_samples: int = 100) -> dict[str, Any]:
        """Collect ANALYZE round-trip latency samples (analysis scope)."""
        print(f"Collecting {num_samples} ANALYZE round-trip latency samples...")

        # Initialize components once (connection reuse across samples)
        if self.db is None:
            self.db = Database()
            self.ta = TechnicalAnalysis()

        # Generate small test data for realistic measurements
        # (20 candles keeps DB write overhead low and stable)
        test_data = self._generate_test_data(20)

        for i in range(num_samples):
            # Measure TA calculation
            ta_start = datetime.now(UTC)
            indicators = await asyncio.to_thread(
                self.ta.calculate_indicators, test_data
            )
            ta_duration_ms = (datetime.now(UTC) - ta_start).total_seconds() * 1000

            # Measure database operations (async methods, connection reuse)
            db_start = datetime.now(UTC)
            await self.db.async_store_historical_data(test_data)
            signals = await self.db.async_get_latest_signals("TEST", limit=10)
            db_duration_ms = (datetime.now(UTC) - db_start).total_seconds() * 1000

            # Calculate round-trip
            round_trip_ms = ta_duration_ms + db_duration_ms

            # Record measurement
            measurement = {
                "sample_id": i + 1,
                "timestamp": datetime.now(UTC).isoformat(),
                "ta_duration_ms": round(ta_duration_ms, 2),
                "db_duration_ms": round(db_duration_ms, 2),
                "round_trip_ms": round(round_trip_ms, 2),
                "ta_indicators_count": len(indicators),
                "db_signals_count": len(signals),
                "passes_ta_gate": ta_duration_ms <= self.TA_GATE_MS,
                "passes_db_gate": db_duration_ms <= self.DB_GATE_MS,
                "passes_round_trip_gate": round_trip_ms <= self.ROUND_TRIP_GATE_MS,
            }
            self.measurements.append(measurement)

            if (i + 1) % 10 == 0:
                print(f"  Collected {i + 1}/{num_samples} samples")

        # Close DB after all samples collected (connection reuse until then)
        if self.db:
            self.db.close()
            self.db = None

        return self._calculate_statistics()

    async def collect_live_samples(
        self,
        base_url: str,
        api_key: str,
        num_samples: int,
        symbol: str = "TEST",
    ) -> dict[str, Any]:
        """Collect live OpenAlgo round-trip latency samples (live scope).

        Each sample is one read-only get_quotes HTTP round trip to the
        configured OpenAlgo endpoint. This isolates the OpenAlgo network
        leg; combine with the analysis-scope statistics (TA + local DB,
        measured separately in the same run) when estimating the full
        ANALYZE loop against a live endpoint.
        """
        from src.loats.openalgo import AsyncOpenAlgoClient

        print(
            f"Collecting {num_samples} LIVE OpenAlgo round-trip latency samples "
            f"against {base_url} ..."
        )

        # get_quotes caches by digest of the sorted symbol list with a 60s TTL
        # (module-level cache_manager singleton). To measure the HTTP round
        # trip every time, the quotes cache is CLEARED before each sample.
        # The --symbol value is probed VERBATIM: fabricating suffixed symbols
        # would not exist in the broker master (verified live, F8-L-03).
        from src.loats.config import get_settings
        from src.loats.utils.cache import cache_manager

        await cache_manager.initialize()
        # The client's wire timeout is settings-driven (AsyncOpenAlgoClient
        # reads Settings.request_timeout); report it rather than pretending
        # this script can override it.
        effective_timeout_s: float = get_settings().request_timeout

        live_samples: list[dict[str, Any]] = []
        errors: list[str] = []

        async with AsyncOpenAlgoClient(api_key=api_key, base_url=base_url) as client:
            for i in range(num_samples):
                sample: dict[str, Any] = {
                    "sample_id": i + 1,
                    "timestamp": datetime.now(UTC).isoformat(),
                    "symbol": symbol,
                }
                try:
                    live_start = datetime.now(UTC)
                    # Bypass the 60s quotes cache so every sample measures a
                    # real HTTP round trip, not an in-process cache hit.
                    await cache_manager.clear("quotes:*")
                    await client.get_quotes([symbol])
                    live_duration_ms = (
                        datetime.now(UTC) - live_start
                    ).total_seconds() * 1000
                    sample["live_duration_ms"] = round(live_duration_ms, 2)
                    sample["passes_live_gate"] = (
                        live_duration_ms <= self.ROUND_TRIP_GATE_MS
                    )
                except Exception as e:
                    completed = datetime.now(UTC)
                    elapsed_ms = (completed - live_start).total_seconds() * 1000
                    errors.append(f"sample {i + 1}: {type(e).__name__}: {e}")
                    # The HTTP round trip DID complete (with an API-level
                    # error status); record its latency as evidence while
                    # keeping the gate verdict strict (no pass credit).
                    sample["live_duration_ms"] = round(elapsed_ms, 2)
                    sample["passes_live_gate"] = False
                    sample["error"] = f"{type(e).__name__}: {e}"
                live_samples.append(sample)

                if (i + 1) % 10 == 0:
                    print(f"  Collected {i + 1}/{num_samples} live samples")

        self.live_measurements = live_samples
        return self._calculate_live_statistics(
            errors=errors, base_url=base_url, request_timeout_s=effective_timeout_s
        )

    def _calculate_live_statistics(
        self,
        errors: list[str],
        base_url: str,
        request_timeout_s: float,
    ) -> dict[str, Any]:
        """Calculate statistics for the live-endpoint scope."""
        durations = [
            m["live_duration_ms"]
            for m in self.live_measurements
            if m.get("live_duration_ms") is not None
        ]
        # "successful" means the API answered without an error status; a
        # sample can carry a completed-exchange latency AND still be failed
        # (e.g. HTTP 400 symbol-not-found / 500 permission-denied).
        successful = sum(1 for m in self.live_measurements if not m.get("error"))
        passes = sum(1 for m in self.live_measurements if m.get("passes_live_gate"))
        total = len(self.live_measurements)

        stats: dict[str, Any] = {
            "summary": {
                "total_samples": total,
                "successful_samples": successful,
                "failed_samples": total - successful,
                "round_trip_gate": f"{self.ROUND_TRIP_GATE_MS}ms",
            },
            "gate_compliance": {
                "live_round_trip_gate_pass_rate": (
                    round(passes / total * 100, 2) if total else 0.0
                )
            },
            "measurements": self.live_measurements,
        }

        if durations:
            stats["round_trip_statistics"] = self._percentiles(durations)

        if errors:
            stats["errors"] = errors[:20]
            stats["failure_mode"] = self._classify_failure_mode(errors)

        stats["endpoint"] = {
            "base_url": base_url,
            "request_timeout_s": request_timeout_s,
            "method": "POST /api/v1/quotes (read-only, AsyncOpenAlgoClient.get_quotes)",
            "cache_bypass": "quotes cache cleared before each sample (TTL is 60s)",
        }
        return stats

    @staticmethod
    def _classify_failure_mode(errors: list[str]) -> str:
        """Classify the dominant live-probe failure mode for operator triage."""
        joined = " ".join(errors)
        if "Permission denied" in joined or "Insufficient permission" in joined:
            return (
                "broker-permission: the broker relayed 'Insufficient permission "
                "for that call' (Kite Connect PermissionException via the "
                "OpenAlgo Zerodha plugin). The Kite Connect app needs the "
                "market-data entitlement — order APIs and data APIs are "
                "subscribed separately on Kite Connect. Nothing to fix in this "
                "repository."
            )
        if "not found for exchange" in joined:
            return (
                "symbol-not-found: the probe symbol does not exist in the "
                "OpenAlgo master contracts. Re-run with a valid --symbol "
                "(e.g. --symbol TCS) and ensure master contracts are "
                "downloaded on the OpenAlgo instance."
            )
        if "Connection error" in joined or "ConnectError" in joined:
            return (
                "endpoint-unreachable: no service accepted the connection at "
                "the configured OPENALGO_BASE_URL. Start OpenAlgo and verify "
                "the URL."
            )
        if "Timeout" in joined or "timed out" in joined:
            return (
                "timeout: the endpoint accepted the connection but did not "
                "answer within the request timeout."
            )
        return "unclassified: inspect per-sample errors in measurements."

    @staticmethod
    def _percentiles(values: list[float]) -> dict[str, float]:
        sorted_vals = sorted(values)
        n = len(sorted_vals)

        def pct(p: float) -> float:
            return round(sorted_vals[min(int(n * p), n - 1)], 2)

        return {
            "min": round(min(values), 2),
            "max": round(max(values), 2),
            "mean": round(statistics.mean(values), 2),
            "median": round(statistics.median(values), 2),
            "p90": pct(0.90),
            "p95": pct(0.95),
            "p99": pct(0.99),
            "std_dev": round(statistics.stdev(values) if len(values) > 1 else 0, 2),
        }

    def _calculate_statistics(self) -> dict[str, Any]:
        """Calculate statistics from collected measurements."""
        ta_durations = [m["ta_duration_ms"] for m in self.measurements]
        db_durations = [m["db_duration_ms"] for m in self.measurements]
        round_trips = [m["round_trip_ms"] for m in self.measurements]

        # Count gate passes
        ta_passes = sum(1 for m in self.measurements if m["passes_ta_gate"])
        db_passes = sum(1 for m in self.measurements if m["passes_db_gate"])
        rt_passes = sum(1 for m in self.measurements if m["passes_round_trip_gate"])

        gate_compliance = {
            "ta_gate_pass_rate": round(ta_passes / len(self.measurements) * 100, 2),
            "db_gate_pass_rate": round(db_passes / len(self.measurements) * 100, 2),
            "round_trip_gate_pass_rate": round(
                rt_passes / len(self.measurements) * 100, 2
            ),
            "all_gates_pass_rate": round(
                sum(
                    1
                    for m in self.measurements
                    if m["passes_ta_gate"]
                    and m["passes_db_gate"]
                    and m["passes_round_trip_gate"]
                )
                / len(self.measurements)
                * 100,
                2,
            ),
        }

        stats: dict[str, Any] = {
            "summary": {
                "total_samples": len(self.measurements),
                "ta_gate": f"{self.TA_GATE_MS}ms",
                "db_gate": f"{self.DB_GATE_MS}ms",
                "round_trip_gate": f"{self.ROUND_TRIP_GATE_MS}ms",
            },
            "ta_statistics": self._percentiles(ta_durations),
            "db_statistics": self._percentiles(db_durations),
            "round_trip_statistics": self._percentiles(round_trips),
            "gate_compliance": gate_compliance,
            "measurements": self.measurements,
        }
        return stats

    def _generate_test_data(self, size: int) -> list[HistoricalData]:
        """Generate test historical data."""
        from datetime import timedelta

        import numpy as np

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

    def save_evidence(
        self,
        stats: dict[str, Any],
        output_path: Path,
        live_stats: dict[str, Any] | None = None,
        live_requested: bool = False,
    ) -> None:
        """Save evidence to JSON file."""
        live_available = live_stats is not None
        # P1 is only discharged by live-endpoint evidence.
        p1_discharging = live_available and (
            live_stats["gate_compliance"]["live_round_trip_gate_pass_rate"] >= 80.0
        )

        if live_available:
            measurement_scope = "live-endpoint"
        elif live_requested:
            measurement_scope = (
                "live-endpoint (FAILED - probe errored, no live evidence)"
            )
        else:
            measurement_scope = "analysis-scope (client-side only)"

        evidence: dict[str, Any] = {
            "metadata": {
                "todo_id": "TODO-25",
                "finding_id": "F7-L-05",
                "phase_gate": "P1",
                "description": "Live ANALYZE round-trip latency measurements",
                "collected_at": datetime.now(UTC).isoformat(),
                "git_commit": self._get_git_commit(),
                "python_version": sys.version,
                "fix_version": (
                    "3.0 - F8-L-03: two-scope evidence; P1 verdict requires "
                    "live OpenAlgo round trip (analysis-scope alone no longer "
                    "discharges P1)"
                ),
                "measurement_scope": measurement_scope,
                "p1_discharging": p1_discharging,
                "scopes": {
                    "analysis": "TA calculation + local database operations (in-process)",
                    "live": (
                        "POST /api/v1/quotes HTTP round trip to the configured "
                        "OpenAlgo endpoint (read-only; measured in isolation "
                        "from the analysis scope)"
                        if live_available
                        else "not measured in this run"
                    ),
                },
            },
            "evidence": stats,
        }
        if live_stats is not None:
            evidence["live_evidence"] = live_stats

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(evidence, f, indent=2, default=str)

        print(f"\n✅ Evidence saved to: {output_path}")

    def _get_git_commit(self) -> str:
        """Get current git commit hash."""
        import subprocess

        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
                check=True,
                timeout=5,
            )
            return result.stdout.strip()
        except Exception:
            return "unknown"

    def print_summary(
        self,
        stats: dict[str, Any],
        live_stats: dict[str, Any] | None = None,
        live_requested: bool = False,
    ) -> None:
        """Print evidence collection summary."""
        print("\n" + "=" * 70)
        print("P1 PHASE-GATE EVIDENCE COLLECTION SUMMARY")
        print("=" * 70)

        summary = stats["summary"]
        print(f"\nTotal samples: {summary['total_samples']}")
        print("Performance gates:")
        print(f"  - TA calculation: {summary['ta_gate']}")
        print(f"  - Database ops:   {summary['db_gate']}")
        print(f"  - Round-trip:     {summary['round_trip_gate']}")

        rt_stats = stats["round_trip_statistics"]
        print("\nRound-trip latency statistics (ANALYSIS scope):")
        print(f"  - Mean:   {rt_stats['mean']} ms")
        print(f"  - Median: {rt_stats['median']} ms")
        print(f"  - P95:    {rt_stats['p95']} ms")
        print(f"  - P99:    {rt_stats['p99']} ms")

        gate_compliance = stats["gate_compliance"]
        print("\nGate compliance (ANALYSIS scope):")
        print(
            f"  - TA gate pass rate:         {gate_compliance['ta_gate_pass_rate']:.2f}%"
        )
        print(
            f"  - DB gate pass rate:         {gate_compliance['db_gate_pass_rate']:.2f}%"
        )
        print(
            f"  - Round-trip gate pass rate: {gate_compliance['round_trip_gate_pass_rate']:.2f}%"
        )
        print(
            f"  - All gates pass rate:       {gate_compliance['all_gates_pass_rate']:.2f}%"
        )

        # Live scope section
        if live_stats is not None:
            live_rt = live_stats.get("round_trip_statistics")
            live_gc = live_stats["gate_compliance"]
            live_summary = live_stats["summary"]
            print("\nLIVE OpenAlgo round-trip latency statistics:")
            print(f"  - Endpoint:   {live_stats['endpoint']['base_url']}")
            print(
                f"  - Samples:    {live_summary['total_samples']} "
                f"({live_summary['successful_samples']} ok, "
                f"{live_summary['failed_samples']} failed)"
            )
            if live_rt:
                print(f"  - Mean:   {live_rt['mean']} ms")
                print(f"  - Median: {live_rt['median']} ms")
                print(f"  - P95:    {live_rt['p95']} ms")
                print(f"  - P99:    {live_rt['p99']} ms")
            print(
                f"  - Round-trip gate pass rate: "
                f"{live_gc['live_round_trip_gate_pass_rate']:.2f}%"
            )
        elif live_requested:
            print("\nLIVE OpenAlgo round-trip: REQUESTED BUT FAILED (see errors above)")

        print("\n" + "=" * 70)

        # P1 gate verdict — live evidence is mandatory (F8-L-03)
        P1_GATE_THRESHOLD = 80.0
        if live_stats is not None:
            live_pass = (
                live_stats["gate_compliance"]["live_round_trip_gate_pass_rate"]
                >= P1_GATE_THRESHOLD
            )
            if live_pass:
                print("✅ P1 PHASE-GATE: PASSED (live-endpoint evidence)")
                pct = live_stats["gate_compliance"]["live_round_trip_gate_pass_rate"]
                print(
                    f"   Evidence: Live round-trip latency meets <100ms gate "
                    f"({pct:.2f}% ≥ {P1_GATE_THRESHOLD:.0f}%)"
                )
            else:
                print("❌ P1 PHASE-GATE: FAILED (live-endpoint evidence)")
                print(
                    f"   Evidence: Live round-trip below <100ms gate "
                    f"({live_stats['gate_compliance']['live_round_trip_gate_pass_rate']:.2f}% pass rate)"
                )
                failure_mode = live_stats.get("failure_mode")
                if failure_mode:
                    print(f"   Diagnosis: {failure_mode}")
        else:
            print("⚠️  P1 PHASE-GATE: INDETERMINATE")
            print(
                "   Analysis-scope evidence alone does NOT discharge P1 "
                "(F8-L-03). Re-run with --live-endpoint against a live "
                "OpenAlgo endpoint."
            )

        print("=" * 70)


async def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Collect P1 phase-gate evidence")
    parser.add_argument(
        "--samples",
        type=int,
        default=100,
        help="Number of latency samples to collect (default: 100)",
    )
    parser.add_argument(
        "--live-endpoint",
        action="store_true",
        help=(
            "Require a live OpenAlgo round trip per sample (P1-discharging "
            "evidence). Probes POST /api/v1/quotes (read-only)."
        ),
    )
    parser.add_argument(
        "--base-url",
        type=str,
        default=None,
        help=(
            "OpenAlgo base URL for --live-endpoint "
            "(default: OPENALGO_BASE_URL or settings default)"
        ),
    )
    parser.add_argument(
        "--api-key",
        type=str,
        default=None,
        help="OpenAlgo API key (default: OPENALGO_API_KEY env var or settings)",
    )
    parser.add_argument(
        "--symbol",
        type=str,
        default="TEST",
        help="Base symbol for quote probes (default: TEST; made unique per run)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output file path (default: reports/p1_analyze_latency_YYYYMMDD_HHMMSS.json)",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress verbose output",
    )

    args = parser.parse_args()

    # Generate default output path if not provided
    if args.output is None:
        timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        args.output = Path("reports") / f"p1_analyze_latency_{timestamp}.json"

    # Collect evidence
    collector = P1EvidenceCollector()
    stats = await collector.collect_samples(args.samples)

    live_stats: dict[str, Any] | None = None
    live_error: str | None = None
    if args.live_endpoint:
        from src.loats.config import get_settings

        settings = get_settings()
        base_url = args.base_url or settings.openalgo_base_url
        api_key = args.api_key or settings.openalgo_api_key.get_secret_value()
        try:
            live_stats = await collector.collect_live_samples(
                base_url=base_url,
                api_key=api_key,
                num_samples=args.samples,
                symbol=args.symbol,
            )
        except Exception as e:
            live_error = f"{type(e).__name__}: {e}"
            print(f"\n❌ Live-endpoint probe failed: {live_error}")

    # Save evidence
    collector.save_evidence(
        stats,
        args.output,
        live_stats=live_stats,
        live_requested=args.live_endpoint,
    )

    # Print summary
    if not args.quiet:
        collector.print_summary(
            stats, live_stats=live_stats, live_requested=args.live_endpoint
        )

    # Exit codes:
    #   0 = P1 PASSED (live-endpoint evidence met the gate)
    #   1 = P1 FAILED (live evidence collected, gate not met)
    #   2 = INDETERMINATE (no live evidence: probe not requested, or failed)
    P1_GATE_THRESHOLD = 80.0
    if live_stats is not None:
        p1_pass = (
            live_stats["gate_compliance"]["live_round_trip_gate_pass_rate"]
            >= P1_GATE_THRESHOLD
        )
        sys.exit(0 if p1_pass else 1)
    sys.exit(2)


if __name__ == "__main__":
    asyncio.run(main())
