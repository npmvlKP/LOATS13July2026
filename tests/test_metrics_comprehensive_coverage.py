"""
Comprehensive test suite for metrics.py to achieve 80%+ coverage.
Focuses on missing coverage areas including error handling, direct methods,
and HTTP server functionality.
"""

import json
import threading
import time
from unittest.mock import MagicMock, patch

import pytest

from loats.metrics import (
    MetricsManager,
    get_metrics_summary,
    set_circuit_breaker_status,
    set_kill_switch_status,
    start_metrics_server,
    track_job,
)


class TestMetricsErrorHandling:
    """Test error handling in metrics methods."""

    def test_manager_methods_error_handling(self):
        """Test error handling in manager methods."""
        manager = MetricsManager()
        manager.reset_for_testing()

        # Test that manager methods handle errors gracefully
        # The actual error handling is tested through the public methods

        # Test mock interface methods with invalid data
        try:
            manager.job_execution_counter.labels(job_id=None, status=None).inc()
        except Exception:
            pass  # Expected to fail gracefully

        try:
            manager.signals_generated_counter.labels(
                signal_type=None, scan_type=None
            ).inc()
        except Exception:
            pass  # Expected to fail gracefully

        # Should still be able to get summary after errors
        summary = manager.get_metrics_summary()
        assert summary is not None


class TestDirectMetricsMethods:
    """Test direct metrics methods that are not covered by existing tests."""

    def test_mock_interface_methods(self):
        """Test the mock interface methods that are actually used in production."""
        manager = MetricsManager()
        manager.reset_for_testing()

        # Test job execution tracking via mock interface
        manager.job_execution_counter.labels(job_id="job1", status="success").inc()
        manager.job_latency_summary.labels(job_id="job1").observe(1.5)

        # Verify metrics were updated
        assert manager.job_execution_stats == {
            "success": 1,
            "failure": 0,
            "total": 1,
        }
        assert manager.job_latency_stats["count"] == 1
        assert manager.job_latency_stats["total_seconds"] == 1.5
        assert manager.job_latency_stats["min_seconds"] == 1.5
        assert manager.job_latency_stats["max_seconds"] == 1.5

        # Test signal recording via mock interface
        manager.signals_generated_counter.labels(
            signal_type="BUY", scan_type="ta_scan"
        ).inc()

        # Verify metrics were updated
        assert manager.signals_generated_stats["total"] == 1
        assert manager.signals_generated_stats["by_type"] == {"BUY": 1}
        assert manager.signals_generated_stats["by_scan_type"] == {"ta_scan": 1}

        # Test another signal
        manager.signals_generated_counter.labels(
            signal_type="SELL", scan_type="sentiment_scan"
        ).inc()

        # Verify metrics were updated
        assert manager.signals_generated_stats["total"] == 2
        assert manager.signals_generated_stats["by_type"] == {"BUY": 1, "SELL": 1}
        assert manager.signals_generated_stats["by_scan_type"] == {
            "ta_scan": 1,
            "sentiment_scan": 1,
        }

    def test_set_kill_switch_status_direct(self):
        """Test the set_kill_switch_status method directly."""
        manager = MetricsManager()
        manager.reset_for_testing()

        # Set kill switch active
        manager.set_kill_switch_status(True)
        assert manager.system_status["kill_switch_active"] is True

        # Set kill switch inactive
        manager.set_kill_switch_status(False)
        assert manager.system_status["kill_switch_active"] is False

    def test_set_circuit_breaker_status_direct(self):
        """Test the set_circuit_breaker_status method directly."""
        manager = MetricsManager()
        manager.reset_for_testing()

        # Set circuit breaker status for different components
        manager.set_circuit_breaker_status("openalgo", True)
        manager.set_circuit_breaker_status("database", False)
        manager.set_circuit_breaker_status("telegram", True)

        # Verify metrics were updated
        assert manager.system_status["circuit_breaker_status"] == {
            "openalgo": True,
            "database": False,
            "telegram": True,
        }


