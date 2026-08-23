"""Comprehensive tests for the trading strategy core implementation."""

import datetime
import os
from collections.abc import Generator
from typing import Any

import pytest

from src.loats.config import get_settings
from src.loats.models import (
    Signal,
    Trade,
    Order,
    OrderType,
    OrderVariety,
    TransactionType,
    ProductType,
    OrderStatus,
)
from src.loats.trading_strategy.core import TradingStrategyCore, StrategyMode


@pytest.fixture
def setup_env() -> Generator[None, None, None]:
    """Set up environment for testing."""
    # Set required environment variable
    os.environ["OPENALGO_API_KEY"] = "test_key"
    yield
    # Clean up
    del os.environ["OPENALGO_API_KEY"]


@pytest.fixture
def trading_strategy() -> TradingStrategyCore:
    """Create a fresh trading strategy instance for each test."""
    return TradingStrategyCore()


def test_trading_strategy_initialization(trading_strategy: TradingStrategyCore) -> None:
    """Test that trading strategy initializes correctly."""
    assert trading_strategy.mode == StrategyMode.ANALYZE
    assert len(trading_strategy.active_trades) == 0
    assert len(trading_strategy.pending_orders) == 0
    assert trading_strategy.max_ops == get_settings().max_ops
    assert trading_strategy.max_daily_orders == get_settings().max_daily_orders
    assert trading_strategy.nifty_lot_size == get_settings().nifty_lot_size


def test_set_mode(trading_strategy: TradingStrategyCore) -> None:
    """Test setting different strategy modes."""
    trading_strategy.set_mode(StrategyMode.LIVE)
    assert trading_strategy.mode == StrategyMode.LIVE

    trading_strategy.set_mode(StrategyMode.BACKTEST)
    assert trading_strategy.mode == StrategyMode.BACKTEST

    trading_strategy.set_mode(StrategyMode.ANALYZE)
    assert trading_strategy.mode == StrategyMode.ANALYZE


def test_validate_trade_basic(trading_strategy: TradingStrategyCore) -> None:
    """Test basic trade validation."""
    trade = Trade(
        trade_id="test_trade_1",
        symbol="NIFTY",
        entry_price=100.0,
        quantity=25,
        entry_time=datetime.datetime.now(datetime.UTC),
        status="PENDING",
        metadata={}
    )

    is_valid, validation = trading_strategy.validate_trade(trade)
    assert is_valid is True
    assert len(validation["reasons"]) == 0
    assert "Running in ANALYZE mode" in validation["warnings"]


def test_validate_trade_position_limits(trading_strategy: TradingStrategyCore) -> None:
    """Test position limit validation."""
    settings = get_settings()

    # Fill up to position limit
    for i in range(settings.max_nifty_positions):
        trade = Trade(
            trade_id=f"test_trade_{i}",
            symbol="NIFTY",
            entry_price=100.0,
            quantity=25,
            entry_time=datetime.datetime.now(datetime.UTC),
            status="ACTIVE",
            metadata={}
        )
        trading_strategy.active_trades[f"test_trade_{i}"] = trade

    # Try to add one more - should fail
    new_trade = Trade(
        trade_id="test_trade_new",
        symbol="NIFTY",
        entry_price=100.0,
        quantity=25,
        entry_time=datetime.datetime.now(datetime.UTC),
        status="PENDING",
        metadata={}
    )

    is_valid, validation = trading_strategy.validate_trade(new_trade)
    assert is_valid is False
    assert "Position limit reached" in validation["reasons"][0]


def test_execute_trade_in_analyze_mode(trading_strategy: TradingStrategyCore) -> None:
    """Test trade execution in ANALYZE mode."""
    signal = Signal(
        symbol="NIFTY",
        signal_type="BUY",
        strength=0.8,
        timestamp=datetime.datetime.now(datetime.UTC),
        price=100.0,
        metadata={"strategy": "test"}
    )

    success, trade = trading_strategy.execute_trade(signal)
    assert success is False
    assert trade is None


