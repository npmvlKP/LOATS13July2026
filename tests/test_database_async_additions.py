#!/usr/bin/env python3
"""
Comprehensive test suite for database_async_additions.py module.

This test file covers all async database operations to address the 0% coverage issue.
"""

import asyncio
import json
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from loats.database import Database
from loats.database_async_additions import AIOSQLITE_AVAILABLE, extend_database_class
from loats.models import (
    AuditLogEntry,
    FundsData,
    HistoricalData,
    Order,
    Position,
    QuoteData,
    Signal,
    Trade,
)


class TestDatabaseAsyncAdditions:
    """Test suite for async database operations."""

    @pytest.fixture
    def temp_db(self):
        """Create a temporary database for testing."""
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp_dir:
            db_path = Path(temp_dir) / "test.db"
            audit_log_path = Path(temp_dir) / "test_audit.jsonl"

            # Initialize database
            db = Database(db_path=db_path, audit_log_path=audit_log_path)
            db._initialize_database()

            # Ensure async methods are extended
            extend_database_class()

            yield db

            # Clean up - close async pool first, then sync connections
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

    def test_extend_database_class(self):
        """Test that the Database class is properly extended with async methods."""
        # Ensure the extension function works
        extend_database_class()

        # Verify that all async methods are added
        for method_name in [
            "_async_create_signal",
            "_async_store_historical_data",
            "_async_store_quote",
            "_async_store_position",
            "_async_store_funds",
            "_async_get_latest_signals",
            "_async_update_trade",
            "_async_update_order_status",
            "async_get_trade",
            "_async_log_audit",
        ]:
            assert hasattr(Database, method_name), (
                f"Database should have {method_name} method"
            )

        # Verify that wrapper methods are added
        for method_name in [
            "async_create_signal",
            "async_store_historical_data",
            "async_store_quote",
            "async_store_position",
            "async_store_funds",
            "async_get_latest_signals",
            "async_update_trade",
            "async_update_order_status",
        ]:
            assert hasattr(Database, method_name), (
                f"Database should have {method_name} method"
            )

    async def test_async_create_signal(self, temp_db):
        """Test async signal creation."""
        if not AIOSQLITE_AVAILABLE:
            pytest.skip("aiosqlite not available")

        # Initialize async pool
        await temp_db.async_initialize()

        # Create test signal
        signal = Signal(
            signal_id="test_signal_001",
            symbol="TEST",
            signal_type="BUY",
            strength=0.8,
            timestamp=datetime.now(UTC),
            indicators={"rsi": 30.0, "macd": 1.5},
            confidence=0.9,
            metadata={"scan_type": "technical", "source": "test"},
        )

        # Test async signal creation
        result = await temp_db.async_create_signal(signal)
        assert result is True

        # Verify signal was created
        signals = temp_db.get_latest_signals("TEST", limit=1)
        assert len(signals) == 1
        assert signals[0].signal_id == "test_signal_001"

        # Verify audit log was created in database (may skip JSONL in test mode)
        conn = temp_db._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM audit_log WHERE entity_id = ?", ("test_signal_001",)
        )
        count = cursor.fetchone()[0]
        conn.close()
        assert count >= 1

    async def test_async_create_signal_fallback(self, temp_db):
        """Test async signal creation fallback when aiosqlite is not available."""
        if AIOSQLITE_AVAILABLE:
            # Temporarily disable aiosqlite for this test
            with patch("loats.database_async_additions.AIOSQLITE_AVAILABLE", False):
                # Create test signal
                signal = Signal(
                    signal_id="test_signal_002",
                    symbol="TEST",
                    signal_type="SELL",
                    strength=0.7,
                    timestamp=datetime.now(UTC),
                    indicators={"rsi": 70.0, "macd": -1.5},
                    confidence=0.8,
                    metadata={"scan_type": "technical", "source": "test"},
                )

                # Test async signal creation (should use fallback)
                result = await temp_db.async_create_signal(signal)
                assert result is True

                # Verify signal was created
                signals = temp_db.get_latest_signals("TEST", limit=1)
                assert len(signals) == 1

    async def test_async_store_historical_data(self, temp_db):
        """Test async historical data storage."""
        if not AIOSQLITE_AVAILABLE:
            pytest.skip("aiosqlite not available")

        # Initialize async pool
        await temp_db.async_initialize()

        # Create test historical data
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

        # Test async historical data storage
        result = await temp_db.async_store_historical_data(historical_data)
        assert result is True

        # Verify data was stored
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

        # Initialize async pool
        await temp_db.async_initialize()

        # Create test quote data
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

        # Test async quote storage
        result = await temp_db.async_store_quote(quote)
        assert result is True

        # Verify data was stored
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

        # Initialize async pool
        await temp_db.async_initialize()

        # Create test position
        now = datetime.now(UTC)
        position = Position(
            symbol="TEST",
            quantity=10,
            average_price=100.0,
            last_price=105.0,
            pnl=50.0,
            product_type="MIS",
            buy_quantity=10,
            sell_quantity=0,
            timestamp=now,
        )

        # Test async position storage
        result = await temp_db.async_store_position(position)
        assert result is True

        # Verify data was stored
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

        # Initialize async pool
        await temp_db.async_initialize()

        # Create test funds data
        now = datetime.now(UTC)
        funds = FundsData(
            available_cash=50000.0,
            utilized_margin=20000.0,
            available_margin=30000.0,
            total_equity=70000.0,
            timestamp=now,
        )

        # Test async funds storage
        result = await temp_db.async_store_funds(funds)
        assert result is True

        # Verify data was stored
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

        # Initialize async pool
        await temp_db.async_initialize()

        # Create test signals with increasing timestamps
        base_time = datetime.now(UTC)
        signals = [
            Signal(
                signal_id=f"test_signal_{i:03d}",
                symbol="TEST",
                signal_type="BUY" if i % 2 == 0 else "SELL",
                strength=0.7 + i * 0.05,
                timestamp=base_time - timedelta(seconds=10 - i),
                indicators={"rsi": 30.0 + i * 2, "macd": 1.0 + i * 0.2},
                confidence=0.8 + i * 0.02,
                metadata={"scan_type": "technical", "source": "test"},
            )
            for i in range(3)
        ]

        # Store signals using sync method
        for signal in signals:
            temp_db.create_signal(signal)

        # Test async signal retrieval
        retrieved_signals = await temp_db.async_get_latest_signals("TEST", limit=2)
        assert len(retrieved_signals) == 2

        # Verify the signals are the most recent ones
        signal_ids = {signal.signal_id for signal in retrieved_signals}
        assert "test_signal_002" in signal_ids
        assert "test_signal_001" in signal_ids

    async def test_async_get_latest_signals_with_scan_type(self, temp_db):
        """Test async retrieval of latest signals with scan type filter."""
        if not AIOSQLITE_AVAILABLE:
            pytest.skip("aiosqlite not available")

        # Initialize async pool
        await temp_db.async_initialize()

        # Create test signals with different scan types
        now = datetime.now(UTC)
        signals = [
            Signal(
                signal_id="signal_tech_001",
                symbol="TEST",
                signal_type="BUY",
                strength=0.8,
                timestamp=now,
                indicators={"rsi": 30.0},
                confidence=0.9,
                metadata={"scan_type": "technical", "source": "test"},
            ),
            Signal(
                signal_id="signal_fund_001",
                symbol="TEST",
                signal_type="SELL",
                strength=0.7,
                timestamp=now,
                indicators={"pe_ratio": 25.0},
                confidence=0.85,
                metadata={"scan_type": "fundamental", "source": "test"},
            ),
        ]

        # Store signals using sync method
        for signal in signals:
            temp_db.create_signal(signal)

        # Test async signal retrieval with scan type filter
        retrieved_signals = await temp_db.async_get_latest_signals(
            "TEST", limit=10, scan_type="technical"
        )
        assert len(retrieved_signals) == 1
        assert retrieved_signals[0].signal_id == "signal_tech_001"

    async def test_async_update_trade(self, temp_db):
        """Test async trade update."""
        if not AIOSQLITE_AVAILABLE:
            pytest.skip("aiosqlite not available")

        # Initialize async pool
        await temp_db.async_initialize()

        # Create test trade
        now = datetime.now(UTC)
        trade = Trade(
            trade_id="test_trade_001",
            symbol="TEST",
            quantity=10,
            entry_price=100.0,
            exit_price=None,
            entry_time=now,
            exit_time=None,
            transaction_type="BUY",
            product_type="MIS",
            pnl=None,
            status="OPEN",
            strategy="test_strategy",
        )

        # Store trade using sync method
        temp_db.create_trade(trade)

        # Update trade
        updated_trade = Trade(
            trade_id="test_trade_001",
            symbol="TEST",
            quantity=10,
            entry_price=100.0,
            exit_price=105.0,
            entry_time=now,
            exit_time=now,
            transaction_type="BUY",
            product_type="MIS",
            pnl=50.0,
            status="COMPLETED",
            strategy="test_strategy",
        )

        # Test async trade update
        result = await temp_db.async_update_trade(updated_trade)
        assert result is True

        # Verify trade was updated
        retrieved_trade = temp_db.get_trade("test_trade_001")
        assert retrieved_trade is not None
        assert retrieved_trade.status == "COMPLETED"
        assert retrieved_trade.pnl == 50.0

    async def test_async_update_order_status(self, temp_db):
        """Test async order status update."""
        if not AIOSQLITE_AVAILABLE:
            pytest.skip("aiosqlite not available")

        # Initialize async pool
        await temp_db.async_initialize()

        # Test async order status update (no existing order, should return False)
        result = await temp_db.async_update_order_status(
            "nonexistent_order", "COMPLETED"
        )
        assert result is False

    async def test_async_get_trade(self, temp_db):
        """Test async trade retrieval."""
        if not AIOSQLITE_AVAILABLE:
            pytest.skip("aiosqlite not available")

        # Initialize async pool
        await temp_db.async_initialize()

        # Create test trade
        now = datetime.now(UTC)
        trade = Trade(
            trade_id="test_trade_002",
            symbol="TEST",
            quantity=5,
            entry_price=95.0,
            exit_price=None,
            entry_time=now,
            exit_time=None,
            transaction_type="BUY",
            product_type="MIS",
            pnl=None,
            status="OPEN",
            strategy="test_strategy",
        )

        # Store trade using sync method
        temp_db.create_trade(trade)

        # Test async trade retrieval
        retrieved_trade = await temp_db.async_get_trade("test_trade_002")
        assert retrieved_trade is not None
        assert retrieved_trade.trade_id == "test_trade_002"
        assert retrieved_trade.symbol == "TEST"

        # Test async trade retrieval for nonexistent trade
        nonexistent_trade = await temp_db.async_get_trade("nonexistent_trade")
        assert nonexistent_trade is None

    async def test_async_log_audit(self, temp_db):
        """Test async audit logging."""
        if not AIOSQLITE_AVAILABLE:
            pytest.skip("aiosqlite not available")

        # Initialize async pool
        await temp_db.async_initialize()

        # Test async audit logging
        await temp_db._async_log_audit(
            action="TEST",
            entity_type="test_entity",
            entity_id="test_id_001",
            user="test_user",
            metadata={"test_key": "test_value"},
            previous_state={"old": "state"},
            new_state={"new": "state"},
        )

        # Verify audit log was created
        assert temp_db.audit_log_path.exists()
        with temp_db.audit_log_path.open("r", encoding="utf-8") as f:
            lines = f.readlines()
            assert len(lines) >= 1

        # Verify audit entry was stored in database
        conn = temp_db._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM audit_log WHERE entity_id = ?", ("test_id_001",)
        )
        count = cursor.fetchone()[0]
        conn.close()
        assert count == 1

    async def test_async_methods_without_async_pool(self, temp_db):
        """Test async methods when async pool is not available."""
        if AIOSQLITE_AVAILABLE:
            # Temporarily disable async pool for this test
            temp_db._async_pool = None

            # Create test signal
            signal = Signal(
                signal_id="test_signal_003",
                symbol="TEST",
                signal_type="BUY",
                strength=0.8,
                timestamp=datetime.now(UTC),
                indicators={"rsi": 30.0},
                confidence=0.9,
                metadata={"scan_type": "technical", "source": "test"},
            )

            # Test async signal creation (should use fallback)
            result = await temp_db.async_create_signal(signal)
            assert result is True

            # Verify signal was created
            signals = temp_db.get_latest_signals("TEST", limit=1)
            assert len(signals) == 1

    async def test_async_methods_without_aiosqlite(self, temp_db):
        """Test async methods when aiosqlite is not available."""
        if AIOSQLITE_AVAILABLE:
            # Temporarily disable aiosqlite for this test
            with patch("loats.database_async_additions.AIOSQLITE_AVAILABLE", False):
                # Create test signal
                signal = Signal(
                    signal_id="test_signal_004",
                    symbol="TEST",
                    signal_type="BUY",
                    strength=0.8,
                    timestamp=datetime.now(UTC),
                    indicators={"rsi": 30.0},
                    confidence=0.9,
                    metadata={"scan_type": "technical", "source": "test"},
                )

                # Test async signal creation (should use fallback)
                result = await temp_db.async_create_signal(signal)
                assert result is True

    async def test_async_audit_log_failure(self, temp_db):
        """Test async audit log failure handling."""
        if not AIOSQLITE_AVAILABLE:
            pytest.skip("aiosqlite not available")

        # Initialize async pool
        await temp_db.async_initialize()

        # Mock the audit log file write to fail
        original_open = Path.open

        def failing_open(*args, **kwargs):
            if "test_audit.jsonl" in str(args[0]):
                raise OSError("Simulated file write failure")
            return original_open(*args, **kwargs)

        # Test that audit log failure is handled properly
        with patch("pathlib.Path.open", side_effect=failing_open):
            with pytest.raises(RuntimeError, match="Failed to write audit log entry"):
                await temp_db._async_log_audit(
                    action="TEST",
                    entity_type="test_entity",
                    entity_id="test_id_002",
                    user="test_user",
                )

    async def test_core_async_create_signal(self, temp_db):
        """Test the core async signal creation method directly."""
        if not AIOSQLITE_AVAILABLE:
            pytest.skip("aiosqlite not available")

        # Initialize async pool
        await temp_db.async_initialize()

        # Create test signal
        signal = Signal(
            signal_id="test_core_signal_001",
            symbol="CORE",
            signal_type="BUY",
            strength=0.85,
            timestamp=datetime.now(UTC),
            indicators={"rsi": 25.0, "macd": 2.0},
            confidence=0.95,
            metadata={"scan_type": "core_test", "source": "test"},
        )

        # Test the core async method directly
        result = await temp_db._async_create_signal(signal)
        assert result is True

        # Verify signal was created
        signals = temp_db.get_latest_signals("CORE", limit=1)
        assert len(signals) == 1
        assert signals[0].signal_id == "test_core_signal_001"

    async def test_core_async_store_historical_data(self, temp_db):
        """Test the core async historical data storage method directly."""
        if not AIOSQLITE_AVAILABLE:
            pytest.skip("aiosqlite not available")

        # Initialize async pool
        await temp_db.async_initialize()

        # Create test historical data
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

        # Test the core async method directly
        result = await temp_db._async_store_historical_data(historical_data)
        assert result is True

        # Verify data was stored
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

        # Initialize async pool
        await temp_db.async_initialize()

        # Create test quote data
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

        # Test the core async method directly
        result = await temp_db._async_store_quote(quote)
        assert result is True

        # Verify data was stored
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

        # Initialize async pool
        await temp_db.async_initialize()

        # Create test position
        now = datetime.now(UTC)
        position = Position(
            symbol="CORE",
            quantity=15,
            average_price=105.0,
            last_price=108.0,
            pnl=45.0,
            product_type="MIS",
            buy_quantity=15,
            sell_quantity=0,
            timestamp=now,
        )

        # Test the core async method directly
        result = await temp_db._async_store_position(position)
        assert result is True

        # Verify data was stored
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

        # Initialize async pool
        await temp_db.async_initialize()

        # Create test funds data
        now = datetime.now(UTC)
        funds = FundsData(
            available_cash=60000.0,
            utilized_margin=25000.0,
            available_margin=35000.0,
            total_equity=85000.0,
            timestamp=now,
        )

        # Test the core async method directly
        result = await temp_db._async_store_funds(funds)
        assert result is True

        # Verify data was stored
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

        # Initialize async pool
        await temp_db.async_initialize()

        # Create test signals using sync method
        base_time = datetime.now(UTC)
        signals = [
            Signal(
                signal_id=f"core_signal_{i:03d}",
                symbol="CORE",
                signal_type="BUY" if i % 2 == 0 else "SELL",
                strength=0.75 + i * 0.03,
                timestamp=base_time - timedelta(seconds=15 - i),
                indicators={"rsi": 25.0 + i * 3, "macd": 1.2 + i * 0.3},
                confidence=0.85 + i * 0.01,
                metadata={"scan_type": "core_test", "source": "test"},
            )
            for i in range(4)
        ]

        # Store signals using sync method
        for signal in signals:
            temp_db.create_signal(signal)

        # Test the core async method directly
        retrieved_signals = await temp_db._async_get_latest_signals("CORE", limit=3)
        assert len(retrieved_signals) == 3

        # Verify the signals are the most recent ones
        signal_ids = {signal.signal_id for signal in retrieved_signals}
        assert "core_signal_003" in signal_ids
        assert "core_signal_002" in signal_ids
        assert "core_signal_001" in signal_ids

    async def test_core_async_update_trade(self, temp_db):
        """Test the core async trade update method directly."""
        if not AIOSQLITE_AVAILABLE:
            pytest.skip("aiosqlite not available")

        # Initialize async pool
        await temp_db.async_initialize()

        # Create test trade using sync method
        now = datetime.now(UTC)
        trade = Trade(
            trade_id="core_trade_001",
            symbol="CORE",
            quantity=20,
            entry_price=105.0,
            exit_price=None,
            entry_time=now,
            exit_time=None,
            transaction_type="BUY",
            product_type="MIS",
            pnl=None,
            status="OPEN",
            strategy="core_strategy",
        )

        temp_db.create_trade(trade)

        # Update trade
        updated_trade = Trade(
            trade_id="core_trade_001",
            symbol="CORE",
            quantity=20,
            entry_price=105.0,
            exit_price=110.0,
            entry_time=now,
            exit_time=now,
            transaction_type="BUY",
            product_type="MIS",
            pnl=100.0,
            status="COMPLETED",
            strategy="core_strategy",
        )

        # Test the core async method directly
        result = await temp_db._async_update_trade(updated_trade)
        assert result is True

        # Verify trade was updated
        retrieved_trade = temp_db.get_trade("core_trade_001")
        assert retrieved_trade is not None
        assert retrieved_trade.status == "COMPLETED"
        assert retrieved_trade.pnl == 100.0

    async def test_core_async_update_order_status(self, temp_db):
        """Test the core async order status update method directly."""
        if not AIOSQLITE_AVAILABLE:
            pytest.skip("aiosqlite not available")

        # Initialize async pool
        await temp_db.async_initialize()

        # Create test order using sync method
        now = datetime.now(UTC)
        order = Order(
            order_id="core_order_001",
            symbol="CORE",
            quantity=10,
            order_type="LIMIT",
            price=108.0,
            trigger_price=None,
            variety="regular",
            transaction_type="BUY",
            product_type="MIS",
            status="OPEN",
            timestamp=now,
            filled_quantity=0,
            average_price=108.0,  # Fixed: must be > 0
            stop_loss=None,
            take_profit=None,
            trailing_stop_loss=None,
            idempotency_key="core_test_key_001",
        )

        temp_db.store_order(order)

        # Test the core async method directly
        result = await temp_db._async_update_order_status("core_order_001", "COMPLETED")
        assert result is True

        # Verify order status was updated
        updated_order = temp_db.get_order("core_order_001")
        assert updated_order is not None
        assert updated_order.status == "COMPLETED"

    async def test_core_async_get_trade(self, temp_db):
        """Test the core async trade retrieval method directly."""
        if not AIOSQLITE_AVAILABLE:
            pytest.skip("aiosqlite not available")

        # Initialize async pool
        await temp_db.async_initialize()

        # Create test trade using sync method
        now = datetime.now(UTC)
        trade = Trade(
            trade_id="core_trade_002",
            symbol="CORE",
            quantity=15,
            entry_price=108.0,
            exit_price=None,
            entry_time=now,
            exit_time=None,
            transaction_type="BUY",
            product_type="MIS",
            pnl=None,
            status="OPEN",
            strategy="core_strategy",
        )

        temp_db.create_trade(trade)

        # Test the core async method directly
        retrieved_trade = await temp_db.async_get_trade("core_trade_002")
        assert retrieved_trade is not None
        assert retrieved_trade.trade_id == "core_trade_002"
        assert retrieved_trade.symbol == "CORE"

        # Test retrieval of nonexistent trade
        nonexistent_trade = await temp_db.async_get_trade("nonexistent_core_trade")
        assert nonexistent_trade is None

    async def test_core_async_log_audit(self, temp_db):
        """Test the core async audit logging method directly."""
        if not AIOSQLITE_AVAILABLE:
            pytest.skip("aiosqlite not available")

        # Initialize async pool
        await temp_db.async_initialize()

        # Test the core async audit logging method directly
        await temp_db._async_log_audit(
            action="CORE_TEST",
            entity_type="core_entity",
            entity_id="core_id_001",
            user="core_user",
            metadata={"core_key": "core_value"},
            previous_state={"old_core": "state"},
            new_state={"new_core": "state"},
        )

        # Verify audit log was created
        assert temp_db.audit_log_path.exists()
        with temp_db.audit_log_path.open("r", encoding="utf-8") as f:
            lines = f.readlines()
            assert len(lines) >= 1

        # Verify audit entry was stored in database
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

        # Initialize async pool
        await temp_db.async_initialize()

        # Verify pool was created
        assert hasattr(temp_db, "_async_pool")
        assert temp_db._async_pool is not None

        # Create some test data to ensure connections are used
        signal = Signal(
            signal_id="pool_test_signal",
            symbol="POOL",
            signal_type="BUY",
            strength=0.8,
            timestamp=datetime.now(UTC),
            indicators={"rsi": 30.0},
            confidence=0.9,
        )

        result = await temp_db.async_create_signal(signal)
        assert result is True

        # Test proper cleanup
        await temp_db.async_close_all()

        # Verify pool was closed
        assert temp_db._async_pool is None

        # Verify no warnings about event loop being closed
        # (This would be caught by pytest warnings if it occurred)


if __name__ == "__main__":
    # Run the tests
    unittest.main(verbosity=2)