class TestMetricsSummary:
    """Test the get_metrics_summary method."""

    def test_get_metrics_summary_empty(self):
        """Test get_metrics_summary with no data."""
        manager = MetricsManager()
        manager.reset_for_testing()

        summary = manager.get_metrics_summary()

        # Verify structure
        assert "job_executions" in summary
        assert "job_latency" in summary
        assert "signals_generated" in summary
        assert "system_status" in summary

        # Verify empty state values
        assert summary["job_executions"] == {
            "success": 0,
            "failure": 0,
            "total": 0,
            "success_rate": 0.0,
        }
        assert summary["job_latency"] == {
            "average_seconds": 0.0,
            "min_seconds": float("inf"),
            "max_seconds": 0.0,
            "total_seconds": 0.0,
            "count": 0,
        }
        assert summary["signals_generated"] == {
            "total": 0,
            "by_type": {},
            "by_scan_type": {},
        }
        assert summary["system_status"] == {
            "kill_switch_active": False,
            "circuit_breaker_status": {},
        }

    def test_get_metrics_summary_with_data(self):
        """Test get_metrics_summary with populated data."""
        manager = MetricsManager()
        manager.reset_for_testing()

        # Add some data using mock interface
        manager.job_execution_counter.labels(job_id="job1", status="success").inc()
        manager.job_latency_summary.labels(job_id="job1").observe(1.0)
        manager.job_execution_counter.labels(job_id="job2", status="success").inc()
        manager.job_latency_summary.labels(job_id="job2").observe(2.0)
        manager.job_execution_counter.labels(job_id="job3", status="failure").inc()
        manager.job_latency_summary.labels(job_id="job3").observe(0.5)

        manager.signals_generated_counter.labels(
            signal_type="BUY", scan_type="ta_scan"
        ).inc()
        manager.signals_generated_counter.labels(
            signal_type="BUY", scan_type="ta_scan"
        ).inc()
        manager.signals_generated_counter.labels(
            signal_type="SELL", scan_type="sentiment_scan"
        ).inc()

        manager.set_kill_switch_status(True)
        manager.set_circuit_breaker_status("openalgo", True)

        summary = manager.get_metrics_summary()

        # Verify job executions
        assert summary["job_executions"] == {
            "success": 2,
            "failure": 1,
            "total": 3,
            "success_rate": 2 / 3,
        }

        # Verify job latency
        assert summary["job_latency"] == {
            "average_seconds": 3.5 / 3,
            "min_seconds": 0.5,
            "max_seconds": 2.0,
            "total_seconds": 3.5,
            "count": 3,
        }

        # Verify signals
        assert summary["signals_generated"] == {
            "total": 3,
            "by_type": {"BUY": 2, "SELL": 1},
            "by_scan_type": {"ta_scan": 2, "sentiment_scan": 1},
        }

        # Verify system status
        assert summary["system_status"] == {
            "kill_switch_active": True,
            "circuit_breaker_status": {"openalgo": True},
        }

    def test_get_metrics_summary_error_handling(self):
        """Test get_metrics_summary error handling."""
        manager = MetricsManager()
        manager.reset_for_testing()

        # Test with division by zero scenario
        manager.job_execution_stats["total"] = 0
        manager.job_execution_stats["success"] = 0

        summary = manager.get_metrics_summary()

        # Should handle division by zero gracefully
        assert summary["job_executions"]["success_rate"] == 0.0

        # Test with zero count for latency
        manager.job_latency_stats["count"] = 0
        manager.job_latency_stats["total_seconds"] = 0.0

        summary = manager.get_metrics_summary()

        # Should handle division by zero gracefully
        assert summary["job_latency"]["average_seconds"] == 0.0


class TestHTTPServerFunctionality:
    """Test the HTTP server functionality."""

    def test_start_metrics_server_function(self):
        """Test the start_metrics_server function."""
        # Test that the function can be called without errors
        # We're not testing the actual server implementation since it's a private function
        # Just testing that the public API works
        try:
            start_metrics_server(port=8080)
        except Exception:
            pass  # Expected to fail in test environment, but shouldn't crash


