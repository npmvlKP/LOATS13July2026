"""
Unit tests for metrics module.
Tests Prometheus metrics collection and tracking functionality.
"""

import time
from unittest.mock import MagicMock, patch

import pytest

from src.loats.metrics import (
    MetricsManager,
    record_signal,
    set_circuit_breaker_status,
    set_kill_switch_status,
    start_metrics_server,
    track_job,
)


class TestMetricsManager:
    """Tests for MetricsManager singleton."""

    def test_metrics_manager_singleton(self) -> None:
        """Test that MetricsManager is a singleton."""
        # Get multiple instances
        manager1 = MetricsManager()
        manager2 = MetricsManager()

        # Should be the same instance
        assert manager1 is manager2

        # Should have initialized metrics
        assert hasattr(manager1, "job_execution_counter")
        assert hasattr(manager1, "job_latency_summary")
        assert hasattr(manager1, "signals_generated_counter")
        assert hasattr(manager1, "kill_switch_status")
        assert hasattr(manager1, "circuit_breaker_status")

    def test_metrics_manager_initialization(self) -> None:
        """Test MetricsManager initialization."""
        manager = MetricsManager()

        # Check that all metrics are initialized
        assert manager.job_execution_counter is not None
        assert manager.job_latency_summary is not None
        assert manager.signals_generated_counter is not None
        assert manager.kill_switch_status is not None
        assert manager.circuit_breaker_status is not None

        # Check initial server state
        assert manager._server_started is False

    def test_metrics_manager_double_initialization(self) -> None:
        """Test that MetricsManager handles double initialization correctly."""
        # First initialization
        manager1 = MetricsManager()
        assert manager1._initialized is True

        # Second initialization should return same instance without reinitializing
        manager2 = MetricsManager()
        assert manager2 is manager1
        assert manager2._initialized is True

    def test_labels_counter_records_job_execution(self) -> None:
        """Real path: labels().inc() must record job execution stats."""
        manager = MetricsManager()
        manager.reset_for_testing()

        manager.job_execution_counter.labels(job_id="j1", status="success").inc()
        manager.job_execution_counter.labels(job_id="j2", status="failure").inc()

        assert manager.job_execution_stats == {
            "success": 1,
            "failure": 1,
            "total": 2,
        }

    def test_labels_summary_observe_records_latency(self) -> None:
        """Real path: labels().observe(value) must record the observed value."""
        manager = MetricsManager()
        manager.reset_for_testing()

        manager.job_latency_summary.labels(job_id="j1").observe(1.25)
        manager.job_latency_summary.labels(job_id="j1").observe(0.5)

        assert manager.job_latency_stats["count"] == 2
        assert manager.job_latency_stats["total_seconds"] == 1.75
        assert manager.job_latency_stats["min_seconds"] == 0.5
        assert manager.job_latency_stats["max_seconds"] == 1.25

    def test_labels_gauge_set_records_circuit_breaker(self) -> None:
        """Real path: labels().set(value) must record circuit breaker status."""
        manager = MetricsManager()
        manager.reset_for_testing()

        manager.circuit_breaker_status.labels(component="openalgo").set(1)
        manager.circuit_breaker_status.labels(component="telegram").set(0)

        assert manager.system_status["circuit_breaker_status"] == {
            "openalgo": True,
            "telegram": False,
        }

    def test_kill_switch_setter_records_status(self) -> None:
        """Real path: kill_switch_status.set(value) must record status."""
        manager = MetricsManager()
        manager.reset_for_testing()

        manager.kill_switch_status.set(1)
        manager.kill_switch_status.set(0)

        assert manager.system_status["kill_switch_active"] is False

    def test_signals_counter_records_signal(self) -> None:
        """Real path: labels().inc() must record signal stats."""
        manager = MetricsManager()
        manager.reset_for_testing()

        manager.signals_generated_counter.labels(
            signal_type="BUY", scan_type="ta"
        ).inc()

        assert manager.signals_generated_stats["total"] == 1
        assert manager.signals_generated_stats["by_type"] == {"BUY": 1}
        assert manager.signals_generated_stats["by_scan_type"] == {"ta": 1}


