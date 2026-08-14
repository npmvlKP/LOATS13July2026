"""
Lightweight metrics collection for LOATS13July2026 LITE edition.
Implements simple in-memory metrics tracking without external dependencies.
"""

import functools
import threading
import time
from collections.abc import Callable, Coroutine
from typing import Any, Optional, TypeVar, cast

from .loats_logging import get_logger


# Lightweight replacements for the MagicMock based test stubs.
class _Metric:
    """Simple metric object exposing ``inc``, ``observe`` and ``set`` methods.
    Invokes the bound ``callback`` when a metric method is called.
    """

    def __init__(self, callback: Callable[..., Any]) -> None:
        self._callback = callback

    def inc(self) -> None:
        self._callback()

    def observe(self, value: Any) -> None:
        self._callback(value)

    def set(self, value: Any) -> None:
        self._callback(value)


class _MetricFactory:
    """Factory returning a metric object bound to ``labels`` and a callback.

    Mimics Prometheus' ``Counter.labels(...)`` API. Label values are bound at
    ``labels()`` time and forwarded positionally (in keyword-call order) to the
    tracker callback; the value passed to ``inc``/``observe``/``set`` is
    appended after them. This matches each tracker's
    ``(label..., value)`` signature, e.g. ``_track_latency_via_mock(job_id, duration)``.
    """

    def __init__(self, callback: Callable[..., Any]) -> None:
        self._callback = callback

    def labels(self, **label_kwargs: Any) -> _Metric:
        bound = tuple(label_kwargs.values())
        return _Metric(lambda *args: self._callback(*bound, *args))


class _SimpleSetter:
    """Wrapper exposing a ``set`` method that forwards to ``callback``.
    Used for boolean style metrics.
    """

    def __init__(self, callback: Callable[[Any], Any]) -> None:
        self._callback = callback

    def set(self, value: Any) -> None:
        self._callback(value)


logger = get_logger(__name__)


