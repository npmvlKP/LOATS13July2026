#!/usr/bin/env python3
"""
Comprehensive test suite for database async operations.

Tests both the public async wrappers on ``Database`` and the aiosqlite-backed
private helpers in ``database_async_additions``.  Tests are written against the
*actual* Database API rather than an idealised one.
"""

import asyncio
import inspect
import json
import tempfile
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

import pytest

from loats.database import Database
from loats.database_async_additions import AIOSQLITE_AVAILABLE, extend_database_class
from loats.models import (
    FundsData,
    HistoricalData,
    Order,
    Position,
    ProductType,
    QuoteData,
    Signal,
    SignalType,
    Trade,
    TradeDecision,
    TransactionType,
)

# ---------------------------------------------------------------------------
# TradeDecision persistence coverage (R7 margin round, 2026-09-12).
#
# The whole trade-decision layer (sync CRUD in database.py:1947-2179 and the
# aiosqlite-backed _async_record_trade_decision in
# database_async_additions.py:342-401) carried zero test references before
# this block: the 58-line optimized async implementation was uncovered, and
# the dispatch pins below were born RED — ``async_create_trade_decision``
# dispatched to ``_async_create_trade_decision``, a name the extension never
# registered, so the preferred aiosqlite branch died on AttributeError and
# silently fell back whenever the pool was attached.
#
# Determinism: seeded ids/UTC datetimes (no wall-clock dependence), Decimal
# strings for money fields, timezone-aware IST-offset timestamps, and the
# F8-L-02 ``as_of_date`` snapshot pinned so round-trips are assertable.
# ---------------------------------------------------------------------------

_SEED_EPOCH = datetime(2026, 9, 12, 9, 15, 0, tzinfo=UTC)
_LOATS_SEED = 785641230


def _make_decision(
    decision_id: str = "decision_20260912091500000000_feedface",
    *,
    symbol: str = "TCS",
    decision_type: SignalType = SignalType.BUY,
    as_of_date: date | None = date(2026, 9, 11),
) -> TradeDecision:
    """Deterministic TradeDecision factory (seeded id, pinned snapshot date)."""
    return TradeDecision(
        decision_id=decision_id,
        symbol=symbol,
        decision_type=decision_type,
        composite_strength=float(Decimal("0.73")),
        timestamp=_SEED_EPOCH,
        as_of_date=as_of_date,
        entry_price=float(Decimal("4100.50")),
        quantity=25,
        stop_loss=float(Decimal("4050.00")),
        take_profit=float(Decimal("4210.00")),
        trailing_stop_config={"mode": "atr", "atr_multiplier": 2.5},
        position_size_method="fixed_fraction",
        risk_percentage=float(Decimal("0.01")),
        var_analysis={"var_95": float(Decimal("1234.56")), "horizon_days": 1},
        gating_rules_result={"passed": True, "rules_evaluated": 7},
        source_breakdown={"ta": 0.6, "sentiment": 0.4},
        metadata={"session": "EQ", "seed": _LOATS_SEED},
        status="PENDING",
    )


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp_dir:
        db_path = Path(temp_dir) / "test.db"
        audit_log_path = Path(temp_dir) / "test_audit.jsonl"

        db = Database(db_path=db_path, audit_log_path=audit_log_path)
        db._initialize_database()
        extend_database_class()

        yield db

        if hasattr(db, "_async_pool") and db._async_pool is not None:
            try:
                loop = asyncio.new_event_loop()
                try:
                    loop.run_until_complete(db.async_close_all())
                except Exception:
                    pass
                finally:
                    loop.close()
            except Exception:
                pass
            db._async_pool = None
        db.close_all()