class TestMetricsServer:
    """Tests for metrics server functionality."""

    def test_start_metrics_server_default_port(self) -> None:
        """Test starting metrics server with default port."""
        manager = MetricsManager()

        # Mock the start_http_server function
        with patch("src.loats.metrics.start_http_server") as mock_start_server:
            manager.start_server()

            # Should call start_http_server with default port
            mock_start_server.assert_called_once_with(8001)

            # Server should be marked as started
            assert manager._server_started is True

    def test_start_metrics_server_custom_port(self) -> None:
        """Test starting metrics server with custom port."""
        manager = MetricsManager()

        # Mock the start_http_server function
        with patch("src.loats.metrics.start_http_server") as mock_start_server:
            manager.start_server(port=9000)

            # Should call start_http_server with custom port
            mock_start_server.assert_called_once_with(9000)

            # Server should be marked as started
            assert manager._server_started is True

    def test_start_metrics_server_already_started(self) -> None:
        """Test starting metrics server when already started."""
        manager = MetricsManager()

        # Mock the start_http_server function
        with patch("src.loats.metrics.start_http_server") as mock_start_server:
            # Start server first time
            manager.start_server()
            mock_start_server.assert_called_once()

            # Try to start again
            manager.start_server()

            # Should not call start_http_server again
            mock_start_server.assert_called_once()

            # Should log that server is already running
            # (This would be verified by checking logs in a real test)

    def test_start_metrics_server_exception_handling(self) -> None:
        """Test metrics server exception handling."""
        manager = MetricsManager()

        # Mock the start_http_server function to raise exception
        with patch(
            "src.loats.metrics.start_http_server", side_effect=Exception("Port in use")
        ):
            # Should not raise exception
            manager.start_server()

            # Server should not be marked as started
            assert manager._server_started is False

    def test_start_metrics_server_function(self) -> None:
        """Test the start_metrics_server function."""
        # Mock the start_http_server function
        with patch("src.loats.metrics.start_http_server") as mock_start_server:
            start_metrics_server(port=8080)

            # Should call start_http_server with custom port
            mock_start_server.assert_called_once_with(8080)


class TestJobTracking:
    """Tests for job tracking functionality."""

    def test_track_job_decorator_success(self) -> None:
        """Test track_job decorator with successful job."""
        manager = MetricsManager()

        # Mock the metrics to track calls
        with patch.object(manager.job_execution_counter, "labels") as mock_labels:
            mock_counter = MagicMock()
            mock_labels.return_value = mock_counter

            with patch.object(
                manager.job_latency_summary, "labels"
            ) as mock_latency_labels:
                mock_summary = MagicMock()
                mock_latency_labels.return_value = mock_summary

                @track_job("test_job")
                async def test_job():
                    return "success"

                # Execute the async function
                import asyncio

                result = asyncio.run(test_job())

                # Should return the job result
                assert result == "success"

                # Should have recorded success metrics
                mock_labels.assert_called_once_with(job_id="test_job", status="success")
                mock_counter.inc.assert_called_once()
                mock_latency_labels.assert_called_once_with(job_id="test_job")
                mock_summary.observe.assert_called_once()

    def test_track_job_decorator_failure(self) -> None:
        """Test track_job decorator with failing job."""
        manager = MetricsManager()

        # Mock the metrics to track calls
        with patch.object(manager.job_execution_counter, "labels") as mock_labels:
            mock_counter = MagicMock()
            mock_labels.return_value = mock_counter

            with patch.object(
                manager.job_latency_summary, "labels"
            ) as mock_latency_labels:
                mock_summary = MagicMock()
                mock_latency_labels.return_value = mock_summary

                @track_job("test_job")
                async def test_job():
                    raise Exception("Job failed")

                # Execute the async function and expect exception
                import asyncio

                with pytest.raises(Exception, match="Job failed"):
                    asyncio.run(test_job())

                # Should have recorded failure metrics
                mock_labels.assert_called_once_with(job_id="test_job", status="failure")
                mock_counter.inc.assert_called_once()
                mock_latency_labels.assert_called_once_with(job_id="test_job")
                mock_summary.observe.assert_called_once()

    def test_track_job_decorator_latency_measurement(self) -> None:
        """Test track_job decorator latency measurement."""
        manager = MetricsManager()

        with patch.object(manager.job_latency_summary, "labels") as mock_latency_labels:
            mock_summary = MagicMock()
            mock_latency_labels.return_value = mock_summary

            @track_job("test_job")
            async def test_job():
                time.sleep(0.1)  # Simulate work
                return "success"

            # Execute the job
            import asyncio

            assert asyncio.run(test_job()) == "success"

            # Should have recorded latency
            mock_latency_labels.assert_called_once_with(job_id="test_job")
            mock_summary.observe.assert_called_once()

            # Check that latency was measured (should be around 0.1 seconds)
            observed_latency = mock_summary.observe.call_args[0][0]
            assert 0.05 <= observed_latency <= 0.2  # Allow some tolerance


