"""
Metrics collection LOATS13July2026 using prometheus_client.
"""

import time
from typing import Any, Optional

from prometheus_client import Counter, Gauge, Summary, start_http_server

from .loats_logging import get_logger

logger = get_logger(__name__)


class MetricsManager:
    """Singleton manager Prometheus metrics prevent duplicate registration."""

    _instance: Optional["MetricsManager"] = None
    _initialized: bool = False

    def __new__(cls) -> "MetricsManager":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        if getattr(self, "_initialized", False):
            return
        # 1. Job Execution Counters
        self.job_execution_counter = Counter(
            "loats_job_executions_total",
            "Total number job executions",
            ["job_id", "status"],
        )
        # 2. Job Execution Latency
        self.job_latency_summary = Summary(
            "loats_job_latency_seconds", "Latency job executions seconds", ["job_id"]
        )
        # 3. Signals Generated
        self.signals_generated_counter = Counter(
            "loats_signals_generated_total",
            "Total number trading signals generated",
            ["signal_type", "scan_type"],
        )
        # 4. System Status Gauges
        self.kill_switch_status = Gauge(
            "loats_kill_switch_active",
            "Kill switch status (1 for active, 0 for inactive)",
        )
        self.circuit_breaker_status = Gauge(
            "loats_circuit_breaker_open",
            "Circuit breaker status (1 for open, 0 for closed)",
            ["component"],
        )
        self._server_started: bool = False
        self._initialized = True

    def reset_for_testing(self) -> None:
        """Reset the metrics manager state for testing purposes.
        This method should only be used in test environments to ensure test isolation.
        """
        if hasattr(self, "_server_started"):
            self._server_started = False

    def start_server(self, port: int = 8001) -> None:
        """Start Prometheus metrics server."""
        if self._server_started:
            logger.info("Prometheus metrics server already running")
            return
        try:
            start_http_server(port)
            self._server_started = True
            logger.info(f"Prometheus metrics server started port {port}")
        except Exception as e:
            logger.error(f"Failed start Prometheus metrics server: {e}")


# Initialize the singleton
metrics = MetricsManager()


def start_metrics_server(port: int = 8001) -> None:
    """Start Prometheus metrics server singleton."""
    metrics.start_server(port)


def track_job(job_id: str) -> Any:
    """Decorator track job execution time status."""

    def decorator(func: Any) -> Any:
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            start_time = time.time()
            status = "success"
            try:
                result = await func(*args, **kwargs)
                return result
            except Exception:
                status = "failure"
                raise
            finally:
                duration = time.time() - start_time
                try:
                    metrics.job_execution_counter.labels(
                        job_id=job_id, status=status
                    ).inc()
                except Exception:
                    # Silently handle metrics errors to not interfere with job execution
                    pass
                try:
                    metrics.job_latency_summary.labels(job_id=job_id).observe(duration)
                except Exception:
                    # Silently handle metrics errors to not interfere with job execution
                    pass

        return wrapper

    return decorator


def record_signal(signal_type: str, scan_type: str) -> None:
    """Record signal generation event."""
    try:
        metrics.signals_generated_counter.labels(
            signal_type=signal_type, scan_type=scan_type
        ).inc()
    except Exception:
        # Silently handle metrics errors to not interfere with application flow
        pass


def set_kill_switch_status(active: bool) -> None:
    """Set kill switch status metric."""
    try:
        metrics.kill_switch_status.set(1 if active else 0)
    except Exception:
        # Silently handle metrics errors to not interfere with application flow
        pass


def set_circuit_breaker_status(component: str, open_status: bool) -> None:
    """Set circuit breaker status metric."""
    try:
        metrics.circuit_breaker_status.labels(component=component).set(
            1 if open_status else 0
        )
    except Exception:
        # Silently handle metrics errors to not interfere with application flow
        pass
