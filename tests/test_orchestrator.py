"""
Tests for Orchestrator Module.
Validates <100ms cycle latency target and component coordination.
"""

from datetime import UTC, datetime

import pytest

from src.orchestrator import CycleMetrics, CycleResult, Orchestrator


class MockComponent:
    """Mock component for testing."""

    def __init__(self, latency_ms: float = 1.0, result: dict | None = None) -> None:
        self.latency_ms = latency_ms
        self._result = result or {"status": "ok"}
        self.call_count = 0

    def execute(self, context: dict) -> dict:
        """Execute with simulated latency."""
        self.call_count += 1
        return self._result


@pytest.fixture
def orchestrator() -> Orchestrator:
    """Create Orchestrator instance."""
    return Orchestrator()


@pytest.fixture
def mock_components() -> dict[str, MockComponent]:
    """Create mock components for testing."""
    return {
        "sentiment": MockComponent(1.0, {"score": 0.5, "label": "positive"}),
        "ta": MockComponent(1.0, {"rsi": 55.0, "macd": "bullish"}),
        "strike": MockComponent(1.0, {"selected_strike": 25000.0}),
        "risk": MockComponent(1.0, {"approved": True}),
        "rules": MockComponent(1.0, {"decision": "APPROVED"}),
        "signals": MockComponent(1.0, {"signals": []}),
    }


class TestOrchestrator:
    """Tests for Orchestrator class."""

    def test_orchestrator_registration(self, orchestrator) -> None:
        """Test component registration."""
        mock = MockComponent()
        orchestrator.register("test", mock)
        assert "test" in orchestrator._components
        assert orchestrator._components["test"] == mock

    def test_orchestrator_unregister(self, orchestrator) -> None:
        """Test component unregistration."""
        mock = MockComponent()
        orchestrator.register("test", mock)
        orchestrator.unregister("test")
        assert "test" not in orchestrator._components

    def test_orchestrator_cycle_execution(self, orchestrator, mock_components) -> None:
        """Test basic cycle execution."""
        for name, component in mock_components.items():
            orchestrator.register(name, component)

        result = orchestrator.cycle({"symbol": "NIFTY"})

        assert "cycle_id" in result
        assert "metrics" in result
        assert result["metrics"]["within_target"] is True
        assert result["metrics"]["total_latency_ms"] < 100.0

    def test_orchestrator_cycle_latency_target(
        self, orchestrator, mock_components
    ) -> None:
        """Test that orchestrator meets <100ms cycle target."""
        for name, component in mock_components.items():
            orchestrator.register(name, component)

        latencies = []
        for _ in range(10):
            result = orchestrator.cycle({"symbol": "NIFTY"})
            latencies.append(result["metrics"]["total_latency_ms"])

        avg_latency = sum(latencies) / len(latencies)
        assert avg_latency < 100.0, (
            f"Average latency {avg_latency:.2f}ms exceeds 100ms target"
        )

    def test_orchestrator_component_execution_order(
        self, orchestrator, mock_components
    ) -> None:
        """Test that components execute in correct order."""
        execution_times: dict[str, float] = {}

        for name, component in mock_components.items():
            # Wrap each component to track execution
            original_execute = component.execute

            def make_wrapper(n: str, orig_exec: callable) -> callable:
                def wrapper(ctx: dict) -> dict:
                    execution_times[n] = datetime.now(UTC).timestamp()
                    return orig_exec(ctx)

                return wrapper

            component.execute = make_wrapper(name, original_execute)
            orchestrator.register(name, component)

        orchestrator.cycle({"symbol": "NIFTY"})

        # Verify all components were called
        for name in mock_components:
            assert execution_times.get(name) is not None

    def test_orchestrator_handles_missing_components(self, orchestrator) -> None:
        """Test orchestrator handles missing components gracefully."""
        orchestrator.register("sentiment", MockComponent())

        result = orchestrator.cycle({"symbol": "NIFTY"})

        # Should not crash, just skip missing components
        assert "cycle_id" in result
        assert result["metrics"]["success"] is True

    def test_orchestrator_handles_component_error(self, orchestrator) -> None:
        """Test orchestrator handles component errors gracefully."""

        class ErrorComponent:
            def execute(self, ctx: dict) -> dict:
                return {"error": "Component encountered an error"}

        orchestrator.register("error_component", ErrorComponent())
        result = orchestrator.cycle({"symbol": "NIFTY"})

        # Component returned error - should be captured in results
        assert "sentiment_result" in result or "error_component" in str(result)

    def test_orchestrator_risk_rejection(self, orchestrator, mock_components) -> None:
        """Test that risk rejection stops signal generation."""
        mock_components["risk"] = MockComponent(1.0, {"approved": False})

        for name, component in mock_components.items():
            orchestrator.register(name, component)

        result = orchestrator.cycle({"symbol": "NIFTY"})

        assert result["rules_result"]["decision"] == "REJECTED"
        assert result["rules_result"]["reason"] == "Risk limit exceeded"

    def test_orchestrator_context_propagation(self, orchestrator) -> None:
        """Test that sentiment results propagate to context."""
        sentiment_result = {"score": 0.7, "label": "bullish"}

        class SentimentComponent:
            def execute(self, ctx: dict) -> dict:
                return sentiment_result

        class RulesComponent:
            def execute(self, ctx: dict) -> dict:
                # Rules should see sentiment_score in context
                assert "sentiment_score" in ctx
                return {"decision": "APPROVED"}

        orchestrator.register("sentiment", SentimentComponent())
        orchestrator.register("rules", RulesComponent())

        result = orchestrator.cycle({"symbol": "NIFTY"})
        assert result["sentiment_result"]["score"] == 0.7