def test_execute_trade_in_live_mode(trading_strategy: TradingStrategyCore) -> None:
    """Test trade execution in LIVE mode."""
    trading_strategy.set_mode(StrategyMode.LIVE)

    signal = Signal(
        symbol="NIFTY",
        signal_type="BUY",
        strength=0.8,
        timestamp=datetime.datetime.now(datetime.UTC),
        price=100.0,
        metadata={"strategy": "test"}
    )

    success, trade = trading_strategy.execute_trade(signal)
    assert success is True
    assert trade is not None
    assert trade.symbol == "NIFTY"
    assert trade.signal_type == "BUY"
    assert trade.entry_price == 100.0
    assert trade.quantity == trading_strategy.nifty_lot_size
    assert trade.status == "PENDING"
    assert trade.trade_id.startswith("trade_")

    # Verify trade was added to active trades
    assert trade.trade_id in trading_strategy.active_trades


def test_manage_position_close(trading_strategy: TradingStrategyCore) -> None:
    """Test closing a position."""
    # Create a trade first
    trade = Trade(
        trade_id="test_trade_1",
        symbol="NIFTY",
        signal_type="BUY",
        entry_price=100.0,
        quantity=25,
        entry_time=datetime.datetime.now(datetime.UTC),
        status="ACTIVE",
        metadata={}
    )
    trading_strategy.active_trades["test_trade_1"] = trade

    # Close the position
    result = trading_strategy.manage_position("test_trade_1", "CLOSE")
    assert result is True
    assert trading_strategy.active_trades["test_trade_1"].status == "CLOSED"
    assert hasattr(trading_strategy.active_trades["test_trade_1"], "exit_time")


def test_manage_position_modify(trading_strategy: TradingStrategyCore) -> None:
    """Test modifying a position."""
    settings = get_settings()

    # Create a trade first
    trade = Trade(
        trade_id="test_trade_1",
        symbol="NIFTY",
        entry_price=100.0,
        quantity=25,
        entry_time=datetime.datetime.now(datetime.UTC),
        status="ACTIVE",
        metadata={"modification_count": 0}
    )
    trading_strategy.active_trades["test_trade_1"] = trade

    # Modify the position multiple times
    for i in range(settings.max_modifications - 1):
        result = trading_strategy.manage_position("test_trade_1", "MODIFY")
        assert result is True
        assert trading_strategy.active_trades["test_trade_1"].metadata["modification_count"] == i + 1

    # Try to modify one more time - should fail
    result = trading_strategy.manage_position("test_trade_1", "MODIFY")
    assert result is False


def test_manage_position_invalid_action(trading_strategy: TradingStrategyCore) -> None:
    """Test invalid position management action."""
    result = trading_strategy.manage_position("nonexistent_trade", "INVALID")
    assert result is False


def test_get_active_trades(trading_strategy: TradingStrategyCore) -> None:
    """Test getting active trades."""
    # Add some trades
    for i in range(3):
        trade = Trade(
            trade_id=f"test_trade_{i}",
            symbol="NIFTY",
            signal_type="BUY",
            entry_price=100.0,
            quantity=25,
            entry_time=datetime.datetime.now(datetime.UTC),
            status="ACTIVE",
            metadata={}
        )
        trading_strategy.active_trades[f"test_trade_{i}"] = trade

    active_trades = trading_strategy.get_active_trades()
    assert len(active_trades) == 3
    assert all(trade.trade_id.startswith("test_trade_") for trade in active_trades)


def test_get_trade_status(trading_strategy: TradingStrategyCore) -> None:
    """Test getting trade status."""
    # Add a trade
    trade = Trade(
        trade_id="test_trade_1",
        symbol="NIFTY",
        signal_type="BUY",
        entry_price=100.0,
        quantity=25,
        entry_time=datetime.datetime.now(datetime.UTC),
        status="ACTIVE",
        metadata={"modification_count": 2}
    )
    trading_strategy.active_trades["test_trade_1"] = trade

    status = trading_strategy.get_trade_status("test_trade_1")
    assert status["status"] == "ACTIVE"
    assert status["trade_id"] == "test_trade_1"
    assert status["symbol"] == "NIFTY"
    assert status["entry_price"] == 100.0
    assert status["modifications"] == 2

    # Test non-existent trade
    status = trading_strategy.get_trade_status("nonexistent")
    assert status["status"] == "NOT_FOUND"