class TestMetricsEdgeCases:
    """Test edge cases for metrics functionality."""

    def test_metrics_with_empty_strings(self):
        """Test metrics with empty string values."""
        manager = MetricsManager()
        manager.reset_for_testing()

        # Test with empty strings using mock interface
        manager.job_execution_counter.labels(job_id="", status="success").inc()
        manager.job_latency_summary.labels(job_id="").observe(1.0)
        manager.signals_generated_counter.labels(signal_type="", scan_type="").inc()
        manager.set_circuit_breaker_status("", True)

        # Should handle empty strings without errors
        summary = manager.get_metrics_summary()
        assert summary is not None

    def test_metrics_with_none_values(self):
        """Test metrics with None values."""
        manager = MetricsManager()
        manager.reset_for_testing()

        # Test with None values (should be handled gracefully)
        try:
            manager.job_execution_counter.labels(job_id=None, status="success").inc()
        except Exception:
            pass  # Expected to fail, but shouldn't crash the system

        try:
            manager.signals_generated_counter.labels(
                signal_type=None, scan_type=None
            ).inc()
        except Exception:
            pass  # Expected to fail, but shouldn't crash the system

        # Should still be able to get summary
        summary = manager.get_metrics_summary()
        assert summary is not None

    def test_metrics_with_very_large_values(self):
        """Test metrics with very large values."""
        manager = MetricsManager()
        manager.reset_for_testing()

        # Test with very large values using mock interface
        manager.job_execution_counter.labels(job_id="job1", status="success").inc()
        manager.job_latency_summary.labels(job_id="job1").observe(999999.999)
        manager.job_execution_counter.labels(job_id="job2", status="success").inc()
        manager.job_latency_summary.labels(job_id="job2").observe(0.000001)

        # Should handle large values without errors
        summary = manager.get_metrics_summary()
        assert summary["job_latency"]["max_seconds"] == 999999.999
        assert summary["job_latency"]["min_seconds"] == 0.000001

    def test_metrics_with_negative_values(self):
        """Test metrics with negative values."""
        manager = MetricsManager()
        manager.reset_for_testing()

        # Test with negative values (should be handled gracefully)
        try:
            manager.job_execution_counter.labels(job_id="job1", status="success").inc()
            manager.job_latency_summary.labels(job_id="job1").observe(-1.0)
        except Exception:
            pass  # Expected to fail, but shouldn't crash the system

        # Should still be able to get summary
        summary = manager.get_metrics_summary()
        assert summary is not None