class TestSignalRecording:
    """Tests for signal recording functionality."""

    def test_record_signal(self) -> None:
        """Test record_signal function."""
        manager = MetricsManager()

        with patch.object(manager.signals_generated_counter, "labels") as mock_labels:
            mock_counter = MagicMock()
            mock_labels.return_value = mock_counter

            # Record a signal
            record_signal(signal_type="BUY", scan_type="ta_scan")

            # Should have called the counter
            mock_labels.assert_called_once_with(signal_type="BUY", scan_type="ta_scan")
            mock_counter.inc.assert_called_once()

    def test_record_signal_different_types(self) -> None:
        """Test record_signal with different signal types."""
        manager = MetricsManager()

        with patch.object(manager.signals_generated_counter, "labels") as mock_labels:
            mock_counter = MagicMock()
            mock_labels.return_value = mock_counter

            # Record different signal types
            record_signal(signal_type="BUY", scan_type="ta_scan")
            record_signal(signal_type="SELL", scan_type="ta_scan")
            record_signal(signal_type="NEUTRAL", scan_type="sentiment_scan")

            # Should have called the counter three times
            assert mock_labels.call_count == 3
            assert mock_counter.inc.call_count == 3


class TestStatusMetrics:
    """Tests for status metrics functionality."""

    def test_set_kill_switch_status(self) -> None:
        """Test set_kill_switch_status function."""
        manager = MetricsManager()

        with patch.object(manager.kill_switch_status, "set") as mock_set:
            # Set kill switch active
            set_kill_switch_status(active=True)
            mock_set.assert_called_once_with(1)

            # Set kill switch inactive
            set_kill_switch_status(active=False)
            assert mock_set.call_count == 2
            mock_set.assert_called_with(0)

    def test_set_circuit_breaker_status(self) -> None:
        """Test set_circuit_breaker_status function."""
        manager = MetricsManager()

        with patch.object(manager.circuit_breaker_status, "labels") as mock_labels:
            mock_gauge = MagicMock()
            mock_labels.return_value = mock_gauge

            # Set circuit breaker status for different components
            set_circuit_breaker_status(component="openalgo", open_status=True)
            set_circuit_breaker_status(component="database", open_status=False)
            set_circuit_breaker_status(component="openalgo", open_status=True)

            # Should have called the gauge appropriately
            assert mock_labels.call_count == 3
            mock_labels.assert_any_call(component="openalgo")
            mock_labels.assert_any_call(component="database")
            assert mock_gauge.set.call_count == 3
            mock_gauge.set.assert_any_call(1)
            mock_gauge.set.assert_any_call(0)


class TestMetricsIntegration:
    """Integration tests for metrics functionality."""

    def test_metrics_lifecycle(self) -> None:
        """Test complete metrics lifecycle."""
        # Get metrics manager
        manager = MetricsManager()

        # Start metrics server
        with patch("src.loats.metrics.start_http_server"):
            manager.start_server(port=8001)

        # Record some signals
        with patch.object(manager.signals_generated_counter, "labels") as mock_labels:
            mock_counter = MagicMock()
            mock_labels.return_value = mock_counter

            record_signal(signal_type="BUY", scan_type="ta_scan")
            record_signal(signal_type="SELL", scan_type="sentiment_scan")

            assert mock_counter.inc.call_count == 2

        # Set status metrics
        with patch.object(manager.kill_switch_status, "set") as mock_set:
            set_kill_switch_status(active=True)
            mock_set.assert_called_once_with(1)

        # Test job tracking
        with patch.object(manager.job_execution_counter, "labels") as mock_job_labels:
            mock_job_counter = MagicMock()
            mock_job_labels.return_value = mock_job_counter

            with patch.object(
                manager.job_latency_summary, "labels"
            ) as mock_latency_labels:
                mock_summary = MagicMock()
                mock_latency_labels.return_value = mock_summary

                @track_job("integration_test")
                async def test_job():
                    return "success"

                import asyncio

                result = asyncio.run(test_job())
                assert result == "success"

                mock_job_labels.assert_called_once_with(
                    job_id="integration_test", status="success"
                )
                mock_job_counter.inc.assert_called_once()
                mock_latency_labels.assert_called_once_with(job_id="integration_test")
                mock_summary.observe.assert_called_once()

    def test_metrics_error_handling(self) -> None:
        """Test metrics error handling."""
        manager = MetricsManager()

        # Test with metrics that might fail
        with patch.object(
            manager.job_execution_counter,
            "labels",
            side_effect=Exception("Metrics error"),
        ):

            @track_job("error_test")
            async def test_job():
                return "success"

            import asyncio

            # Should not raise exception for metrics errors
            result = asyncio.run(test_job())
            assert result == "success"

        # Test signal recording with error
        with patch.object(
            manager.signals_generated_counter,
            "labels",
            side_effect=Exception("Metrics error"),
        ):
            # Should not raise exception
            record_signal(signal_type="BUY", scan_type="ta_scan")

        # Test status setting with error
        with patch.object(
            manager.kill_switch_status, "set", side_effect=Exception("Metrics error")
        ):
            # Should not raise exception
            set_kill_switch_status(active=True)