def test_check_ops_limit(trading_strategy: TradingStrategyCore) -> None:
    """Test OPS limit checking."""
    settings = get_settings()

    # Should allow up to max_ops
    for i in range(settings.max_ops):
        order = Order(
            order_id=f"order_{i}",
            symbol="NIFTY",
            quantity=25,
            order_type=OrderType.LIMIT,
            price=100.0,
            variety=OrderVariety.REGULAR,
            transaction_type=TransactionType.BUY,
            product_type=ProductType.MIS,
            status=OrderStatus.OPEN,
            timestamp=datetime.datetime.now(datetime.UTC),
            filled_quantity=0
        )
        trading_strategy.pending_orders[f"order_{i}"] = order

    assert trading_strategy.check_ops_limit() is False

    # Clear and test with fewer orders
    trading_strategy.pending_orders.clear()
    for i in range(settings.max_ops - 1):
        order = Order(
            order_id=f"order_{i}",
            symbol="NIFTY",
            quantity=25,
            order_type=OrderType.LIMIT,
            price=100.0,
            variety=OrderVariety.REGULAR,
            transaction_type=TransactionType.BUY,
            product_type=ProductType.MIS,
            status=OrderStatus.OPEN,
            timestamp=datetime.datetime.now(datetime.UTC),
            filled_quantity=0
        )
        trading_strategy.pending_orders[f"order_{i}"] = order

    assert trading_strategy.check_ops_limit() is True


def test_get_strategy_metrics(trading_strategy: TradingStrategyCore) -> None:
    """Test getting strategy metrics."""
    settings = get_settings()

    # Add some trades and orders
    for i in range(2):
        trade = Trade(
            trade_id=f"test_trade_{i}",
            symbol="NIFTY",
            entry_price=100.0,
            quantity=25,
            entry_time=datetime.datetime.now(datetime.UTC),
            status="ACTIVE",
            metadata={}
        )
        trading_strategy.active_trades[f"test_trade_{i}"] = trade

    for i in range(1):
        order = Order(
            order_id=f"order_{i}",
            symbol="NIFTY",
            quantity=25,
            order_type=OrderType.LIMIT,
            price=100.0,
            variety=OrderVariety.REGULAR,
            transaction_type=TransactionType.BUY,
            product_type=ProductType.MIS,
            status=OrderStatus.OPEN,
            timestamp=datetime.datetime.now(datetime.UTC),
            filled_quantity=0
        )
        trading_strategy.pending_orders[f"order_{i}"] = order

    metrics = trading_strategy.get_strategy_metrics()
    assert metrics["active_trades"] == 2
    assert metrics["pending_orders"] == 1
    assert metrics["mode"] == "ANALYZE"
    assert metrics["max_ops"] == settings.max_ops
    assert metrics["max_daily_orders"] == settings.max_daily_orders
    assert metrics["current_exposure"] == 5000.0  # 2 trades * 25 * 100
    assert metrics["max_exposure"] == float(settings.max_total_exposure)


def test_reset(trading_strategy: TradingStrategyCore) -> None:
    """Test resetting strategy state."""
    # Add some trades and orders
    trade = Trade(
        trade_id="test_trade_1",
        symbol="NIFTY",
        entry_price=100.0,
        quantity=25,
        entry_time=datetime.datetime.now(datetime.UTC),
        status="ACTIVE",
        metadata={}
    )
    trading_strategy.active_trades["test_trade_1"] = trade

    order = Order(
        order_id="order_1",
        symbol="NIFTY",
        quantity=25,
        order_type=OrderType.LIMIT,
        price=100.0,
        variety=OrderVariety.REGULAR,
        transaction_type=TransactionType.BUY,
        product_type=ProductType.MIS,
        status=OrderStatus.OPEN,
        timestamp=datetime.datetime.now(datetime.UTC),
        filled_quantity=0
    )
    trading_strategy.pending_orders["order_1"] = order

    trading_strategy.strategy_state["test_key"] = "test_value"

    # Reset
    trading_strategy.reset()

    assert len(trading_strategy.active_trades) == 0
    assert len(trading_strategy.pending_orders) == 0
    assert len(trading_strategy.strategy_state) == 0


def test_update_market_data(trading_strategy: TradingStrategyCore) -> None:
    """Test updating market data."""
    market_data = {
        "NIFTY": {"price": 105.0, "volume": 1000000},
        "BANKNIFTY": {"price": 25000.0, "volume": 500000},
        "timestamp": datetime.datetime.now(datetime.UTC).isoformat()
    }

    trading_strategy.update_market_data(market_data)

    assert "market_data" in trading_strategy.strategy_state
    assert trading_strategy.strategy_state["market_data"] == market_data