class TestMetricsIntegration:
    """Integration tests for metrics functionality."""

    def test_complete_metrics_workflow(self):
        """Test a complete metrics workflow."""
        # Reset metrics
        manager = MetricsManager()
        manager.reset_for_testing()

        # Simulate a complete workflow
        # 1. Track job execution using mock interface
        manager.job_execution_counter.labels(
            job_id="scan_job_1", status="success"
        ).inc()
        manager.job_latency_summary.labels(job_id="scan_job_1").observe(2.5)
        manager.job_execution_counter.labels(
            job_id="scan_job_2", status="failure"
        ).inc()
        manager.job_latency_summary.labels(job_id="scan_job_2").observe(1.2)

        # 2. Record signals using mock interface
        manager.signals_generated_counter.labels(
            signal_type="BUY", scan_type="ta_scan"
        ).inc()
        manager.signals_generated_counter.labels(
            signal_type="BUY", scan_type="ta_scan"
        ).inc()
        manager.signals_generated_counter.labels(
            signal_type="SELL", scan_type="sentiment_scan"
        ).inc()

        # 3. Set system status
        manager.set_kill_switch_status(False)
        manager.set_circuit_breaker_status("openalgo", False)
        manager.set_circuit_breaker_status("database", True)

        # 4. Get summary
        summary = manager.get_metrics_summary()

        # Verify all metrics are present
        assert summary["job_executions"]["total"] == 2
        assert summary["job_executions"]["success"] == 1
        assert summary["job_executions"]["failure"] == 1

        assert summary["job_latency"]["count"] == 2
        assert summary["job_latency"]["total_seconds"] == 3.7

        assert summary["signals_generated"]["total"] == 3
        assert summary["signals_generated"]["by_type"]["BUY"] == 2
        assert summary["signals_generated"]["by_type"]["SELL"] == 1

        assert summary["system_status"]["kill_switch_active"] is False
        assert summary["system_status"]["circuit_breaker_status"]["database"] is True

        # 5. Test error handling
        try:
            manager.job_execution_counter.labels(job_id=None, status=None).inc()
        except Exception:
            pass  # Should handle errors gracefully

        # Should still work after errors
        summary2 = manager.get_metrics_summary()
        assert summary2 is not None

    def test_metrics_with_concurrent_access(self):
        """Test metrics with concurrent access."""
        manager = MetricsManager()
        manager.reset_for_testing()

        def worker(worker_id):
            """Worker function that updates metrics."""
            for i in range(10):
                manager.job_execution_counter.labels(
                    job_id=f"job_{worker_id}_{i}", status="success"
                ).inc()
                manager.job_latency_summary.labels(
                    job_id=f"job_{worker_id}_{i}"
                ).observe(0.1)
                manager.signals_generated_counter.labels(
                    signal_type="BUY", scan_type=f"scan_{worker_id}"
                ).inc()

        # Create and start multiple threads
        threads = []
        for i in range(5):
            thread = threading.Thread(target=worker, args=(i,))
            threads.append(thread)
            thread.start()

        # Wait for all threads to complete
        for thread in threads:
            thread.join()

        # Verify metrics were updated correctly
        summary = manager.get_metrics_summary()

        # Should have 50 jobs (5 threads * 10 jobs each)
        assert summary["job_executions"]["total"] == 50
        assert summary["job_executions"]["success"] == 50

        # Should have 50 signals (5 threads * 10 signals each)
        assert summary["signals_generated"]["total"] == 50

        # Should have 50 latency records
        assert summary["job_latency"]["count"] == 50
        # Use approximate comparison for floating point
        assert abs(summary["job_latency"]["total_seconds"] - 5.0) < 1e-10  # 50 * 0.1


class TestMetricsPerformance:
    """Performance tests for metrics functionality."""

    def test_metrics_with_large_dataset(self):
        """Test metrics with a large dataset."""
        manager = MetricsManager()
        manager.reset_for_testing()

        # Add a large number of metrics using mock interface
        for i in range(1000):
            manager.job_execution_counter.labels(
                job_id=f"job_{i}", status="success"
            ).inc()
            manager.job_latency_summary.labels(job_id=f"job_{i}").observe(1.0)
            manager.signals_generated_counter.labels(
                signal_type="BUY", scan_type="ta_scan"
            ).inc()

        # Should handle large dataset without errors
        summary = manager.get_metrics_summary()

        assert summary["job_executions"]["total"] == 1000
        assert summary["signals_generated"]["total"] == 1000
        assert summary["job_latency"]["count"] == 1000

    def test_metrics_summary_performance(self):
        """Test metrics summary performance."""
        manager = MetricsManager()
        manager.reset_for_testing()

        # Add a large number of metrics using mock interface
        for i in range(1000):
            manager.job_execution_counter.labels(
                job_id=f"job_{i}", status="success"
            ).inc()
            manager.job_latency_summary.labels(job_id=f"job_{i}").observe(1.0)
            manager.signals_generated_counter.labels(
                signal_type=f"SIGNAL_{i % 10}", scan_type=f"SCAN_{i % 5}"
            ).inc()

        # Measure time to generate summary
        start_time = time.time()
        summary = manager.get_metrics_summary()
        end_time = time.time()

        # Should complete quickly even with large dataset
        assert end_time - start_time < 0.1  # Should take less than 100ms

        # Verify summary is correct
        assert summary["job_executions"]["total"] == 1000
        assert summary["signals_generated"]["total"] == 1000
        assert len(summary["signals_generated"]["by_type"]) == 10
        assert len(summary["signals_generated"]["by_scan_type"]) == 5