class TestMetricsEdgeCases:
    """Tests for metrics edge cases."""

    def test_track_job_with_exception_in_function(self) -> None:
        """Test track_job with exception in the decorated function."""
        manager = MetricsManager()

        with patch.object(manager.job_execution_counter, "labels") as mock_labels:
            mock_counter = MagicMock()
            mock_labels.return_value = mock_counter

            with patch.object(
                manager.job_latency_summary, "labels"
            ) as mock_latency_labels:
                mock_summary = MagicMock()
                mock_latency_labels.return_value = mock_summary

                @track_job("error_job")
                async def test_job():
                    raise ValueError("Test error")

                import asyncio

                with pytest.raises(ValueError, match="Test error"):
                    asyncio.run(test_job())

                # Should have recorded failure metrics
                mock_labels.assert_called_once_with(
                    job_id="error_job", status="failure"
                )
                mock_counter.inc.assert_called_once()
                mock_latency_labels.assert_called_once_with(job_id="error_job")
                mock_summary.observe.assert_called_once()

    def test_metrics_with_special_characters(self) -> None:
        """Test metrics with special characters in labels."""
        manager = MetricsManager()

        with patch.object(manager.signals_generated_counter, "labels") as mock_labels:
            mock_counter = MagicMock()
            mock_labels.return_value = mock_counter

            # Test with special characters
            record_signal(signal_type="BUY_SIGNAL_🚀", scan_type="ta-scan_v1.0")

            mock_labels.assert_called_once_with(
                signal_type="BUY_SIGNAL_🚀", scan_type="ta-scan_v1.0"
            )
            mock_counter.inc.assert_called_once()

        with patch.object(manager.circuit_breaker_status, "labels") as mock_labels:
            mock_gauge = MagicMock()
            mock_labels.return_value = mock_gauge

            set_circuit_breaker_status(component="openalgo-api_v2", open_status=True)
            mock_labels.assert_called_once_with(component="openalgo-api_v2")

    def test_multiple_metrics_managers(self) -> None:
        """Test that multiple metrics managers are actually the same instance."""
        manager1 = MetricsManager()
        manager2 = MetricsManager()
        manager3 = MetricsManager()

        # All should be the same instance
        assert manager1 is manager2
        assert manager2 is manager3
        assert manager1 is manager3

        # Test that metrics are shared by verifying they use the same counter object
        assert manager1.job_execution_counter is manager2.job_execution_counter
        assert manager2.job_execution_counter is manager3.job_execution_counter
        assert manager1.signals_generated_counter is manager2.signals_generated_counter

    def test_metrics_server_port_edge_cases(self) -> None:
        """Test metrics server with edge case port numbers."""
        manager = MetricsManager()

        # Test with very high port number
        with patch("src.loats.metrics.start_http_server") as mock_start_server:
            manager.start_server(port=65535)  # Maximum port number
            mock_start_server.assert_called_once_with(65535)

        # Reset for next test
        manager._server_started = False

        # Test with low port number
        with patch("src.loats.metrics.start_http_server") as mock_start_server:
            manager.start_server(port=1)  # Minimum port number
            mock_start_server.assert_called_once_with(1)

    def test_track_job_with_async_exception(self) -> None:
        """Test track_job with async exception handling."""
        manager = MetricsManager()

        with patch.object(manager.job_execution_counter, "labels") as mock_labels:
            mock_counter = MagicMock()
            mock_labels.return_value = mock_counter

            with patch.object(
                manager.job_latency_summary, "labels"
            ) as mock_latency_labels:
                mock_summary = MagicMock()
                mock_latency_labels.return_value = mock_summary

                @track_job("async_error_job")
                async def test_job():
                    await asyncio.sleep(0.01)  # Small async delay
                    raise RuntimeError("Async error")

                import asyncio

                async def run_test():
                    with pytest.raises(RuntimeError, match="Async error"):
                        await test_job()

                asyncio.run(run_test())

                # Should have recorded failure metrics
                mock_labels.assert_called_once_with(
                    job_id="async_error_job", status="failure"
                )
                mock_counter.inc.assert_called_once()
                mock_latency_labels.assert_called_once_with(job_id="async_error_job")
                mock_summary.observe.assert_called_once()