def test_get_strategy_config(trading_strategy: TradingStrategyCore) -> None:
    """Test getting strategy configuration."""
    settings = get_settings()

    config = trading_strategy.get_strategy_config()

    assert config["mode"] == "ANALYZE"
    assert config["max_ops"] == settings.max_ops
    assert config["max_daily_orders"] == settings.max_daily_orders
    assert config["nifty_lot_size"] == settings.nifty_lot_size
    assert config["max_order_value"] == float(settings.max_order_value)
    assert config["max_total_exposure"] == float(settings.max_total_exposure)
    assert config["max_nifty_positions"] == settings.max_nifty_positions
    assert config["max_banknifty_positions"] == settings.max_banknifty_positions


def test_validate_cmp_compliance(trading_strategy: TradingStrategyCore) -> None:
    """Test CMP compliance validation."""
    settings = get_settings()

    # Create a trade that violates multiple CMP rules
    trade = Trade(
        trade_id="test_trade_1",
        symbol="NIFTY",
        entry_price=100.0,
        quantity=25,
        entry_time=datetime.datetime.now(datetime.UTC),
        status="PENDING",
        metadata={"modification_count": settings.max_modifications + 1}
    )

    # Fill up position limit
    for i in range(settings.max_nifty_positions):
        existing_trade = Trade(
            trade_id=f"existing_trade_{i}",
            symbol="NIFTY",
            entry_price=100.0,
            quantity=25,
            entry_time=datetime.datetime.now(datetime.UTC),
            status="ACTIVE",
            metadata={}
        )
        trading_strategy.active_trades[f"existing_trade_{i}"] = existing_trade

    # Fill up OPS limit
    for i in range(settings.max_ops):
        order = Order(
            order_id=f"order_{i}",
            symbol="NIFTY",
            quantity=25,
            order_type=OrderType.LIMIT,
            price=100.0,
            variety=OrderVariety.REGULAR,
            transaction_type=TransactionType.BUY,
            product_type=ProductType.MIS,
            status=OrderStatus.OPEN,
            timestamp=datetime.datetime.now(datetime.UTC),
            filled_quantity=0
        )
        trading_strategy.pending_orders[f"order_{i}"] = order

    # Validate - should fail all rules
    is_valid, validation = trading_strategy.validate_cmp_compliance(trade)

    assert is_valid is False
    assert len(validation["reasons"]) == 3  # Rule 7, 11, and 4 violations
    assert "CMP Rule 7 violation" in validation["reasons"][0]
    assert "CMP Rule 11 violation" in validation["reasons"][1]
    assert "CMP Rule 4 violation" in validation["reasons"][2]
    assert len(validation["cmp_rules_checked"]) == 3


def test_validate_cmp_compliance_pass(trading_strategy: TradingStrategyCore) -> None:
    """Test CMP compliance validation that should pass."""
    trade = Trade(
        trade_id="test_trade_1",
        symbol="NIFTY",
        signal_type="BUY",
        entry_price=100.0,
        quantity=25,
        entry_time=datetime.datetime.now(datetime.UTC),
        status="PENDING",
        metadata={"modification_count": 0}
    )

    is_valid, validation = trading_strategy.validate_cmp_compliance(trade)

    assert is_valid is True
    assert len(validation["reasons"]) == 0
    assert len(validation["cmp_rules_checked"]) == 3


def test_apply_cmp_trailing_stop_long(trading_strategy: TradingStrategyCore) -> None:
    """Test CMP-compliant trailing stop for long position."""
    trade = Trade(
        trade_id="test_trade_1",
        symbol="NIFTY",
        entry_price=100.0,
        quantity=25,
        entry_time=datetime.datetime.now(datetime.UTC),
        status="ACTIVE",
        metadata={},
        transaction_type=TransactionType.BUY
    )

    # Apply trailing stop with increasing prices
    config = trading_strategy.apply_cmp_trailing_stop(trade, 100.0)
    assert config["trigger_price"] == 98.0  # 2% initial stop
    assert config["trailing_distance"] == 2.0
    assert config["direction"] == "LONG"

    # Price moves up - should update trailing stop
    config = trading_strategy.apply_cmp_trailing_stop(trade, 105.0)
    assert config["trigger_price"] == 103.0  # 105 - 2

    # Original config should be updated
    assert trade.metadata['trailing_config']["trigger_price"] == 103.0


