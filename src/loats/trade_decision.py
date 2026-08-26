"""
CMP Trade Decision Engine for LOATS13July2026.

Implements TradeDecision creation and routing to Analyzer:
- Converts signals to TradeDecisions
- Applies gating rules and strength calculation
- Routes decisions to Analyzer
- Manages decision lifecycle
"""

import asyncio
import datetime
from enum import StrEnum
from typing import Any

from .config import get_settings
from .loats_logging import get_logger
from .models import FundsData, Signal, SignalType, Trade, TradeDecision, TransactionType
from .options import calculate_portfolio_var
from .rules import rules_engine
from .sizing import sizing_engine
from .strength import strength_engine
from .trailing_stop import TrailingStopType, trailing_stop_engine

logger = get_logger(__name__)
settings = get_settings()


class DecisionStatus(StrEnum):
    """Trade decision status enumeration."""

    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXECUTED = "EXECUTED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"


class TradeDecisionEngine:
    """CMP Trade Decision Engine with Analyzer routing."""

    def __init__(self) -> None:
        """Initialize TradeDecisionEngine."""
        self.decision_queue = asyncio.Queue()
        self.analyzer_routing_enabled = True
        self.decision_timeout = datetime.timedelta(minutes=5)

    async def create_trade_decision(
        self,
        signals: list[Signal],
        historical_data: list[Any],
        current_price: float,
        funds: FundsData,
        current_positions: list[Trade],
    ) -> tuple[TradeDecision | None, dict[str, Any]]:
        """
        Create TradeDecision from signals using full CMP workflow.

        Workflow:
        1. Validate signals (≥3 sources)
        2. Calculate composite strength with opposition gate
        3. Apply gating rules (IV-rank/ADX/VIX)
        4. Calculate position size (2% fixed-fraction)
        5. Set up trailing stop
        6. Calculate VaR
        7. Create TradeDecision
        """
        symbol = signals[0].symbol if signals else settings.default_symbol
        timestamp = datetime.datetime.now(datetime.UTC)

        # Step 1: Validate signals
        validation_result = strength_engine.validate_signal_sources(signals)
        if not validation_result[0]:
            return None, {
                "status": "rejected",
                "reason": "signal_validation_failed",
                "details": validation_result[1],
                "symbol": symbol,
                "timestamp": timestamp,
            }

        # Step 2: Calculate composite strength
        composite_strength, strength_details = (
            strength_engine.calculate_composite_strength(signals)
        )
        if composite_strength <= 0.5:  # Minimum strength threshold
            return None, {
                "status": "rejected",
                "reason": "insufficient_strength",
                "composite_strength": composite_strength,
                "strength_details": strength_details,
                "symbol": symbol,
                "timestamp": timestamp,
            }

        # Determine decision type from strongest signal
        strongest_signal = max(signals, key=lambda s: s.strength)
        decision_type = strongest_signal.signal_type

        # Step 3: Apply gating rules
        gating_passed, gating_result = rules_engine.apply_gating_rules(
            strongest_signal, historical_data, current_price
        )

        if not gating_passed:
            return None, {
                "status": "rejected",
                "reason": "gating_rules_failed",
                "gating_result": gating_result,
                "symbol": symbol,
                "timestamp": timestamp,
            }

        # Step 4: Check position limits (CMP Rule 11)
        position_check, position_result = rules_engine.check_position_limits(
            symbol, current_positions
        )
        if not position_check:
            return None, {
                "status": "rejected",
                "reason": "position_limit_exceeded",
                "position_result": position_result,
                "symbol": symbol,
                "timestamp": timestamp,
            }

        # Step 5: Calculate position size (2% fixed-fraction)
        stop_loss = self._calculate_stop_loss(current_price, decision_type)
        position_size, sizing_details = sizing_engine.calculate_fixed_fraction_size(
            funds, current_price, stop_loss, symbol
        )

        if position_size <= 0:
            return None, {
                "status": "rejected",
                "reason": "invalid_position_size",
                "sizing_details": sizing_details,
                "symbol": symbol,
                "timestamp": timestamp,
            }

        # Step 6: Set up trailing stop
        trailing_config = trailing_stop_engine.initialize_trailing_stop(
            Trade(
                trade_id="temp_for_config",
                symbol=symbol,
                quantity=position_size,
                entry_price=current_price,
                entry_time=datetime.datetime.now(datetime.UTC),
                transaction_type=(
                    TransactionType.BUY
                    if decision_type == SignalType.BUY
                    else TransactionType.SELL
                ),
            ),
            current_price,
            TrailingStopType.PERCENTAGE,
            {"percentage": 0.01},  # 1% trailing stop
        )

        # Step 7: Calculate VaR
        var_analysis = calculate_portfolio_var(
            [trade for trade in current_positions if trade.symbol == symbol],
            confidence_level=0.95,
        )

        # Create TradeDecision
        trade_decision = TradeDecision(
            symbol=symbol,
            decision_type=decision_type,
            composite_strength=composite_strength,
            timestamp=timestamp,
            entry_price=current_price,
            quantity=position_size,
            stop_loss=stop_loss,
            take_profit=self._calculate_take_profit(
                current_price, decision_type, position_size
            ),
            trailing_stop_config=trailing_config,
            position_size_method="fixed_fraction",
            risk_percentage=0.02,  # 2% risk
            var_analysis={
                "var_value": var_analysis.var_value,
                "var_percent": var_analysis.var_percent,
                "method": var_analysis.method,
            },
            gating_rules_result=gating_result,
            source_breakdown=strength_engine.get_source_strength_breakdown(signals),
            metadata={
                "sizing_details": sizing_details,
                "strength_details": strength_details,
                "validation_result": validation_result[1],
                "session": str(rules_engine.session_state),
            },
            status="PENDING",
        )

        return trade_decision, {
            "status": "created",
            "symbol": symbol,
            "decision_type": str(decision_type),
            "composite_strength": composite_strength,
            "position_size": position_size,
            "timestamp": timestamp,
        }

    def _calculate_stop_loss(
        self, current_price: float, decision_type: SignalType
    ) -> float:
        """Calculate stop loss based on decision type."""
        if decision_type == SignalType.BUY:
            # For BUY decisions: stop loss below current price
            return current_price * 0.99  # 1% below
        else:
            # For SELL decisions: stop loss above current price
            return current_price * 1.01  # 1% above

    def _calculate_take_profit(
        self, current_price: float, decision_type: SignalType, position_size: int
    ) -> float | None:
        """Calculate take profit based on decision type."""
        if decision_type == SignalType.BUY:
            # For BUY decisions: take profit above current price
            return current_price * 1.02  # 2% above
        else:
            # For SELL decisions: take profit below current price
            return current_price * 0.98  # 2% below

    async def route_to_analyzer(self, trade_decision: TradeDecision) -> dict[str, Any]:
        """
        Route TradeDecision to Analyzer.

        In production, this would send to actual Analyzer service.
        For now, we simulate the routing and return success.
        """
        if not self.analyzer_routing_enabled:
            return {
                "status": "disabled",
                "reason": "analyzer_routing_disabled",
                "decision_id": trade_decision.decision_id,
            }

        try:
            # Simulate Analyzer API call
            payload = trade_decision.to_analyzer_payload()

            # In production: await analyzer_client.send_decision(payload)
            # For simulation, we'll just log and return success

            logger.info(
                f"Routing TradeDecision to Analyzer: {trade_decision.decision_id}"
            )
            logger.debug(f"Analyzer payload: {payload}")

            # Simulate processing delay
            await asyncio.sleep(0.1)

            return {
                "status": "success",
                "decision_id": trade_decision.decision_id,
                "analyzer_response": {
                    "received": True,
                    "decision_id": trade_decision.decision_id,
                    "symbol": trade_decision.symbol,
                    "status": "QUEUED_FOR_ANALYSIS",
                    "timestamp": datetime.datetime.now(datetime.UTC).isoformat(),
                },
            }

        except Exception as e:
            logger.error(f"Failed to route TradeDecision to Analyzer: {e}")
            return {
                "status": "error",
                "decision_id": trade_decision.decision_id,
                "error": str(e),
                "timestamp": datetime.datetime.now(datetime.UTC).isoformat(),
            }

    async def process_decision_queue(self) -> None:
        """Process decisions from the queue and route to Analyzer."""
        while True:
            try:
                decision = await self.decision_queue.get()
                routing_result = await self.route_to_analyzer(decision)

                if routing_result["status"] == "success":
                    logger.info(
                        f"Successfully routed decision {decision.decision_id} "
                        f"to Analyzer"
                    )
                else:
                    logger.warning(
                        f"Failed to route decision {decision.decision_id}: "
                        f"{routing_result}"
                    )

                self.decision_queue.task_done()

            except Exception as e:
                logger.error(f"Error processing decision queue: {e}")
                await asyncio.sleep(1.0)

    async def enqueue_decision(self, trade_decision: TradeDecision) -> dict[str, Any]:
        """Add TradeDecision to processing queue."""
        try:
            await self.decision_queue.put(trade_decision)
            return {
                "status": "queued",
                "decision_id": trade_decision.decision_id,
                "queue_size": self.decision_queue.qsize(),
                "timestamp": datetime.datetime.now(datetime.UTC).isoformat(),
            }
        except Exception as e:
            logger.error(f"Failed to enqueue decision: {e}")
            return {
                "status": "error",
                "decision_id": trade_decision.decision_id,
                "error": str(e),
                "timestamp": datetime.datetime.now(datetime.UTC).isoformat(),
            }

    async def start_decision_processor(self) -> None:
        """Start the decision processing task."""
        if (
            not hasattr(self, "_processor_task")
            or self._processor_task is None
            or self._processor_task.done()
        ):
            self._processor_task = asyncio.create_task(self.process_decision_queue())
            logger.info("Started TradeDecision processor")

    async def stop_decision_processor(self) -> None:
        """Stop the decision processing task."""
        if hasattr(self, "_processor_task") and self._processor_task:
            self._processor_task.cancel()
            try:
                await self._processor_task
            except asyncio.CancelledError:
                pass
            logger.info("Stopped TradeDecision processor")

    def enable_analyzer_routing(self) -> None:
        """Enable Analyzer routing."""
        self.analyzer_routing_enabled = True
        logger.info("Enabled Analyzer routing")

    def disable_analyzer_routing(self) -> None:
        """Disable Analyzer routing."""
        self.analyzer_routing_enabled = False
        logger.info("Disabled Analyzer routing")

    async def create_and_route_decision(
        self,
        signals: list[Signal],
        historical_data: list[Any],
        current_price: float,
        funds: FundsData,
        current_positions: list[Trade],
    ) -> dict[str, Any]:
        """
        Complete workflow: create decision and route to Analyzer.

        Combines create_trade_decision and route_to_analyzer in one call.
        """
        # Create trade decision
        decision, creation_result = await self.create_trade_decision(
            signals, historical_data, current_price, funds, current_positions
        )

        if decision is None:
            return {
                **creation_result,
                "routing_status": "skipped",
                "reason": "decision_not_created",
            }

        # Route to Analyzer
        routing_result = await self.route_to_analyzer(decision)

        return {
            "creation_result": creation_result,
            "routing_result": routing_result,
            "decision_id": decision.decision_id,
            "symbol": decision.symbol,
            "status": "completed",
            "timestamp": datetime.datetime.now(datetime.UTC).isoformat(),
        }

    async def get_decision_status(self, decision_id: str) -> dict[str, Any]:
        """Get status of a TradeDecision."""
        # In production, this would query the Analyzer or database
        # For simulation, we return a mock status

        return {
            "decision_id": decision_id,
            "status": "PROCESSED",
            "analyzer_status": "ANALYZED",
            "timestamp": datetime.datetime.now(datetime.UTC).isoformat(),
            "notes": ("Simulated response - production would query actual Analyzer"),
        }

    def increment_modification_counter(self) -> int:
        """Increment rule 7 modification counter."""
        return rules_engine.increment_modification_counter()

    def get_modification_count(self) -> int:
        """Get current modification counter value."""
        return rules_engine.get_modification_count()

    def reset_modification_counter(self) -> None:
        """Reset rule 7 modification counter."""
        rules_engine.reset_modification_counter()


# Module-level singleton instance
trade_decision_engine = TradeDecisionEngine()

__all__ = ["TradeDecisionEngine", "DecisionStatus", "trade_decision_engine"]