class TestDatabaseAsyncAdditions:
    """Test suite for async database operations."""

    def test_extend_database_class(self):
        """Test that the Database class is properly extended with async methods."""
        extend_database_class()

        # Public wrappers defined on Database itself
        for method_name in [
            "async_initialize",
            "async_create_signal",
            "async_store_historical_data",
            "async_store_quote",
            "async_store_position",
            "async_store_funds",
            "async_get_latest_signals",
            "async_update_trade",
            "async_update_order_status",
            "async_get_trade",
            "async_log_audit",
            "async_get_historical_data",
        ]:
            assert hasattr(Database, method_name), (
                f"Database should have {method_name} method"
            )

        # Private aiosqlite-backed helpers added by database_async_additions
        for method_name in [
            "_async_create_signal",
            "_async_store_historical_data",
            "_async_store_quote",
            "_async_store_position",
            "_async_store_funds",
            "_async_get_latest_signals",
            "_async_update_trade",
            "_async_update_order_status",
            "_async_get_trade",
            "_async_log_audit",
            "_async_get_historical_data",
        ]:
            assert hasattr(Database, method_name), (
                f"Database should have {method_name} method"
            )

    async def test_async_create_signal(self, temp_db):
        """Test async signal creation."""
        if not AIOSQLITE_AVAILABLE:
            pytest.skip("aiosqlite not available")

        await temp_db.async_initialize()

        signal = Signal(
            signal_id="test_signal_001",
            symbol="TEST",
            signal_type=SignalType.BUY,
            strength=0.8,
            timestamp=datetime.now(UTC),
            indicators={"rsi": 30.0, "macd": 1.5},
            confidence=0.9,
            metadata={"scan_type": "technical", "source": "test"},
        )

        result = await temp_db.async_create_signal(signal)
        assert result is True

        signals = temp_db.get_latest_signals("TEST", limit=1)
        assert len(signals) == 1
        assert signals[0].signal_id == "test_signal_001"

    async def test_async_create_signal_core(self, temp_db):
        """Test the core aiosqlite signal creation method directly."""
        if not AIOSQLITE_AVAILABLE:
            pytest.skip("aiosqlite not available")

        await temp_db.async_initialize()

        signal = Signal(
            signal_id="test_signal_002",
            symbol="TEST",
            signal_type=SignalType.SELL,
            strength=0.7,
            timestamp=datetime.now(UTC),
            indicators={"rsi": 70.0, "macd": -1.5},
            confidence=0.8,
            metadata={"scan_type": "technical", "source": "test"},
        )

        result = await temp_db._async_create_signal(signal)
        assert result is True

        signals = temp_db.get_latest_signals("TEST", limit=1)
        assert len(signals) == 1
        assert signals[0].signal_id == "test_signal_002"

    async def test_async_store_historical_data(self, temp_db):
        """Test async historical data storage."""
        if not AIOSQLITE_AVAILABLE:
            pytest.skip("aiosqlite not available")

        await temp_db.async_initialize()

        now = datetime.now(UTC)
        historical_data = [
            HistoricalData(
                symbol="TEST",
                timestamp=now - timedelta(minutes=1),
                open=100.0,
                high=105.0,
                low=99.0,
                close=104.0,
                volume=10000,
                interval="1d",
            ),
            HistoricalData(
                symbol="TEST",
                timestamp=now,
                open=104.0,
                high=108.0,
                low=103.0,
                close=107.0,
                volume=12000,
                interval="1d",
            ),
        ]

        result = await temp_db.async_store_historical_data(historical_data)
        assert result is True

        conn = temp_db._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM historical_data WHERE symbol = ?", ("TEST",)
        )
        count = cursor.fetchone()[0]
        conn.close()
        assert count == 2

    async def test_async_store_quote(self, temp_db):
        """Test async quote data storage."""
        if not AIOSQLITE_AVAILABLE:
            pytest.skip("aiosqlite not available")

        await temp_db.async_initialize()

        now = datetime.now(UTC)
        quote = QuoteData(
            symbol="TEST",
            last_price=105.0,
            open=100.0,
            high=106.0,
            low=99.5,
            close=104.5,
            volume=15000,
            timestamp=now,
            change=5.0,
            change_percent=4.76,
        )

        result = await temp_db.async_store_quote(quote)
        assert result is True

        conn = temp_db._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM quotes WHERE symbol = ?", ("TEST",))
        count = cursor.fetchone()[0]
        conn.close()
        assert count == 1

    async def test_async_store_position(self, temp_db):
        """Test async position storage."""
        if not AIOSQLITE_AVAILABLE:
            pytest.skip("aiosqlite not available")

        await temp_db.async_initialize()

        now = datetime.now(UTC)
        position = Position(
            symbol="TEST",
            quantity=10,
            average_price=100.0,
            last_price=105.0,
            pnl=50.0,
            product_type=ProductType.MIS,
            buy_quantity=10,
            sell_quantity=0,
            timestamp=now,
        )

        result = await temp_db.async_store_position(position)
        assert result is True

        conn = temp_db._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM positions WHERE symbol = ?", ("TEST",))
        count = cursor.fetchone()[0]
        conn.close()
        assert count == 1

    async def test_async_store_funds(self, temp_db):
        """Test async funds data storage."""
        if not AIOSQLITE_AVAILABLE:
            pytest.skip("aiosqlite not available")

        await temp_db.async_initialize()

        now = datetime.now(UTC)
        funds = FundsData(
            available_cash=50000.0,
            utilized_margin=20000.0,
            available_margin=30000.0,
            total_equity=70000.0,
            timestamp=now,
        )

        result = await temp_db.async_store_funds(funds)
        assert result is True

        conn = temp_db._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM funds")
        count = cursor.fetchone()[0]
        conn.close()
        assert count == 1

    async def test_async_get_latest_signals(self, temp_db):
        """Test async retrieval of latest signals."""
        if not AIOSQLITE_AVAILABLE:
            pytest.skip("aiosqlite not available")

        await temp_db.async_initialize()

        base_time = datetime.now(UTC)
        signals = [
            Signal(
                signal_id=f"test_signal_{i:03d}",
                symbol="TEST",
                signal_type=SignalType.BUY if i % 2 == 0 else SignalType.SELL,
                strength=0.7 + i * 0.05,
                timestamp=base_time - timedelta(seconds=10 - i),
                indicators={"rsi": 30.0 + i * 2, "macd": 1.0 + i * 0.2},
                confidence=0.8 + i * 0.02,
                metadata={"scan_type": "technical", "source": "test"},
            )
            for i in range(3)
        ]

        for signal in signals:
            temp_db.create_signal(signal)

        retrieved_signals = await temp_db.async_get_latest_signals("TEST", limit=2)
        assert len(retrieved_signals) == 2

    async def test_async_get_latest_signals_with_scan_type(self, temp_db):
        """Test async retrieval of latest signals with scan type filter."""
        if not AIOSQLITE_AVAILABLE:
            pytest.skip("aiosqlite not available")

        await temp_db.async_initialize()

        now = datetime.now(UTC)
        signals = [
            Signal(
                signal_id="signal_tech_001",
                symbol="TEST",
                signal_type=SignalType.BUY,
                strength=0.8,
                timestamp=now,
                indicators={"rsi": 30.0},
                confidence=0.9,
                metadata={"scan_type": "technical", "source": "test"},
            ),
            Signal(
                signal_id="signal_fund_001",
                symbol="TEST",
                signal_type=SignalType.SELL,
                strength=0.7,
                timestamp=now,
                indicators={"pe_ratio": 25.0},
                confidence=0.85,
                metadata={"scan_type": "fundamental", "source": "test"},
            ),
        ]

        for signal in signals:
            temp_db.create_signal(signal)

        retrieved_signals = await temp_db.async_get_latest_signals(
            "TEST", limit=10, scan_type="technical"
        )
        assert len(retrieved_signals) == 1
        assert retrieved_signals[0].signal_id == "signal_tech_001"

    async def test_async_update_trade(self, temp_db):
        """Test async trade update."""
        if not AIOSQLITE_AVAILABLE:
            pytest.skip("aiosqlite not available")

        await temp_db.async_initialize()

        now = datetime.now(UTC)
        trade = Trade(
            trade_id="test_trade_001",
            symbol="TEST",
            quantity=10,
            entry_price=100.0,
            exit_price=None,
            entry_time=now,
            exit_time=None,
            transaction_type=TransactionType.BUY,
            product_type=ProductType.MIS,
            pnl=None,
            status="OPEN",
            strategy="test_strategy",
        )
        temp_db.create_trade(trade)
        # Release the sync connection so the aiosqlite writer can proceed.
        temp_db.close_all()

        updated_trade = Trade(
            trade_id="test_trade_001",
            symbol="TEST",
            quantity=10,
            entry_price=100.0,
            exit_price=105.0,
            entry_time=now,
            exit_time=now,
            transaction_type=TransactionType.BUY,
            product_type=ProductType.MIS,
            pnl=50.0,
            status="COMPLETED",
            strategy="test_strategy",
        )

        result = await temp_db.async_update_trade(updated_trade)
        assert result is True

        retrieved_trade = temp_db.get_trade("test_trade_001")
        assert retrieved_trade is not None
        assert retrieved_trade.status == "COMPLETED"
        assert retrieved_trade.pnl == 50.0

    async def test_async_update_order_status(self, temp_db):
        """Test async order status update."""
        if not AIOSQLITE_AVAILABLE:
            pytest.skip("aiosqlite not available")

        await temp_db.async_initialize()

        result = await temp_db.async_update_order_status(
            "nonexistent_order", "COMPLETED"
        )
        assert result is False  # no order exists to update

    async def test_async_get_trade(self, temp_db):
        """Test async trade retrieval."""
        if not AIOSQLITE_AVAILABLE:
            pytest.skip("aiosqlite not available")

        await temp_db.async_initialize()

        now = datetime.now(UTC)
        trade = Trade(
            trade_id="test_trade_002",
            symbol="TEST",
            quantity=5,
            entry_price=95.0,
            exit_price=None,
            entry_time=now,
            exit_time=None,
            transaction_type=TransactionType.BUY,
            product_type=ProductType.MIS,
            pnl=None,
            status="OPEN",
            strategy="test_strategy",
        )
        temp_db.create_trade(trade)

        retrieved_trade = await temp_db.async_get_trade("test_trade_002")
        assert retrieved_trade is not None
        assert retrieved_trade.trade_id == "test_trade_002"
        assert retrieved_trade.symbol == "TEST"

        nonexistent_trade = await temp_db.async_get_trade("nonexistent_trade")
        assert nonexistent_trade is None

    async def test_async_log_audit(self, temp_db):
        """Test async audit logging."""
        if not AIOSQLITE_AVAILABLE:
            pytest.skip("aiosqlite not available")

        await temp_db.async_initialize()

        await temp_db._async_log_audit(
            action="TEST",
            entity_type="test_entity",
            entity_id="test_id_001",
            user="test_user",
            metadata={"test_key": "test_value"},
            previous_state={"old": "state"},
            new_state={"new": "state"},
        )

        conn = temp_db._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM audit_log WHERE entity_id = ?", ("test_id_001",)
        )
        count = cursor.fetchone()[0]
        conn.close()
        assert count == 1

    async def test_async_audit_log_failure(self, temp_db):
        """Test async audit log failure when async pool is unavailable."""
        if not AIOSQLITE_AVAILABLE:
            pytest.skip("aiosqlite not available")

        await temp_db.async_initialize()
        temp_db._async_pool = None

        # When the pool is unavailable the method returns gracefully.
        await temp_db._async_log_audit(
            action="TEST",
            entity_type="test_entity",
            entity_id="test_id_002",
            user="test_user",
        )

    async def test_core_async_store_historical_data(self, temp_db):
        """Test the core async historical data storage method directly."""
        if not AIOSQLITE_AVAILABLE:
            pytest.skip("aiosqlite not available")

        await temp_db.async_initialize()

        now = datetime.now(UTC)
        historical_data = [
            HistoricalData(
                symbol="CORE",
                timestamp=now - timedelta(minutes=2),
                open=100.0,
                high=106.0,
                low=98.0,
                close=105.0,
                volume=15000,
                interval="1d",
            ),
            HistoricalData(
                symbol="CORE",
                timestamp=now,
                open=105.0,
                high=110.0,
                low=104.0,
                close=109.0,
                volume=18000,
                interval="1d",
            ),
        ]

        result = await temp_db._async_store_historical_data(historical_data)
        assert result is True

        conn = temp_db._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM historical_data WHERE symbol = ?", ("CORE",)
        )
        count = cursor.fetchone()[0]
        conn.close()
        assert count == 2

    async def test_core_async_store_quote(self, temp_db):
        """Test the core async quote storage method directly."""
        if not AIOSQLITE_AVAILABLE:
            pytest.skip("aiosqlite not available")

        await temp_db.async_initialize()

        now = datetime.now(UTC)
        quote = QuoteData(
            symbol="CORE",
            last_price=108.0,
            open=105.0,
            high=110.0,
            low=104.5,
            close=109.5,
            volume=20000,
            timestamp=now,
            change=8.0,
            change_percent=7.41,
        )

        result = await temp_db._async_store_quote(quote)
        assert result is True

        conn = temp_db._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM quotes WHERE symbol = ?", ("CORE",))
        count = cursor.fetchone()[0]
        conn.close()
        assert count == 1

    async def test_core_async_store_position(self, temp_db):
        """Test the core async position storage method directly."""
        if not AIOSQLITE_AVAILABLE:
            pytest.skip("aiosqlite not available")

        await temp_db.async_initialize()

        now = datetime.now(UTC)
        position = Position(
            symbol="CORE",
            quantity=15,
            average_price=105.0,
            last_price=108.0,
            pnl=45.0,
            product_type=ProductType.MIS,
            buy_quantity=15,
            sell_quantity=0,
            timestamp=now,
        )

        result = await temp_db._async_store_position(position)
        assert result is True

        conn = temp_db._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM positions WHERE symbol = ?", ("CORE",))
        count = cursor.fetchone()[0]
        conn.close()
        assert count == 1

    async def test_core_async_store_funds(self, temp_db):
        """Test the core async funds storage method directly."""
        if not AIOSQLITE_AVAILABLE:
            pytest.skip("aiosqlite not available")

        await temp_db.async_initialize()

        now = datetime.now(UTC)
        funds = FundsData(
            available_cash=60000.0,
            utilized_margin=25000.0,
            available_margin=35000.0,
            total_equity=85000.0,
            timestamp=now,
        )

        result = await temp_db._async_store_funds(funds)
        assert result is True

        conn = temp_db._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM funds")
        count = cursor.fetchone()[0]
        conn.close()
        assert count == 1

    async def test_core_async_get_latest_signals(self, temp_db):
        """Test the core async signal retrieval method directly."""
        if not AIOSQLITE_AVAILABLE:
            pytest.skip("aiosqlite not available")

        await temp_db.async_initialize()

        base_time = datetime.now(UTC)
        signals = [
            Signal(
                signal_id=f"core_signal_{i:03d}",
                symbol="CORE",
                signal_type=SignalType.BUY if i % 2 == 0 else SignalType.SELL,
                strength=0.75 + i * 0.03,
                timestamp=base_time - timedelta(seconds=15 - i),
                indicators={"rsi": 25.0 + i * 3, "macd": 1.2 + i * 0.3},
                confidence=0.85 + i * 0.01,
                metadata={"scan_type": "core_test", "source": "test"},
            )
            for i in range(4)
        ]

        for signal in signals:
            temp_db.create_signal(signal)

        retrieved_signals = await temp_db._async_get_latest_signals("CORE", limit=3)
        assert len(retrieved_signals) == 3

    async def test_core_async_update_trade(self, temp_db):
        """Test the core async trade update method directly."""
        if not AIOSQLITE_AVAILABLE:
            pytest.skip("aiosqlite not available")

        await temp_db.async_initialize()

        now = datetime.now(UTC)
        trade = Trade(
            trade_id="core_trade_001",
            symbol="CORE",
            quantity=20,
            entry_price=105.0,
            exit_price=None,
            entry_time=now,
            exit_time=None,
            transaction_type=TransactionType.BUY,
            product_type=ProductType.MIS,
            pnl=None,
            status="OPEN",
            strategy="core_strategy",
        )
        temp_db.create_trade(trade)
        # Release the sync connection so the aiosqlite writer can proceed.
        temp_db.close_all()

        updated_trade = Trade(
            trade_id="core_trade_001",
            symbol="CORE",
            quantity=20,
            entry_price=105.0,
            exit_price=110.0,
            entry_time=now,
            exit_time=now,
            transaction_type=TransactionType.BUY,
            product_type=ProductType.MIS,
            pnl=100.0,
            status="COMPLETED",
            strategy="core_strategy",
        )

        result = await temp_db._async_update_trade(updated_trade)
        assert result is True

        retrieved_trade = temp_db.get_trade("core_trade_001")
        assert retrieved_trade is not None
        assert retrieved_trade.status == "COMPLETED"
        assert retrieved_trade.pnl == 100.0

    async def test_core_async_update_order_status(self, temp_db):
        """Test the core async order status update method directly."""
        if not AIOSQLITE_AVAILABLE:
            pytest.skip("aiosqlite not available")

        await temp_db.async_initialize()

        now = datetime.now(UTC)
        order = Order(
            order_id="core_order_001",
            symbol="CORE",
            quantity=10,
            order_type="LIMIT",
            price=108.0,
            trigger_price=None,
            variety="regular",
            transaction_type=TransactionType.BUY,
            product_type=ProductType.MIS,
            status="OPEN",
            timestamp=now,
            filled_quantity=0,
            average_price=108.0,
        )
        temp_db.store_order(order)

        result = await temp_db._async_update_order_status("core_order_001", "COMPLETED")
        assert result is True

        updated_order = temp_db.get_order("core_order_001")
        assert updated_order is not None
        assert updated_order.status == "COMPLETED"

    async def test_core_async_get_trade(self, temp_db):
        """Test the core async trade retrieval method directly."""
        if not AIOSQLITE_AVAILABLE:
            pytest.skip("aiosqlite not available")

        await temp_db.async_initialize()

        now = datetime.now(UTC)
        trade = Trade(
            trade_id="core_trade_002",
            symbol="CORE",
            quantity=15,
            entry_price=108.0,
            exit_price=None,
            entry_time=now,
            exit_time=None,
            transaction_type=TransactionType.BUY,
            product_type=ProductType.MIS,
            pnl=None,
            status="OPEN",
            strategy="core_strategy",
        )
        temp_db.create_trade(trade)

        retrieved_trade = await temp_db._async_get_trade("core_trade_002")
        assert retrieved_trade is not None
        assert retrieved_trade.trade_id == "core_trade_002"
        assert retrieved_trade.symbol == "CORE"

        nonexistent_trade = await temp_db._async_get_trade("nonexistent_core_trade")
        assert nonexistent_trade is None

    async def test_core_async_log_audit(self, temp_db):
        """Test the core async audit logging method directly."""
        if not AIOSQLITE_AVAILABLE:
            pytest.skip("aiosqlite not available")

        await temp_db.async_initialize()

        await temp_db._async_log_audit(
            action="CORE_TEST",
            entity_type="core_entity",
            entity_id="core_id_001",
            user="core_user",
            metadata={"core_key": "core_value"},
            previous_state={"old_core": "state"},
            new_state={"new_core": "state"},
        )

        conn = temp_db._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM audit_log WHERE entity_id = ?", ("core_id_001",)
        )
        count = cursor.fetchone()[0]
        conn.close()
        assert count == 1

    async def test_pool_lifecycle_and_cleanup(self, temp_db):
        """Test proper pool lifecycle management and cleanup."""
        if not AIOSQLITE_AVAILABLE:
            pytest.skip("aiosqlite not available")

        await temp_db.async_initialize()
        assert hasattr(temp_db, "_async_pool")
        assert temp_db._async_pool is not None

        signal = Signal(
            signal_id="pool_test_signal",
            symbol="POOL",
            signal_type=SignalType.BUY,
            strength=0.8,
            timestamp=datetime.now(UTC),
            indicators={"rsi": 30.0},
            confidence=0.9,
        )

        result = await temp_db.async_create_signal(signal)
        assert result is True

        await temp_db.async_close_all()
        assert temp_db._async_pool is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])