def test_apply_cmp_trailing_stop_short(trading_strategy: TradingStrategyCore) -> None:
    """Test CMP-compliant trailing stop for short position."""
    trade = Trade(
        trade_id="test_trade_1",
        symbol="NIFTY",
        entry_price=100.0,
        quantity=25,
        entry_time=datetime.datetime.now(datetime.UTC),
        status="ACTIVE",
        metadata={},
        transaction_type=TransactionType.SELL
    )

    # Apply trailing stop with decreasing prices
    config = trading_strategy.apply_cmp_trailing_stop(trade, 100.0)
    assert config["trigger_price"] == 98.0  # 2% initial stop
    assert config["trailing_distance"] == 2.0
    assert config["direction"] == "SHORT"

    # Price moves down - should update trailing stop
    config = trading_strategy.apply_cmp_trailing_stop(trade, 95.0)
    assert config["trigger_price"] == 97.0  # 95 + 2


def test_apply_cmp_trailing_stop_monotonic(trading_strategy: TradingStrategyCore) -> None:
    """Test monotonic ratcheting behavior."""
    trade = Trade(
        trade_id="test_trade_1",
        symbol="NIFTY",
        entry_price=100.0,
        quantity=25,
        entry_time=datetime.datetime.now(datetime.UTC),
        status="ACTIVE",
        metadata={},
        transaction_type=TransactionType.BUY
    )

    # Move price up
    config = trading_strategy.apply_cmp_trailing_stop(trade, 105.0)
    assert config["trigger_price"] == 103.0

    # Move price down - should NOT move stop down (monotonic ratchet)
    config = trading_strategy.apply_cmp_trailing_stop(trade, 102.0)
    assert config["trigger_price"] == 103.0  # Should stay at 103, not move down

    # Move price up further
    config = trading_strategy.apply_cmp_trailing_stop(trade, 110.0)
    assert config["trigger_price"] == 108.0  # Should move up to 108


def test_create_sl_m_order(trading_strategy: TradingStrategyCore) -> None:
    """Test SL-M order creation."""
    trade = Trade(
        trade_id="test_trade_1",
        symbol="NIFTY",
        entry_price=100.0,
        quantity=25,
        entry_time=datetime.datetime.now(datetime.UTC),
        status="ACTIVE",
        metadata={},
        transaction_type=TransactionType.BUY
    )

    # Apply trailing stop first
    trading_strategy.apply_cmp_trailing_stop(trade, 105.0)

    # Create SL-M order
    sl_m_order = trading_strategy.create_sl_m_order(trade)

    assert sl_m_order.order_id.startswith("slm_test_trade_1_")
    assert sl_m_order.symbol == "NIFTY"
    assert sl_m_order.quantity == 25
    assert sl_m_order.order_type == OrderType.SL_M
    assert sl_m_order.price == 103.0  # trigger price from trailing stop
    assert sl_m_order.trigger_price == 103.0
    assert sl_m_order.trailing_stop_loss == 103.0
    assert "cmp_rule" in sl_m_order.metadata
    assert sl_m_order.metadata["cmp_rule"] == "Rule 12"
    assert "created_at" in sl_m_order.metadata

    # Verify order was added to pending orders
    assert sl_m_order.order_id in trading_strategy.pending_orders


def test_create_sl_m_order_without_trailing_config(trading_strategy: TradingStrategyCore) -> None:
    """Test SL-M order creation without trailing config."""
    trade = Trade(
        trade_id="test_trade_1",
        symbol="NIFTY",
        signal_type="BUY",
        entry_price=100.0,
        quantity=25,
        entry_time=datetime.datetime.now(datetime.UTC),
        status="ACTIVE",
        metadata={}
    )

    # Try to create SL-M order without trailing config
    with pytest.raises(ValueError, match="Trade must have trailing_config"):
        trading_strategy.create_sl_m_order(trade)


if __name__ == "__main__":
    # Run the tests
    pytest.main([__file__, "-v"])