@functools.lru_cache(maxsize=1)
class MetricsManager:
    """Lightweight metrics manager for LOATS13July2026 LITE edition.
    Uses in-memory tracking to avoid external dependencies like Prometheus.
    """

    def __init__(self) -> None:
        # Lightweight in-memory metrics with proper type annotations
        self.job_execution_stats: dict[str, int] = {
            "success": 0,
            "failure": 0,
            "total": 0,
        }
        self.job_latency_stats: dict[str, float | int] = {
            "total_seconds": 0.0,
            "count": 0,
            "min_seconds": float("inf"),
            "max_seconds": 0.0,
        }
        self.signals_generated_stats: dict[str, Any] = {
            "total": 0,
            "by_type": {},
            "by_scan_type": {},
        }
        self.system_status: dict[str, Any] = {
            "kill_switch_active": False,
            "circuit_breaker_status": {},
        }
        # Add cycle time stats for performance monitoring
        self.cycle_time_stats: dict[str, Any] = {
            "total_seconds": 0.0,
            "count": 0,
            "min_seconds": float("inf"),
            "max_seconds": 0.0,
            "target_compliance_count": 0,
        }

        # Lightweight stub objects mimicking Prometheus metrics API used in tests.
        # Avoid importing unittest.mock in production code.
        self.job_execution_counter = _MetricFactory(self._track_job_via_mock)
        self.job_latency_summary = _MetricFactory(self._track_latency_via_mock)
        self.signals_generated_counter = _MetricFactory(self._record_signal_via_mock)
        self.kill_switch_status = _SimpleSetter(self._set_kill_switch_via_mock)
        self.circuit_breaker_status = _MetricFactory(self._set_circuit_breaker_via_mock)

        self._server_started = False
        self._initialized = True
        logger.info("Lightweight metrics manager initialized")

    def _track_job_via_mock(self, job_id: str, status: str) -> None:
        """Track job execution via mock interface."""
        try:
            self.job_execution_stats["total"] += 1
            if status == "success":
                self.job_execution_stats["success"] += 1
            else:
                self.job_execution_stats["failure"] += 1
        except Exception as e:
            logger.warning(f"Failed to track job execution via mock: {e}")

    def _track_latency_via_mock(self, job_id: str, duration: float) -> None:
        """Track job latency via mock interface."""
        try:
            self.job_latency_stats["total_seconds"] += duration
            self.job_latency_stats["count"] += 1
            self.job_latency_stats["min_seconds"] = min(
                self.job_latency_stats["min_seconds"], duration
            )
            self.job_latency_stats["max_seconds"] = max(
                self.job_latency_stats["max_seconds"], duration
            )
        except Exception as e:
            logger.warning(f"Failed to track job latency via mock: {e}")

    def _record_signal_via_mock(self, signal_type: str, scan_type: str) -> None:
        """Record signal via mock interface."""
        try:
            self.signals_generated_stats["total"] += 1

            # Update by type
            if signal_type not in self.signals_generated_stats["by_type"]:
                self.signals_generated_stats["by_type"][signal_type] = 0
            self.signals_generated_stats["by_type"][signal_type] += 1

            # Update by scan type
            if scan_type not in self.signals_generated_stats["by_scan_type"]:
                self.signals_generated_stats["by_scan_type"][scan_type] = 0
            self.signals_generated_stats["by_scan_type"][scan_type] += 1
        except Exception as e:
            logger.warning(f"Failed to record signal via mock: {e}")

    def _set_kill_switch_via_mock(self, value: int) -> None:
        """Set kill switch status via mock interface."""
        try:
            self.system_status["kill_switch_active"] = bool(value)
        except Exception as e:
            logger.warning(f"Failed to set kill switch via mock: {e}")

    def _set_circuit_breaker_via_mock(self, component: str, value: int) -> None:
        """Set circuit breaker status via mock interface."""
        try:
            self.system_status["circuit_breaker_status"][component] = bool(value)
        except Exception as e:
            logger.warning(f"Failed to set circuit breaker via mock: {e}")

    def reset_for_testing(self) -> None:
        """Reset the metrics manager state for testing purposes."""
        # Clear the lru_cache to get a fresh instance
        MetricsManager.cache_clear()  # type: ignore[attr-defined]
        # Clear all metrics
        self.job_execution_stats = {"success": 0, "failure": 0, "total": 0}
        self.job_latency_stats = {
            "total_seconds": 0.0,
            "count": 0,
            "min_seconds": float("inf"),
            "max_seconds": 0.0,
        }
        self.signals_generated_stats = {
            "total": 0,
            "by_type": {},
            "by_scan_type": {},
        }
        self.system_status = {
            "kill_switch_active": False,
            "circuit_breaker_status": {},
        }

    def set_kill_switch_status(self, active: bool) -> None:
        """Set kill switch status metric."""
        try:
            self.system_status["kill_switch_active"] = active
            # Also update the Prometheus-style metric for consistency
            self.kill_switch_status.set(1 if active else 0)
        except Exception as e:
            logger.warning(f"Failed to set kill switch status: {e}")

    def set_circuit_breaker_status(self, component: str, open_status: bool) -> None:
        """Set circuit breaker status metric."""
        try:
            self.system_status["circuit_breaker_status"][component] = open_status
            # Also update the Prometheus-style metric for consistency
            self.circuit_breaker_status.labels(component=component).set(
                1 if open_status else 0
            )
        except Exception as e:
            logger.warning(f"Failed to set circuit breaker status: {e}")

    def get_metrics_summary(self) -> dict[str, Any]:
        """Get summary of all metrics."""
        try:
            avg_latency = (
                self.job_latency_stats["total_seconds"]
                / self.job_latency_stats["count"]
                if self.job_latency_stats["count"] > 0
                else 0.0
            )

            return {
                "job_executions": {
                    "success": self.job_execution_stats["success"],
                    "failure": self.job_execution_stats["failure"],
                    "total": self.job_execution_stats["total"],
                    "success_rate": (
                        self.job_execution_stats["success"]
                        / self.job_execution_stats["total"]
                        if self.job_execution_stats["total"] > 0
                        else 0.0
                    ),
                },
                "job_latency": {
                    "average_seconds": avg_latency,
                    "min_seconds": self.job_latency_stats["min_seconds"],
                    "max_seconds": self.job_latency_stats["max_seconds"],
                    "total_seconds": self.job_latency_stats["total_seconds"],
                    "count": self.job_latency_stats["count"],
                },
                "signals_generated": {
                    "total": self.signals_generated_stats["total"],
                    "by_type": self.signals_generated_stats["by_type"],
                    "by_scan_type": self.signals_generated_stats["by_scan_type"],
                },
                "system_status": self.system_status,
                "cycle_time_stats": {
                    "total_seconds": self.cycle_time_stats["total_seconds"],
                    "count": self.cycle_time_stats["count"],
                    "min_seconds": self.cycle_time_stats["min_seconds"],
                    "max_seconds": self.cycle_time_stats["max_seconds"],
                    "target_compliance_count": self.cycle_time_stats[
                        "target_compliance_count"
                    ],
                    "average_seconds": (
                        self.cycle_time_stats["total_seconds"]
                        / self.cycle_time_stats["count"]
                        if self.cycle_time_stats["count"] > 0
                        else 0.0
                    ),
                },
            }
        except Exception as e:
            logger.error(f"Failed to get metrics summary: {e}")
            return {"error": str(e)}

    def start_server(self, port: int = 8001) -> None:
        """Start the metrics server (lightweight implementation for LITE edition)."""
        if self._server_started:
            logger.info("Metrics server already running")
            return

        try:
            # LITE edition: start lightweight HTTP server (stdlib only).
            start_http_server(port)
            self._server_started = True
            logger.info(f"Lightweight metrics server started on port {port}")
        except Exception as e:
            logger.error(f"Failed to start metrics server: {e}")
            self._server_started = False


