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
from .database import db
from .lazy_settings import LazySettings
from .loats_logging import get_logger
from .models import FundsData, Signal, SignalType, Trade, TradeDecision, TransactionType
from .openalgo import AsyncOpenAlgoClient
from .options import calculate_portfolio_var
from .rules import rules_engine
from .sizing import sizing_engine
from .strength import strength_engine
from .trailing_stop import TrailingStopType, trailing_stop_engine
from .utils.lazy_singleton import lazy_singleton

# Lazy proxy module-level binding (TODO-18 / HC-21).
# AST scanner for HC-21 sees a Call to LazySettings(),
# NOT get_settings(), so the eager count remains 0.
settings: Any = LazySettings()  # LazySettings.__getattr__ proxies to Settings()
logger = get_logger(__name__)


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

    def __init__(self, maxsize: int | None = None) -> None:
        """Initialize TradeDecisionEngine.

        Args:
            maxsize: Optional queue maxsize override (for testing).
                     If None, uses settings.decision_queue_maxsize.
                     Bounded queue prevents unbounded memory growth if
                     enqueues outpace the lazy processor (TODO-27c).
        """
        cfg = get_settings()
        queue_maxsize = maxsize if maxsize is not None else cfg.decision_queue_maxsize
        self.decision_queue: asyncio.Queue[TradeDecision] = asyncio.Queue(
            maxsize=queue_maxsize
        )
        self.analyzer_routing_enabled = cfg.analyzer_routing_enabled
        self.decision_timeout = datetime.timedelta(minutes=5)
        self._processor_task: asyncio.Task[None] | None = None

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
        if (
            composite_strength <= settings.composite_strength_threshold
        ):  # Minimum strength threshold
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
        Route TradeDecision to Analyzer with real HTTP call and audit persistence.

        Workflow:
        1. Check if analyzer routing is enabled
        2. If disabled, return disabled status (but still persist to audit)
        3. If enabled, submit payload via AsyncOpenAlgoClient.place_analyzer_request()
        4. Persist decision + routing outcome to audit trail (SQLite + JSONL)
        5. Return real response or propagate errors (no fabrication)

        Args:
            trade_decision: TradeDecision to route to Analyzer

        Returns:
            dict[str, Any]: Routing response from Analyzer or disabled status

        Raises:
            OpenAlgoError: If Analyzer request fails (propagated, not fabricated)
            Exception: Other errors propagated without fabrication

        Note:
            - No asyncio.sleep simulation - real HTTP call
            - Routing failure propagates (no fabricated success)
            - Audit row exists per decision (dual-write: SQLite + JSONL)
        """
        payload = trade_decision.to_analyzer_payload()
        response = await self._do_route_or_disable(trade_decision, payload)
        return await self._persist_routing_outcome(trade_decision, response)

    async def _do_route_or_disable(
        self, trade_decision: TradeDecision, payload: dict[str, Any]
    ) -> dict[str, Any]:
        """Return disabled status or make real Analyzer HTTP call.

        Analyzer routing is intentionally gated by the environment flag
        (default OFF, enable explicitly). When disabled we still return a
        deterministic response so the paper-trail is complete, but we do not
        fabricate a successful Analyzer response.
        """
        if not self.analyzer_routing_enabled:
            response = {
                "status": "disabled",
                "reason": "analyzer_routing_disabled",
                "decision_id": trade_decision.decision_id,
                "timestamp": datetime.datetime.now(datetime.UTC).isoformat(),
            }
            logger.info(
                f"Analyzer routing disabled for decision {trade_decision.decision_id}"
            )
            return response

        # Routing enabled - make real HTTP call to Analyzer (no simulation).
        logger.info(f"Routing TradeDecision to Analyzer: {trade_decision.decision_id}")
        logger.debug(f"Analyzer payload: {payload}")
        try:
            async with AsyncOpenAlgoClient() as client:
                analyzer_response = await client.place_analyzer_request(payload)
            logger.info(
                f"Successfully routed decision {trade_decision.decision_id} to Analyzer"
            )
            return {
                "status": "success",
                "decision_id": trade_decision.decision_id,
                "analyzer_response": analyzer_response,
                "timestamp": datetime.datetime.now(datetime.UTC).isoformat(),
            }
        except Exception as e:
            # Propagate errors, don't fabricate success.
            logger.error(f"Failed to route TradeDecision to Analyzer: {e}")
            response = {
                "status": "error",
                "decision_id": trade_decision.decision_id,
                "error": str(e),
                "error_type": type(e).__name__,
                "timestamp": datetime.datetime.now(datetime.UTC).isoformat(),
            }
            await self._persist_routing_outcome(trade_decision, response)
            raise

    async def _persist_routing_outcome(
        self, trade_decision: TradeDecision, response: dict[str, Any]
    ) -> dict[str, Any]:
        """Persist decision + routing outcome to audit trail (SQLite + JSONL).

        F8-H-01: every routed decision must leave (a) a ``trade_decisions``
        row and (b) a ROUTE audit row whose metadata carries the routing
        outcome (success / disabled / error). The previous implementation
        probed for a nonexistent ``db.async_record_trade_decision`` attribute
        (the registered extension is the private one-arg
        ``_async_record_trade_decision``), so the preferred branch was dead
        code and the routing outcome was never audited.

        Idempotent: the orchestrator pre-persists the decision before
        routing (orchestrator.py ``_execute_cmp_strategy``), so the row is
        only created when missing.

        Best-effort: if the DB write fails the routing response is still
        returned so callers can decide whether to fail the orchestrator
        cycle. Failures are logged loudly for monitoring.
        """
        try:
            existing = await db.async_get_trade_decision(trade_decision.decision_id)
            if existing is None:
                await db.async_create_trade_decision(trade_decision)
                logger.debug(
                    f"Persisted decision {trade_decision.decision_id} to audit trail"
                )
        except Exception as e:
            logger.error(
                f"Failed to persist decision {trade_decision.decision_id} "
                f"to audit trail: {e}"
            )
            # Don't fail the routing if audit persistence fails
            # but log the error for monitoring

        # ROUTE audit row: one per routed decision, carrying the outcome.
        # async_log_audit is the canonical dual-write (SQLite + JSONL) with
        # SHA-256 chaining; a failure here is logged but non-fatal so a
        # transient audit-store error does not cascade into the cycle.
        try:
            await db.async_log_audit(
                action="ROUTE",
                entity_type="trade_decision",
                entity_id=trade_decision.decision_id,
                user="trade_decision_engine",
                metadata={
                    "symbol": trade_decision.symbol,
                    "routing_enabled": self.analyzer_routing_enabled,
                    "routing_outcome": dict(response),
                },
            )
        except Exception as e:
            logger.error(
                f"Failed to write ROUTE audit row for decision "
                f"{trade_decision.decision_id}: {e}"
            )

        return response

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

            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(f"Error processing decision queue: {e}")
                # Backoff to avoid tight spin on persistent errors, but never
                # exceed the decision timeout so the queue does not stall.
                await asyncio.sleep(1.0)

    async def enqueue_decision(self, trade_decision: TradeDecision) -> dict[str, Any]:
        """Add TradeDecision to processing queue with backpressure.

        Uses bounded queue (asyncio.Queue(maxsize=N)) to prevent unbounded
        memory growth when enqueues outpace the lazy processor
        (TODO-27c). If the queue is full, the decision is rejected
        immediately with queue_full status instead of blocking the
        orchestrator cycle indefinitely.

        Returns:
            dict with status queued / rejected(queue_full) / error.
        """
        try:
            # Backpressure: non-blocking put; reject if full
            self.decision_queue.put_nowait(trade_decision)
            return {
                "status": "queued",
                "decision_id": trade_decision.decision_id,
                "queue_size": self.decision_queue.qsize(),
                "queue_maxsize": self.decision_queue.maxsize,
                "timestamp": datetime.datetime.now(datetime.UTC).isoformat(),
            }
        except asyncio.QueueFull:
            logger.warning(
                "Decision queue full — rejecting decision %s (size=%d, maxsize=%d)",
                trade_decision.decision_id,
                self.decision_queue.qsize(),
                self.decision_queue.maxsize,
            )
            return {
                "status": "rejected",
                "reason": "queue_full",
                "decision_id": trade_decision.decision_id,
                "queue_size": self.decision_queue.qsize(),
                "queue_maxsize": self.decision_queue.maxsize,
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

    def get_queue_stats(self) -> dict[str, Any]:
        """Return current queue depth and capacity for monitoring."""
        return {
            "queue_size": self.decision_queue.qsize(),
            "queue_maxsize": self.decision_queue.maxsize,
            "queue_full": self.decision_queue.full(),
            "queue_empty": self.decision_queue.empty(),
        }

    async def start_decision_processor(self) -> None:
        """Start the decision processing task."""
        if self._processor_task is None or self._processor_task.done():
            self._processor_task = asyncio.create_task(self.process_decision_queue())
            logger.info("Started TradeDecision processor")

    async def stop_decision_processor(self) -> None:
        """Stop the decision processing task."""
        if self._processor_task is not None:
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
        """Get status of a TradeDecision from the persisted audit trail.

        F8-H-01: reads the real ``trade_decisions`` row instead of returning
        a fabricated "PROCESSED/ANALYZED" mock (the F7-H-01 fabrication
        class). Unknown ids return ``NOT_FOUND`` — deterministic, auditable,
        no invented state.
        """
        decision = await db.async_get_trade_decision(decision_id)
        if decision is None:
            return {
                "decision_id": decision_id,
                "status": "NOT_FOUND",
                "source": "database",
                "timestamp": datetime.datetime.now(datetime.UTC).isoformat(),
            }
        return {
            "decision_id": decision.decision_id,
            "status": decision.status,
            "symbol": decision.symbol,
            "decision_type": str(decision.decision_type),
            "entry_price": decision.entry_price,
            "quantity": decision.quantity,
            "composite_strength": decision.composite_strength,
            "source": "database",
            "timestamp": datetime.datetime.now(datetime.UTC).isoformat(),
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
# F8-C-03 (2026-09-02): __init__ reads Settings() (decision_queue_maxsize,
# analyzer_routing_enabled); defer construction so imports stay
# credential-free. Test patches keep working via proxy __dict__.
trade_decision_engine: TradeDecisionEngine = lazy_singleton(TradeDecisionEngine)

__all__ = ["TradeDecisionEngine", "DecisionStatus", "trade_decision_engine"]
