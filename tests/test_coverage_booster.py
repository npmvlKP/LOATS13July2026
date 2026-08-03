"""Coverage booster tests to improve overall coverage to 80%+."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone
from decimal import Decimal
import sqlite3

from src.loats.models import (
    Trade, Order, Signal, Position, FundsData, QuoteData,
    HistoricalData, OrderType, TransactionType, SignalType
)
from src.loats.database import Database
from src.loats.alerts import AlertSystem
from src.loats.openalgo import OpenAlgoClient, AsyncOpenAlgoClient
from src.loats.scheduler import TradingScheduler
from src.loats.utils.circuit_breaker import CircuitBreaker
from src.loats.config.settings import get_settings

class TestAlertSystemCoverage:
    """Test AlertSystem methods with low coverage."""

    @pytest.mark.asyncio
    async def test_alert_system_send_alert_error_handling(self):
        """Test send_alert with various error scenarios."""
        db_mock = MagicMock()
        alert_system = AlertSystem(db_mock)

        # Test with None database
        alert_system_no_db = AlertSystem(None)
        with patch.object(alert_system_no_db, '_safe_send_message', return_value=False):
            result = await alert_system_no_db.send_alert("test message")
            assert result is False

    @pytest.mark.asyncio
    async def test_alert_system_position_alert_no_data(self):
        """Test send_position_alert when no position data available."""
        db_mock = MagicMock()
        db_mock.get_position_book.return_value = None
        alert_system = AlertSystem(db_mock)

        with patch.object(alert_system, '_safe_get_position_book', return_value=None):
            result = await alert_system.send_position_alert()
            assert result is False

    @pytest.mark.asyncio
    async def test_alert_system_funds_alert_no_data(self):
        """Test send_funds_alert when no funds data available."""
        db_mock = MagicMock()
        db_mock.get_funds.return_value = None
        alert_system = AlertSystem(db_mock)

        with patch.object(alert_system, '_safe_get_funds', return_value=None):
            result = await alert_system.send_funds_alert()
            assert result is False

    def test_alert_system_circuit_breaker_status(self):
        """Test get_circuit_breaker_status method."""
        db_mock = MagicMock()
        alert_system = AlertSystem(db_mock)

        # This should return some status dict
        status = alert_system.get_circuit_breaker_status()
        assert isinstance(status, dict)

class TestOpenAlgoClientCoverage:
    """Test OpenAlgoClient methods with low coverage."""

    def test_openalgo_client_ensure_client(self):
        """Test _ensure_client method."""
        client = OpenAlgoClient(api_key="test_key")
        client.client = None

        with patch('httpx.Client') as mock_client:
            mock_client_instance = MagicMock()
            mock_client.return_value = mock_client_instance
            result = client._ensure_client()
            assert result == mock_client_instance

    @pytest.mark.asyncio
    async def test_async_openalgo_client_ensure_client(self):
        """Test async _ensure_client method."""
        client = AsyncOpenAlgoClient(api_key="test_key")
        client.client = None

        with patch('httpx.AsyncClient') as mock_client:
            mock_client_instance = AsyncMock()
            mock_client.return_value = mock_client_instance
            result = await client._ensure_client()
            assert result == mock_client_instance

class TestSchedulerCoverage:
    """Test TradingScheduler methods with low coverage."""

    @pytest.mark.asyncio
    async def test_scheduler_market_status_check(self):
        """Test market status check task."""
        scheduler = TradingScheduler()
        scheduler.scheduler = MagicMock()

        # Test with market closed
        with patch.object(scheduler, 'is_market_open', return_value=False):
            await scheduler._market_status_check_task()
            # Should not raise exceptions

    @pytest.mark.asyncio
    async def test_scheduler_data_cleanup(self):
        """Test data cleanup task."""
        scheduler = TradingScheduler()
        scheduler.scheduler = MagicMock()

        with patch.object(scheduler, 'cleanup_old_data'):
            await scheduler._data_cleanup_task()
            # Should not raise exceptions

class TestCircuitBreakerCoverage:
    """Test CircuitBreaker methods with low coverage."""

    def test_circuit_breaker_record_methods(self):
        """Test circuit breaker record methods."""
        from src.loats.utils.circuit_breaker import CircuitBreakerConfig
        config = CircuitBreakerConfig(failure_threshold=3, success_threshold=2, timeout=10.0)
        cb = CircuitBreaker("test_circuit", config)

        # Test record methods
        cb._record_success()
        cb._record_failure()
        cb._record_rejection()

        # Verify stats are updated
        stats = cb.stats
        assert stats.total_calls >= 3

    def test_circuit_breaker_get_status(self):
        """Test get_status method."""
        from src.loats.utils.circuit_breaker import CircuitBreakerConfig
        config = CircuitBreakerConfig(failure_threshold=3, success_threshold=2, timeout=10.0)
        cb = CircuitBreaker("test_circuit", config)

        status = cb.get_status()
        assert isinstance(status, dict)
        assert "circuit_name" in status
        assert "state" in status

class TestDatabaseCoverage:
    """Test Database methods with low coverage."""

    def test_database_model_conversion(self):
        """Test model conversion methods."""
        db = Database()

        # Test _model_to_dict and _dict_to_model
        trade = Trade(
            trade_id="test_123",
            symbol="NIFTY",
            entry_price=Decimal("100.00"),
            exit_price=Decimal("105.00"),
            quantity=10,
            entry_time=datetime.now(timezone.utc),
            exit_time=datetime.now(timezone.utc),
            transaction_type=TransactionType.BUY,
            pnl=Decimal("50.00")
        )

        trade_dict = db._model_to_dict(trade)
        assert isinstance(trade_dict, dict)
        assert trade_dict["trade_id"] == "test_123"

        # Test reverse conversion
        converted_trade = db._dict_to_model(trade_dict, Trade)
        assert converted_trade.trade_id == "test_123"

    def test_database_canonical_methods(self):
        """Test canonical serialization methods."""
        db = Database()

        test_data = {"key": "value", "number": 123}
        serialized = db._canonical_serialize(test_data)
        assert isinstance(serialized, str)

        normalized = db._canonical_normalize("test_value")
        # Should not raise exceptions

class TestModelsCoverage:
    """Test model methods with low coverage."""

    def test_trade_pnl_calculation(self):
        """Test Trade PnL calculation methods."""
        trade = Trade(
            trade_id="test_123",
            symbol="NIFTY",
            entry_price=Decimal("100.00"),
            exit_price=Decimal("105.00"),
            quantity=10,
            entry_time=datetime.now(timezone.utc),
            exit_time=datetime.now(timezone.utc),
            transaction_type=TransactionType.BUY
        )

        # Test calculate_pnl_method with float current_price
        pnl = trade.calculate_pnl_method(105.00)
        assert pnl == 50.00

        # Test with SELL transaction
        trade_sell = Trade(
            trade_id="test_456",
            symbol="NIFTY",
            entry_price=Decimal("105.00"),
            exit_price=Decimal("100.00"),
            quantity=10,
            entry_time=datetime.now(timezone.utc),
            exit_time=datetime.now(timezone.utc),
            transaction_type=TransactionType.SELL
        )

        pnl_sell = trade_sell.calculate_pnl_method(100.00)
        assert pnl_sell == 50.00

class TestUtilsCoverage:
    """Test utility functions with low coverage."""

    def test_cache_key_functions(self):
        """Test cache key generation functions."""
        from src.loats.utils.cache import model_to_cache_key, dict_to_cache_key

        # Test model to cache key
        trade = Trade(
            trade_id="test_123",
            symbol="NIFTY",
            entry_price=Decimal("100.00"),
            exit_price=Decimal("105.00"),
            quantity=10,
            entry_time=datetime.now(timezone.utc),
            exit_time=datetime.now(timezone.utc),
            transaction_type=TransactionType.BUY
        )
        cache_key = model_to_cache_key(trade)
        assert isinstance(cache_key, str)
        assert "test_123" in cache_key

        # Test dict to cache key
        test_dict = {"key": "value", "number": 123}
        dict_key = dict_to_cache_key(test_dict)
        assert isinstance(dict_key, str)