class TestProductionAsyncWiring:
    """Regression: production must wire the aiosqlite implementations.

    Found live 08Sep2026: the supervised P5 run attached the async pool
    but every cycle died with ``'Database' object has no attribute
    '_async_create_signal'`` -- the binding module was only ever imported
    by tests (its import-time ``extend_database_class()`` call masked the
    gap). ``async_initialize`` now performs the binding itself.
    """

    async def test_async_initialize_extends_database_class(
        self, tmp_path: Path
    ) -> None:
        """async_initialize() binds the _async_* implementations even in a
        process that never imported the additions module."""
        db = Database(
            db_path=tmp_path / "wiring.db",
            audit_log_path=tmp_path / "wiring_audit.jsonl",
        )
        bound_names = [
            "_async_create_signal",
            "_async_store_quote",
            "_async_store_historical_data",
        ]
        saved = {name: getattr(Database, name, None) for name in bound_names}
        try:
            # Simulate the production import order: no bindings present.
            for name in bound_names:
                if hasattr(Database, name):
                    delattr(Database, name)
            assert not any(hasattr(Database, name) for name in bound_names)

            await db.async_initialize()

            assert all(hasattr(Database, name) for name in bound_names), (
                "async_initialize must bind the aiosqlite implementations"
            )
            assert db._async_pool is not None
        finally:
            for name, method in saved.items():
                if method is not None and not hasattr(Database, name):
                    setattr(Database, name, method)
            if db._async_pool is not None:
                try:
                    await db.async_close_all()
                except Exception:
                    pass
            db.close_all()

    async def test_async_create_signal_works_with_pool_attached(
        self, tmp_path: Path
    ) -> None:
        """The exact live failure: async_create_signal with the pool set
        must persist via the bound aiosqlite path, not AttributeError."""
        db = Database(
            db_path=tmp_path / "outcome.db",
            audit_log_path=tmp_path / "outcome_audit.jsonl",
        )
        await db.async_initialize()
        try:
            signal = Signal(
                symbol="NIFTY",
                signal_type=SignalType.BUY,
                strength=0.8,
                timestamp=datetime.now(UTC),
                indicators={"put_call_volume_ratio": 1.4},
                confidence=0.8,
            )
            assert await db.async_create_signal(signal) is True
        finally:
            await db.async_close_all()
            db.close_all()


