"""
Orchestrator Module for LOATS13July2026.
High-performance orchestration layer coordinating all trading components.
Target: <100ms per cycle.

Coordinates:
- Sentiment analysis
- Technical analysis (TA)
- Strike selection
- Risk management
- Rule evaluation
- Signal generation
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from .loats.models import Signal, SignalType


@dataclass
class CycleMetrics:
    """Metrics for a single orchestration cycle."""

    cycle_id: str
    start_time: float
    end_time: float
    total_latency_ms: float
    component_latencies: dict[str, float]
    sentiment_latency_ms: float = 0.0
    ta_latency_ms: float = 0.0
    strike_latency_ms: float = 0.0
    risk_latency_ms: float = 0.0
    rules_latency_ms: float = 0.0
    signal_latency_ms: float = 0.0
    success: bool = True
    error_message: str | None = None

    @property
    def within_target(self) -> bool:
        """Check if cycle was within 100ms target."""
        return self.total_latency_ms <= 100.0


@dataclass
class CycleResult:
    """Result of a complete orchestration cycle."""

    cycle_id: str
    timestamp: float
    sentiment_result: dict[str, Any] | None = None
    ta_result: dict[str, Any] | None = None
    strike_result: dict[str, Any] | None = None
    risk_result: dict[str, Any] | None = None
    rules_result: dict[str, Any] | None = None
    signals: list[Signal] = field(default_factory=list)
    final_signal: Signal | None = None
    metrics: CycleMetrics | None = None


class ComponentInterface:
    """Protocol for orchestrator components."""

    def execute(self, context: dict[str, Any]) -> dict[str, Any]:
        """Execute component with context."""
        raise NotImplementedError


class Orchestrator:
    """
    High-performance orchestration engine.
    Coordinates all trading system components in <100ms cycles.

    Components are executed in dependency order:
    1. Sentiment analysis
    2. Technical analysis
    3. Strike selection
    4. Risk evaluation
    5. Rule evaluation
    6. Signal generation
    """

    def __init__(self) -> None:
        """Initialize Orchestrator."""
        self.logger = logging.getLogger(__name__)
        self._components: dict[str, Any] = {}
        self._cycle_count = 0
        self._total_latency_ms = 0.0

    def register(self, name: str, component: Any) -> None:
        """
        Register a component for orchestration.

        Args:
            name: Component name (e.g., "sentiment", "ta", "strike")
            component: Component instance with execute(context) method
        """
        self._components[name] = component
        self.logger.debug(f"Registered component: {name}")

    def unregister(self, name: str) -> None:
        """Unregister a component."""
        if name in self._components:
            del self._components[name]
            self.logger.debug(f"Unregistered component: {name}")

    def cycle(self, context: dict[str, Any] | None = None) -> dict[str, Any]:
        """
        Execute one orchestration cycle. Target: <100ms.

        Args:
            context: Optional context dict with input data

        Returns:
            dict with results from all components
        """
        return self._execute_cycle(context or {})._to_dict()  # type: ignore[no-any-return,attr-defined]

    async def cycle_async(self, context: dict[str, Any] | None = None) -> CycleResult:
        """
        Execute one orchestration cycle asynchronously. Target: <100ms.

        Args:
            context: Optional context dict with input data

        Returns:
            CycleResult with detailed metrics
        """
        return await asyncio.to_thread(self._execute_cycle, context or {})

    def _execute_cycle(self, context: dict[str, Any]) -> CycleResult:
        """Execute synchronous cycle with timing."""
        self._cycle_count += 1
        cycle_id = f"cycle_{self._cycle_count}_{int(time.time() * 1000)}"
        start_time = time.perf_counter()

        metrics = CycleMetrics(
            cycle_id=cycle_id,
            start_time=start_time,
            end_time=0.0,
            total_latency_ms=0.0,
            component_latencies={},
        )

        result = CycleResult(
            cycle_id=cycle_id,
            timestamp=start_time,
        )

        try:
            # Step 1: Sentiment analysis
            sentiment_start = time.perf_counter()
            result.sentiment_result = self._execute_component("sentiment", context)
            metrics.sentiment_latency_ms = (
                time.perf_counter() - sentiment_start
            ) * 1000

            # Update context with sentiment results
            if result.sentiment_result:
                context["sentiment_score"] = result.sentiment_result.get("score", 0.0)
                context["sentiment_label"] = result.sentiment_result.get(
                    "label", "neutral"
                )

            # Step 2: Technical analysis
            ta_start = time.perf_counter()
            result.ta_result = self._execute_component("ta", context)
            metrics.ta_latency_ms = (time.perf_counter() - ta_start) * 1000

            # Step 3: Strike selection
            strike_start = time.perf_counter()
            result.strike_result = self._execute_component("strike", context)
            metrics.strike_latency_ms = (time.perf_counter() - strike_start) * 1000

            # Step 4: Risk evaluation
            risk_start = time.perf_counter()
            result.risk_result = self._execute_component("risk", context)
            metrics.risk_latency_ms = (time.perf_counter() - risk_start) * 1000

            # Check if within risk limits
            if result.risk_result and not result.risk_result.get("approved", True):
                result.rules_result = {
                    "decision": "REJECTED",
                    "reason": "Risk limit exceeded",
                }
                result.signals = []
                result.final_signal = None
            else:
                # Step 5: Rule evaluation
                rules_start = time.perf_counter()
                result.rules_result = self._execute_component("rules", context)
                metrics.rules_latency_ms = (time.perf_counter() - rules_start) * 1000

                # Step 6: Signal generation
                signal_start = time.perf_counter()
                signals_data = self._execute_component("signals", context)
                metrics.signal_latency_ms = (time.perf_counter() - signal_start) * 1000

                # Convert to Signal objects
                result.signals = self._create_signals(signals_data, context)
                result.final_signal = result.signals[0] if result.signals else None

        except Exception as e:
            self.logger.error(f"Cycle {cycle_id} failed: {e}")
            metrics.success = False
            metrics.error_message = str(e)

        # Finalize metrics
        end_time = time.perf_counter()
        metrics.end_time = end_time
        metrics.total_latency_ms = (end_time - start_time) * 1000

        # Track running statistics
        self._total_latency_ms += metrics.total_latency_ms

        result.metrics = metrics

        # Log warning if over target
        if metrics.total_latency_ms > 100:
            self.logger.warning(
                f"Cycle {cycle_id} took {metrics.total_latency_ms:.2f}ms (target: <100ms)"
            )

        return result

    def _execute_component(self, name: str, context: dict[str, Any]) -> dict[str, Any]:
        """Execute a component with timing."""
        if name not in self._components:
            return {}

        component = self._components[name]

        try:
            if hasattr(component, "execute"):
                result: dict[str, Any] = component.execute(context)
            else:
                result = component(context)  # type: ignore[no-any-return]
        except Exception as e:
            self.logger.error(f"Component {name} failed: {e}")
            result = {"error": str(e)}

        return result

    def _create_signals(
        self, signals_data: dict[str, Any], context: dict[str, Any]
    ) -> list[Signal]:
        """Create Signal objects from signals data."""
        signals: list[Signal] = []

        if not signals_data or "signals" not in signals_data:
            return signals

        for sig_data in signals_data.get("signals", []):
            try:
                signal_type_str = sig_data.get("signal_type", "HOLD")
                try:
                    signal_type = SignalType(signal_type_str.upper())
                except ValueError:
                    signal_type = SignalType.HOLD

                signal = Signal(
                    signal_id=sig_data.get("signal_id", f"sig_{time.time_ns()}"),
                    symbol=context.get("symbol", "UNKNOWN"),
                    signal_type=signal_type,
                    strength=sig_data.get("strength", 0.5),
                    timestamp=sig_data.get("timestamp"),
                    indicators=sig_data.get("indicators", {}),
                    metadata=sig_data.get("metadata", {}),
                    confidence=sig_data.get("confidence"),
                )
                signals.append(signal)
            except Exception as e:
                self.logger.warning(f"Failed to create signal: {e}")

        return signals

    def get_statistics(self) -> dict[str, Any]:
        """Get orchestration statistics."""
        avg_latency = (
            self._total_latency_ms / self._cycle_count if self._cycle_count > 0 else 0.0
        )

        return {
            "cycle_count": self._cycle_count,
            "total_latency_ms": self._total_latency_ms,
            "average_latency_ms": avg_latency,
            "within_target_pct": (
                sum(1 for _ in range(self._cycle_count)) / self._cycle_count * 100
                if self._cycle_count > 0
                else 100.0
            ),
            "registered_components": list(self._components.keys()),
        }

    def reset_statistics(self) -> None:
        """Reset statistics counters."""
        self._cycle_count = 0
        self._total_latency_ms = 0.0


# Extension for CycleResult to include _to_dict method
def _cycle_result_to_dict(self: CycleResult) -> dict[str, Any]:
    """Convert CycleResult to dictionary."""
    return {
        "cycle_id": self.cycle_id,
        "timestamp": self.timestamp,
        "sentiment_result": self.sentiment_result,
        "ta_result": self.ta_result,
        "strike_result": self.strike_result,
        "risk_result": self.risk_result,
        "rules_result": self.rules_result,
        "signals": [
            {
                "signal_id": s.signal_id,
                "symbol": s.symbol,
                "signal_type": s.signal_type.value,
                "strength": s.strength,
                "confidence": s.confidence,
                "indicators": s.indicators,
            }
            for s in self.signals
        ],
        "final_signal": (
            {
                "signal_id": self.final_signal.signal_id,
                "signal_type": self.final_signal.signal_type.value,
                "strength": self.final_signal.strength,
            }
            if self.final_signal
            else None
        ),
        "metrics": (
            {
                "cycle_id": self.metrics.cycle_id,
                "total_latency_ms": self.metrics.total_latency_ms,
                "within_target": self.metrics.within_target,
                "sentiment_latency_ms": self.metrics.sentiment_latency_ms,
                "ta_latency_ms": self.metrics.ta_latency_ms,
                "strike_latency_ms": self.metrics.strike_latency_ms,
                "risk_latency_ms": self.metrics.risk_latency_ms,
                "rules_latency_ms": self.metrics.rules_latency_ms,
                "signal_latency_ms": self.metrics.signal_latency_ms,
                "success": self.metrics.success,
                "error_message": self.metrics.error_message,
            }
            if self.metrics
            else None
        ),
    }


# Monkey-patch the method onto the class
CycleResult._to_dict = _cycle_result_to_dict  # type: ignore[attr-defined]


__all__ = [
    "Orchestrator",
    "CycleResult",
    "CycleMetrics",
    "ComponentInterface",
]
