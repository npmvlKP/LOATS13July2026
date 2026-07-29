"""
Metrics collection LOATS13July2026 using prometheus_client.
"""
import time

from prometheus_client import Counter, Gauge, Summary, start_http_server

from .loats_logging import get_logger

logger = get_logger(__name__)

# --- Metrics Definitions ---

# 1. Job Execution Counters (Success/Failure)
JOB_EXECUTION_COUNTER = Counter(
    "loats_job_executions_total",
    "Total number of job executions",
    ["job_id", "status"]
)

# 2. Job Execution Latency
JOB_LATENCY_SUMMARY = Summary(
    "loats_job_latency_seconds",
    "Latency of job executions in seconds",
    ["job_id"]
)

# 3. Signals Generated
SIGNALS_GENERATED_COUNTER = Counter(
    "loats_signals_generated_total",
    "Total number of trading signals generated",
    ["signal_type", "scan_type"]
)

# 4. System Status Gauges
KILL_SWITCH_STATUS = Gauge(
    "loats_kill_switch_active",
    "Kill switch status (1 for active, 0 for inactive)"
)

CIRCUIT_BREAKER_STATUS = Gauge(
    "loats_circuit_breaker_open",
    "Circuit breaker status (1 for open, 0 for closed)",
    ["component"]
)

def start_metrics_server(port: int = 8001) -> None:
    """Start Prometheus metrics server."""
    try:
        start_http_server(port)
        logger.info(f"Prometheus metrics server started on port {port}")
    except Exception as e:
        logger.error(f"Failed to start Prometheus metrics server: {e}")

def track_job(job_id: str):
    """Decorator to track job execution time and status."""
    def decorator(func):
        async def wrapper(*args, **kwargs):
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
                JOB_EXECUTION_COUNTER.labels(job_id=job_id, status=status).inc()
                JOB_LATENCY_SUMMARY.labels(job_id=job_id).observe(duration)
        return wrapper
    return decorator

def record_signal(signal_type: str, scan_type: str) -> None:
    """Record signal generation."""
    SIGNALS_GENERATED_COUNTER.labels(signal_type=signal_type, scan_type=scan_type).inc()

def set_kill_switch_status(active: bool) -> None:
    """Set kill switch status."""
    KILL_SWITCH_STATUS.set(1 if active else 0)

def set_circuit_breaker_status(component: str, open_status: bool) -> None:
    """Set circuit breaker status."""
    CIRCUIT_BREAKER_STATUS.labels(component=component).set(1 if open_status else 0)