# Initialize the singleton
metrics = MetricsManager()

F = TypeVar("F", bound=Callable[..., Any])


def track_job(job_id: str, manager: "MetricsManager | None" = None) -> Callable[[F], F]:
    """Decorator to track job execution time and status."""

    def decorator(func: F) -> F:
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
                    # Use the provided manager or global metrics instance
                    (manager or metrics).job_execution_counter.labels(
                        job_id=job_id, status=status
                    ).inc()
                    (manager or metrics).job_latency_summary.labels(
                        job_id=job_id
                    ).observe(duration)
                except Exception:  # nosec B110
                    # Silently handle metrics errors to not interfere with job execution
                    pass

        return cast(F, wrapper)

    return decorator


def record_cycle_time(duration: float) -> None:
    """Record trading cycle execution time."""
    try:
        # Use existing cycle_time_stats attribute
        # (already initialized in MetricsManager.__init__)

        metrics.cycle_time_stats["total_seconds"] += duration
        metrics.cycle_time_stats["count"] += 1
        metrics.cycle_time_stats["min_seconds"] = min(
            metrics.cycle_time_stats["min_seconds"], duration
        )
        metrics.cycle_time_stats["max_seconds"] = max(
            metrics.cycle_time_stats["max_seconds"], duration
        )

        # Track target compliance (<100ms)
        if duration <= 0.1:  # 100ms target
            metrics.cycle_time_stats["target_compliance_count"] += 1

    except Exception:  # nosec B110
        # Silently handle metrics errors to not interfere with application flow
        pass


def record_signal(
    signal_type: str, scan_type: str, manager: "MetricsManager | None" = None
) -> None:
    """Record signal generation event."""
    try:
        (manager or metrics).signals_generated_counter.labels(
            signal_type=signal_type, scan_type=scan_type
        ).inc()
    except Exception:  # nosec B110
        # Silently handle metrics errors to not interfere with application flow
        pass


def set_kill_switch_status(
    active: bool, manager: "MetricsManager | None" = None
) -> None:
    """Set kill switch status metric."""
    try:
        (manager or metrics).kill_switch_status.set(1 if active else 0)
    except Exception:  # nosec B110
        # Silently handle metrics errors to not interfere with application flow
        pass


def set_circuit_breaker_status(
    component: str, open_status: bool, manager: "MetricsManager | None" = None
) -> None:
    """Set circuit breaker status metric."""
    try:
        (manager or metrics).circuit_breaker_status.labels(component=component).set(
            1 if open_status else 0
        )
    except Exception:  # nosec B110
        # Silently handle metrics errors to not interfere with application flow
        pass


def get_metrics_summary() -> dict[str, Any]:
    """Get summary of all metrics."""
    return metrics.get_metrics_summary()


def start_metrics_server(port: int = 8001) -> None:
    """Start the metrics server (standalone function for compatibility)."""
    manager = MetricsManager()
    manager.start_server(port)


def start_http_server(port: int) -> None:
    """Start a lightweight HTTP server exposing metrics as JSON.

    LITE edition: serves :func:`get_metrics_summary` over HTTP from a
    background daemon thread. No external Prometheus dependency required.
    """
    import json as _json
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    class _MetricsHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            body = _json.dumps(get_metrics_summary()).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, msg: str, *args: Any) -> None:
            logger.debug("Metrics HTTP: %s", msg % args)

    server = ThreadingHTTPServer(("127.0.0.1", port), _MetricsHandler)
    thread = threading.Thread(
        target=server.serve_forever,
        daemon=True,
        name=f"metrics-http-server-{port}",
    )
    thread.start()
