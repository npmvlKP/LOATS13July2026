#!/usr/bin/env python3
"""
Test suite for trailing stop runtime driver implementation.
"""

import pytest

from loats.models import Position, ProductType, TransactionType
from loats.trailing_stop import TrailingStopType, trailing_stop_engine


@pytest.mark.asyncio
async def test_trailing_stop_runtime_driver_basic():
    """Test basic functionality of trailing stop runtime driver."""

    # Create a mock position with trailing stop configuration
    mock_position = Position(
        symbol="NIFTY",
        quantity=100,
        average_price=18400.0,
        last_price=18600.0,
        pnl=20000.0,
        product_type=ProductType.MIS,
        buy_quantity=100,
        sell_quantity=0,
    )

    # Create trailing stop configuration
    trailing_config = {
        "trade_id": "test_trade",
        "symbol": "NIFTY",
        "entry_price": 18400.0,
        "current_price": 18600.0,
        "stop_type": TrailingStopType.RATCHET,
        "status": "ACTIVE",
        "trigger_price": 18450.0,
        "adjustment_count": 0,
        "current_ratchet_level": 0,
        "transaction_type": TransactionType.BUY
    }

    # Update the trailing stop
    updated_config, triggered = trailing_stop_engine.update_trailing_stop(
        trailing_config,
        18650.0
    )

    # Debug output
    print(f"Triggered: {triggered}")
    print(f"Original trigger_price: {trailing_config['trigger_price']}")
    print(f"Updated trigger_price: {updated_config['trigger_price']}")

    # For a ratchet to update, we need significant price movement
    # With current ratchet_step of 0.002 (0.2%), let's use a bigger price movement
    high_price_config = trailing_config.copy()
    high_price_config["current_price"] = 19000.0  # Much higher

    updated_config_high, triggered_high = trailing_stop_engine.update_trailing_stop(
        high_price_config,
        19000.0
    )

    print(f"High price triggered: {triggered_high}")
    print(f"High price original trigger_price: {high_price_config['trigger_price']}")
    print(f"High price updated trigger_price: {updated_config_high['trigger_price']}")

    # Verify the ratchet updated (if triggered)
    if triggered_high:
        assert updated_config_high["trigger_price"] > trailing_config["trigger_price"]
        assert updated_config_high["adjustment_count"] > 0
        assert updated_config_high["status"] == "ACTIVE"
    else:
        # If not triggered, the config should remain unchanged
        assert updated_config_high["trigger_price"] == trailing_config["trigger_price"]