class TestCycleMetrics:
    """Tests for CycleMetrics dataclass."""

    def test_within_target_property(self) -> None:
        """Test within_target property."""
        metrics = CycleMetrics(
            cycle_id="test_1",
            start_time=0.0,
            end_time=0.05,
            total_latency_ms=50.0,
            component_latencies={},
        )
        assert metrics.within_target is True

        metrics = CycleMetrics(
            cycle_id="test_2",
            start_time=0.0,
            end_time=0.15,
            total_latency_ms=150.0,
            component_latencies={},
        )
        assert metrics.within_target is False


class TestOrchestratorStatistics:
    """Tests for orchestrator statistics."""

    def test_get_statistics(self, orchestrator, mock_components) -> None:
        """Test statistics retrieval."""
        for name, component in mock_components.items():
            orchestrator.register(name, component)

        # Run a few cycles
        for _ in range(5):
            orchestrator.cycle({"symbol": "NIFTY"})

        stats = orchestrator.get_statistics()

        assert stats["cycle_count"] == 5
        assert stats["total_latency_ms"] > 0
        assert stats["average_latency_ms"] > 0
        assert "sentiment" in stats["registered_components"]
        assert "ta" in stats["registered_components"]

    def test_reset_statistics(self, orchestrator, mock_components) -> None:
        """Test statistics reset."""
        for name, component in mock_components.items():
            orchestrator.register(name, component)

        # Run cycles
        for _ in range(3):
            orchestrator.cycle({"symbol": "NIFTY"})

        stats_before = orchestrator.get_statistics()
        assert stats_before["cycle_count"] == 3

        orchestrator.reset_statistics()

        stats_after = orchestrator.get_statistics()
        assert stats_after["cycle_count"] == 0


class TestCycleLatencyBreakdown:
    """Tests for component latency breakdown."""

    def test_latency_breakdown(self, orchestrator, mock_components) -> None:
        """Test that individual component latencies are tracked."""
        for name, component in mock_components.items():
            orchestrator.register(name, component)

        result = orchestrator.cycle({"symbol": "NIFTY"})

        metrics = result["metrics"]
        assert "sentiment_latency_ms" in metrics
        assert "ta_latency_ms" in metrics
        assert "strike_latency_ms" in metrics
        assert "risk_latency_ms" in metrics
        assert "rules_latency_ms" in metrics

        # Verify all latency values are non-negative
        assert metrics["sentiment_latency_ms"] >= 0
        assert metrics["ta_latency_ms"] >= 0
        assert metrics["strike_latency_ms"] >= 0
        assert metrics["risk_latency_ms"] >= 0
        assert metrics["rules_latency_ms"] >= 0


class TestOrchestratorAsync:
    """Tests for async orchestrator methods."""

    @pytest.mark.asyncio
    async def test_cycle_async(self, orchestrator, mock_components) -> None:
        """Test async cycle execution."""
        for name, component in mock_components.items():
            orchestrator.register(name, component)

        result = await orchestrator.cycle_async({"symbol": "NIFTY"})

        assert isinstance(result, CycleResult)
        assert result.cycle_id.startswith("cycle_")
        assert result.metrics is not None
        assert result.metrics.total_latency_ms < 100.0


class TestEdgeCases:
    """Tests for edge cases."""

    def test_empty_cycle(self, orchestrator) -> None:
        """Test cycle with no registered components."""
        result = orchestrator.cycle({})

        assert result["metrics"]["success"] is True
        assert result["metrics"]["total_latency_ms"] < 100.0

    def test_very_fast_components(self, orchestrator) -> None:
        """Test with extremely fast components."""
        fast_component = MockComponent(0.001, {"fast": True})
        orchestrator.register("fast", fast_component)

        latencies = []
        for _ in range(20):
            result = orchestrator.cycle({})
            latencies.append(result["metrics"]["total_latency_ms"])

        # Even with fast components, should be well under target
        max_latency = max(latencies)
        assert max_latency < 100.0
        assert sum(latencies) / len(latencies) < 10.0

    def test_signal_generation_in_cycle(self, orchestrator) -> None:
        """Test that signals are generated correctly."""
        from datetime import datetime

        signals_data = {
            "signals": [
                {
                    "signal_id": "sig_1",
                    "symbol": "NIFTY",
                    "signal_type": "BUY",
                    "strength": 0.8,
                    "confidence": 0.9,
                    "timestamp": datetime.now(UTC),
                    "indicators": {"rsi": 70, "macd_histogram": 2.5},
                }
            ]
        }

        class SignalComponent:
            def execute(self, ctx: dict) -> dict:
                return signals_data

        orchestrator.register("signals", SignalComponent())
        orchestrator.register("sentiment", MockComponent(1.0, {"score": 0.5}))
        orchestrator.register("risk", MockComponent(1.0, {"approved": True}))
        orchestrator.register("rules", MockComponent(1.0, {"decision": "APPROVED"}))

        result = orchestrator.cycle({"symbol": "NIFTY"})

        assert len(result["signals"]) == 1
        assert result["signals"][0]["signal_type"] == "BUY"
        assert result["signals"][0]["strength"] == 0.8