class TestTradeDecisionSyncPersistence:
    """Sync trade-decision CRUD (database.py 1947-2179) — previously untested."""

    def test_create_and_get_round_trip(self, temp_db: Database) -> None:
        """INSERT then SELECT preserves every column incl. F8-L-02 snapshot."""
        decision = _make_decision()
        assert temp_db.create_trade_decision(decision) is True

        loaded = temp_db.get_trade_decision(decision.decision_id)
        assert loaded is not None
        assert loaded.decision_id == decision.decision_id
        assert loaded.symbol == "TCS"
        assert loaded.decision_type is SignalType.BUY
        assert Decimal(str(loaded.composite_strength)) == Decimal("0.73")
        assert loaded.timestamp == _SEED_EPOCH
        assert loaded.as_of_date == date(2026, 9, 11)
        assert Decimal(str(loaded.entry_price)) == Decimal("4100.50")
        assert loaded.quantity == 25
        assert Decimal(str(loaded.stop_loss)) == Decimal("4050.00")
        assert loaded.take_profit == float(Decimal("4210.00"))
        assert loaded.trailing_stop_config == {"mode": "atr", "atr_multiplier": 2.5}
        assert Decimal(str(loaded.risk_percentage)) == Decimal("0.01")
        assert loaded.var_analysis["horizon_days"] == 1
        assert Decimal(str(loaded.var_analysis["var_95"])) == Decimal("1234.56")
        assert loaded.gating_rules_result == {"passed": True, "rules_evaluated": 7}
        assert loaded.source_breakdown == {"ta": 0.6, "sentiment": 0.4}
        assert loaded.status == "PENDING"

    def test_get_missing_decision_returns_none(self, temp_db: Database) -> None:
        """Unknown decision_id maps to None, not an exception."""
        assert temp_db.get_trade_decision("decision_does_not_exist") is None

    def test_minimal_decision_null_json_columns_round_trip(
        self, temp_db: Database
    ) -> None:
        """Defaults-only decision reads back through the NULL-JSON guards."""
        decision = _make_decision(
            decision_id="decision_20260912091500000000_00000000",
            as_of_date=None,
        )
        decision.trailing_stop_config = {}
        decision.var_analysis = {}
        decision.gating_rules_result = {}
        decision.source_breakdown = {}
        decision.metadata = {}
        decision.take_profit = None
        assert temp_db.create_trade_decision(decision) is True

        loaded = temp_db.get_trade_decision(decision.decision_id)
        assert loaded is not None
        assert loaded.trailing_stop_config == {}
        assert loaded.var_analysis == {}
        assert loaded.gating_rules_result == {}
        assert loaded.source_breakdown == {}
        assert loaded.metadata == {}
        assert loaded.take_profit is None
        assert loaded.as_of_date is None

    def test_list_filters_symbol_status_and_limit(self, temp_db: Database) -> None:
        """All four WHERE-branch shapes of get_trade_decisions are exercised."""
        ids = {
            "decision_20260912091500000000_a0000001": ("TCS", "PENDING"),
            "decision_20260912091500000000_a0000002": ("TCS", "ROUTED"),
            "decision_20260912091500000000_a0000003": ("INFY", "PENDING"),
        }
        for i, (did, (symbol, status)) in enumerate(sorted(ids.items())):
            decision = _make_decision(decision_id=did, symbol=symbol)
            decision.status = status
            decision.timestamp = _SEED_EPOCH + timedelta(minutes=i)
            assert temp_db.create_trade_decision(decision) is True

        by_symbol = temp_db.get_trade_decisions(symbol="TCS")
        assert [d.decision_id for d in by_symbol] == [
            "decision_20260912091500000000_a0000002",
            "decision_20260912091500000000_a0000001",
        ]

        by_status = temp_db.get_trade_decisions(status="PENDING")
        assert {d.decision_id for d in by_status} == {
            "decision_20260912091500000000_a0000001",
            "decision_20260912091500000000_a0000003",
        }

        both = temp_db.get_trade_decisions(symbol="TCS", status="PENDING")
        assert [d.decision_id for d in both] == [
            "decision_20260912091500000000_a0000001"
        ]

        limited = temp_db.get_trade_decisions(limit=2)
        assert len(limited) == 2

    def test_update_status_round_trip_and_audit(self, temp_db: Database) -> None:
        """Status update persists, returns False on missing id, and dual-writes."""
        decision = _make_decision(decision_id="decision_20260912091500000000_b0000001")
        assert temp_db.create_trade_decision(decision) is True

        assert (
            temp_db.update_trade_decision_status(decision.decision_id, "ROUTED") is True
        )
        loaded = temp_db.get_trade_decision(decision.decision_id)
        assert loaded is not None
        assert loaded.status == "ROUTED"

        entries = temp_db.get_audit_log(entity_type="trade_decision")
        actions = [e.action for e in entries]
        assert actions.count("CREATE") == 1
        assert actions.count("UPDATE") == 1

        assert (
            temp_db.update_trade_decision_status("decision_missing_zz", "ROUTED")
            is False
        )


class TestTradeDecisionAsyncDispatch:
    """Async trade-decision paths: the dispatch pins were born RED (2026-09-12)."""

    def test_extension_registers_the_dispatched_name(self) -> None:
        """async_create_trade_decision must dispatch to a REGISTERED name.

        Born RED (twice over): (1) pre-fix, ``_async_create_trade_decision``
        — the name the wrapper dispatched to — was never registered by the
        extension, so the preferred aiosqlite branch died on AttributeError
        and silently fell back whenever the pool was attached; (2) the
        source-level pin below also fails on the pre-fix wrapper text. The
        fix dispatches to the registered ``_async_record_trade_decision``.
        """
        extend_database_class()
        assert hasattr(Database, "_async_record_trade_decision")
        # The dispatch target must be the registered implementation: assert
        # on the wrapper's own source so a future rename cannot silently
        # resurrect the never-wired AttributeError fallback.
        wrapper_src = inspect.getsource(Database.async_create_trade_decision)
        assert "_async_record_trade_decision" in wrapper_src
        assert "_async_create_trade_decision" not in wrapper_src

    def test_async_log_audit_binding_is_registered(self) -> None:
        """Contract prerequisite: the extension binds _async_log_audit.

        ASYNC_DISPATCH_DOCUMENTATION.md lists it as a primary method; the
        dispatch itself is pinned by the spy test below.
        """
        extend_database_class()
        assert hasattr(Database, "_async_log_audit")

    @pytest.mark.asyncio
    async def test_async_log_audit_dispatches_to_registered_impl(
        self, temp_db: Database, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Pooled async_log_audit must run the REGISTERED implementation.

        Born RED: ``async_log_audit`` was a bare to_thread wrapper that never
        consulted the pool, so the registered dual-write implementation was
        unreachable and the documented tri-modal dispatch contract
        (ASYNC_DISPATCH_DOCUMENTATION.md) was violated for this method.
        """
        extend_database_class()
        dispatch_flag: list[bool] = []

        original = cast("Any", Database)._async_log_audit

        async def _spy(self: Database, *args: object, **kwargs: object) -> None:
            dispatch_flag.append(True)
            await original(self, *args, **kwargs)

        monkeypatch.setattr(Database, "_async_log_audit", _spy)

        await temp_db.async_initialize()
        try:
            assert temp_db._async_pool is not None
            await temp_db.async_log_audit(
                action="ROUTE",
                entity_type="trade_decision",
                entity_id="decision_20260912091500000000_c0000004",
                metadata={"outcome": "dispatch-probe"},
            )
            assert dispatch_flag == [True]
        finally:
            await temp_db.async_close_all()
            temp_db.close_all()

    @pytest.mark.asyncio
    async def test_pooled_create_round_trips_via_aiosqlite(
        self, temp_db: Database
    ) -> None:
        """With the pool attached, the pooled path persists and reads back."""
        await temp_db.async_initialize()
        try:
            assert temp_db._async_pool is not None
            assert AIOSQLITE_AVAILABLE is True

            decision = _make_decision(
                decision_id="decision_20260912091500000000_c0000001"
            )
            assert await temp_db.async_create_trade_decision(decision) is True

            loaded = await temp_db.async_get_trade_decision(decision.decision_id)
            assert loaded is not None
            assert loaded.symbol == "TCS"
            assert loaded.as_of_date == date(2026, 9, 11)
            assert Decimal(str(loaded.entry_price)) == Decimal("4100.50")
        finally:
            await temp_db.async_close_all()
            temp_db.close_all()

    @pytest.mark.asyncio
    async def test_unpooled_create_falls_back_to_sync_row(
        self, temp_db: Database
    ) -> None:
        """Without a pool the to_thread fallback still persists the row."""
        assert temp_db._async_pool is None

        decision = _make_decision(decision_id="decision_20260912091500000000_c0000002")
        assert await temp_db.async_create_trade_decision(decision) is True

        loaded = temp_db.get_trade_decision(decision.decision_id)
        assert loaded is not None
        assert loaded.decision_id == decision.decision_id

    @pytest.mark.asyncio
    async def test_async_log_audit_dual_writes_jsonl_and_db(
        self, temp_db: Database
    ) -> None:
        """The dual-write audit path lands in BOTH trails with a valid chain.

        Born RED as a unit: the registered implementation ran only when the
        dispatch existed; now both the dispatch contract and the write
        behavior (JSONL row + sha-chained DB row) are pinned.
        """
        await temp_db.async_initialize()
        try:
            assert temp_db._async_pool is not None
            await temp_db.async_log_audit(
                action="ROUTE",
                entity_type="trade_decision",
                entity_id="decision_20260912091500000000_c0000003",
                metadata={"outcome": "success", "decision_type": "BUY"},
                new_state={"status": "ROUTED"},
            )

            # JSONL trail: parse the temp audit file for the entity id.
            jsonl_rows = [
                json.loads(line)
                for line in temp_db.audit_log_path.read_text(
                    encoding="utf-8"
                ).splitlines()
                if line.strip()
            ]
            jsonl_hits = [
                r
                for r in jsonl_rows
                if r["entity_id"] == "decision_20260912091500000000_c0000003"
            ]
            assert len(jsonl_hits) == 1
            assert jsonl_hits[0]["action"] == "ROUTE"
            assert jsonl_hits[0]["metadata"]["outcome"] == "success"

            # DB trail: sha256 over the entry minus the hash field itself.
            rows = temp_db.get_audit_log(entity_type="trade_decision", limit=10)
            db_hits = [
                r
                for r in rows
                if r.entity_id == "decision_20260912091500000000_c0000003"
            ]
            assert len(db_hits) == 1
            raw = json.loads(
                temp_db.audit_log_path.read_text(encoding="utf-8").splitlines()[-1]
            )
            expected = {k: v for k, v in raw.items() if k != "sha256_hash"}
            assert temp_db._calculate_sha256(expected) == raw["sha256_hash"]
        finally:
            await temp_db.async_close_all()
            temp_db.close_all()

    @pytest.mark.asyncio
    async def test_async_log_audit_jsonl_failure_aborts_db_write(
        self, temp_db: Database
    ) -> None:
        """A failed JSONL write aborts the DB write and raises RuntimeError.

        Pins the async half of the dual-write guarantee documented on the
        sync ``_log_audit`` (database.py: "If JSONL write fails, exception
        is raised before DB commit"): the raise-and-abort branch in the
        aiosqlite-backed implementation (database_async_additions.py) was
        never executed by any test.  The failure is REAL filesystem I/O --
        the audit path is pointed at an existing directory, so the append
        open fails with PermissionError (Windows) / IsADirectoryError
        (POSIX), both OSError subtypes -- not a mock.
        """
        await temp_db.async_initialize()
        try:
            assert temp_db._async_pool is not None

            jsonl_dir = temp_db.audit_log_path.with_suffix(".jsonl_dir")
            jsonl_dir.mkdir()
            temp_db.audit_log_path = jsonl_dir

            entity_id = "decision_20260913020000000000_c0000010"
            with pytest.raises(RuntimeError, match="Database commit aborted"):
                await temp_db.async_log_audit(
                    action="ROUTE",
                    entity_type="trade_decision",
                    entity_id=entity_id,
                    metadata={"outcome": "injected_jsonl_failure"},
                )

            # DB trail: the commit must never have happened.
            rows = temp_db.get_audit_log(entity_type="trade_decision", limit=10)
            assert [r for r in rows if r.entity_id == entity_id] == []
            # JSONL trail: the path is still the directory -- no file was
            # half-written behind the failed append.
            assert temp_db.audit_log_path.is_dir()
        finally:
            await temp_db.async_close_all()
            temp_db.close_all()

    @pytest.mark.asyncio
    async def test_async_log_audit_no_pool_delegates_to_sync_dual_write(
        self, temp_db: Database
    ) -> None:
        """Without a pool, the bound impl delegates to the public wrapper.

        Pins the pool-None branch of ``_async_log_audit``: it re-enters
        ``Database.async_log_audit``, which routes to the to_thread sync
        dual-write.  The public wrapper never reaches that branch on its
        own when the pool is absent, so the delegation is exercised
        directly against the bound implementation and asserted as the
        dual-write consistency invariant: the SAME entry (same sha256
        hash) lands in BOTH trails.
        """
        assert temp_db._async_pool is None

        entity_id = "decision_20260913020000000000_c0000011"
        # Bound at runtime by extend_database_class(); invisible statically.
        await cast("Any", temp_db)._async_log_audit(
            action="ROUTE",
            entity_type="trade_decision",
            entity_id=entity_id,
            metadata={"outcome": "no_pool_delegation"},
            new_state={"status": "ROUTED"},
        )

        # JSONL trail: exactly one row for the entity.
        rows = [
            json.loads(line)
            for line in temp_db.audit_log_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        hits = [r for r in rows if r["entity_id"] == entity_id]
        assert len(hits) == 1

        # DB trail: the sync dual-write persisted the same entry with the
        # same chain hash -- the two trails agree.
        db_rows = temp_db.get_audit_log(entity_type="trade_decision", limit=10)
        db_hits = [r for r in db_rows if r.entity_id == entity_id]
        assert len(db_hits) == 1
        assert db_hits[0].action == "ROUTE"
        assert db_hits[0].sha256_hash == hits[0]["sha256_hash"]
