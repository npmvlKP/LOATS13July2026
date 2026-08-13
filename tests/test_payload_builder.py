#!/usr/bin/env python3
"""
Comprehensive test suite for payload_builder.py module.

This test file covers all payload building functions to address the 14.8% coverage issue.
"""

import unittest
from enum import Enum
from unittest.mock import patch

from loats.models import (
    OrderType,
    OrderVariety,
    ProductType,
    TransactionType,
)
from loats.utils.payload_builder import (
    _enum_to_value,
    build_cancel_order_payload,
    build_modify_order_payload,
    build_place_order_payload,
    build_place_smart_order_payload,
)

class TestPayloadBuilderUtilities(unittest.TestCase):
    """Test suite for payload builder utility functions."""

    def test_enum_to_value(self):
        """Test enum to value conversion."""
        # Test with enum
        result = _enum_to_value(OrderType.MARKET)
        assert result == "MARKET"

        # Test with string
        result = _enum_to_value("MARKET")
        assert result == "MARKET"

        # Test with other types
        result = _enum_to_value(123)
        assert result == 123

        result = _enum_to_value(None)
        assert result is None

        # Test with custom enum
        class TestEnum(Enum):
            VALUE1 = "value1"
            VALUE2 = "value2"

        result = _enum_to_value(TestEnum.VALUE1)
        assert result == "value1"

class TestBuildPlaceOrderPayload(unittest.TestCase):
    """Test suite for build_place_order_payload function."""

    def test_build_place_order_payload_minimal(self):
        """Test minimal place order payload."""
        payload = build_place_order_payload(
            symbol="RELIANCE",
            quantity=10,
            order_type=OrderType.MARKET,
        )

        expected = {
            "symbol": "RELIANCE",
            "quantity": 10,
            "order_type": "MARKET",
            "variety": "regular",
            "transaction_type": "BUY",
            "product_type": "MIS",
        }
        assert payload == expected

    def test_build_place_order_payload_with_optional_fields(self):
        """Test place order payload with optional fields."""
        payload = build_place_order_payload(
            symbol="RELIANCE",
            quantity=10,
            order_type=OrderType.LIMIT,
            price=105.0,
            variety=OrderVariety.REGULAR,
            transaction_type=TransactionType.SELL,
            product_type=ProductType.NRML,
            trigger_price=104.0,
            stop_loss=95.0,
            take_profit=110.0,
            trailing_stop_loss=5.0,
        )

        expected = {
            "symbol": "RELIANCE",
            "quantity": 10,
            "order_type": "LIMIT",
            "variety": "regular",
            "transaction_type": "SELL",
            "product_type": "NRML",
            "price": 105.0,
            "trigger_price": 104.0,
            "stop_loss": 95.0,
            "take_profit": 110.0,
            "trailing_stop_loss": 5.0,
        }
        assert payload == expected

    def test_build_place_order_payload_with_string_enums(self):
        """Test place order payload with string enum values."""
        payload = build_place_order_payload(
            symbol="RELIANCE",
            quantity=10,
            order_type="LIMIT",
            price=105.0,
            variety="stoploss",
            transaction_type="SELL",
            product_type="NRML",
        )

        expected = {
            "symbol": "RELIANCE",
            "quantity": 10,
            "order_type": "LIMIT",
            "variety": "stoploss",
            "transaction_type": "SELL",
            "product_type": "NRML",
            "price": 105.0,
        }
        assert payload == expected

    def test_build_place_order_payload_with_none_optional_fields(self):
        """Test place order payload with None optional fields."""
        payload = build_place_order_payload(
            symbol="RELIANCE",
            quantity=10,
            order_type=OrderType.MARKET,
            price=None,
            trigger_price=None,
            stop_loss=None,
            take_profit=None,
            trailing_stop_loss=None,
        )

        expected = {
            "symbol": "RELIANCE",
            "quantity": 10,
            "order_type": "MARKET",
            "variety": "regular",
            "transaction_type": "BUY",
            "product_type": "MIS",
        }
        assert payload == expected

class TestBuildPlaceSmartOrderPayload(unittest.TestCase):
    """Test suite for build_place_smart_order_payload function."""

    def test_build_place_smart_order_payload_minimal(self):
        """Test minimal place smart order payload."""
        payload = build_place_smart_order_payload(
            symbol="RELIANCE",
            quantity=10,
            order_type=OrderType.MARKET,
        )

        expected = {
            "symbol": "RELIANCE",
            "quantity": 10,
            "order_type": "MARKET",
            "strategy": "simple",
            "transaction_type": "BUY",
            "product_type": "MIS",
        }
        assert payload == expected

    def test_build_place_smart_order_payload_with_optional_fields(self):
        """Test place smart order payload with optional fields."""
        payload = build_place_smart_order_payload(
            symbol="RELIANCE",
            quantity=10,
            order_type=OrderType.LIMIT,
            price=105.0,
            trigger_price=104.0,
            stop_loss=95.0,
            take_profit=110.0,
            trailing_stop_loss=5.0,
            strategy="momentum",
            transaction_type=TransactionType.SELL,
            product_type=ProductType.NRML,
            metadata={"target": 115.0, "timeframe": "1d"},
        )

        expected = {
            "symbol": "RELIANCE",
            "quantity": 10,
            "order_type": "LIMIT",
            "strategy": "momentum",
            "transaction_type": "SELL",
            "product_type": "NRML",
            "price": 105.0,
            "trigger_price": 104.0,
            "stop_loss": 95.0,
            "take_profit": 110.0,
            "trailing_stop_loss": 5.0,
            "metadata": {"target": 115.0, "timeframe": "1d"},
        }
        assert payload == expected

    def test_build_place_smart_order_payload_with_string_enums(self):
        """Test place smart order payload with string enum values."""
        payload = build_place_smart_order_payload(
            symbol="RELIANCE",
            quantity=10,
            order_type="LIMIT",
            price=105.0,
            strategy="momentum",
            transaction_type="SELL",
            product_type="NRML",
        )

        expected = {
            "symbol": "RELIANCE",
            "quantity": 10,
            "order_type": "LIMIT",
            "strategy": "momentum",
            "transaction_type": "SELL",
            "product_type": "NRML",
            "price": 105.0,
        }
        assert payload == expected

    def test_build_place_smart_order_payload_with_none_optional_fields(self):
        """Test place smart order payload with None optional fields."""
        payload = build_place_smart_order_payload(
            symbol="RELIANCE",
            quantity=10,
            order_type=OrderType.MARKET,
            price=None,
            trigger_price=None,
            stop_loss=None,
            take_profit=None,
            trailing_stop_loss=None,
            metadata=None,
        )

        expected = {
            "symbol": "RELIANCE",
            "quantity": 10,
            "order_type": "MARKET",
            "strategy": "simple",
            "transaction_type": "BUY",
            "product_type": "MIS",
        }
        assert payload == expected

class TestBuildModifyOrderPayload(unittest.TestCase):
    """Test suite for build_modify_order_payload function."""

    def test_build_modify_order_payload_minimal(self):
        """Test minimal modify order payload."""
        payload = build_modify_order_payload(
            order_id="12345",
        )

        expected = {
            "order_id": "12345",
        }
        assert payload == expected

    def test_build_modify_order_payload_with_optional_fields(self):
        """Test modify order payload with optional fields."""
        payload = build_modify_order_payload(
            order_id="12345",
            quantity=20,
            order_type=OrderType.LIMIT,
            price=105.0,
            trigger_price=104.0,
            stop_loss=95.0,
            take_profit=110.0,
            trailing_stop_loss=5.0,
        )

        expected = {
            "order_id": "12345",
            "quantity": 20,
            "order_type": "LIMIT",
            "price": 105.0,
            "trigger_price": 104.0,
            "stop_loss": 95.0,
            "take_profit": 110.0,
            "trailing_stop_loss": 5.0,
        }
        assert payload == expected

    def test_build_modify_order_payload_with_string_enums(self):
        """Test modify order payload with string enum values."""
        payload = build_modify_order_payload(
            order_id="12345",
            quantity=20,
            order_type="LIMIT",
            price=105.0,
        )

        expected = {
            "order_id": "12345",
            "quantity": 20,
            "order_type": "LIMIT",
            "price": 105.0,
        }
        assert payload == expected

    def test_build_modify_order_payload_with_none_optional_fields(self):
        """Test modify order payload with None optional fields."""
        payload = build_modify_order_payload(
            order_id="12345",
            quantity=None,
            order_type=None,
            price=None,
            trigger_price=None,
            stop_loss=None,
            take_profit=None,
            trailing_stop_loss=None,
        )

        expected = {
            "order_id": "12345",
        }
        assert payload == expected

class TestBuildCancelOrderPayload(unittest.TestCase):
    """Test suite for build_cancel_order_payload function."""

    def test_build_cancel_order_payload(self):
        """Test cancel order payload."""
        payload = build_cancel_order_payload(
            order_id="12345",
        )

        expected = {
            "order_id": "12345",
        }
        assert payload == expected

    def test_build_cancel_order_payload_different_order_id(self):
        """Test cancel order payload with different order ID."""
        payload = build_cancel_order_payload(
            order_id="67890",
        )

        expected = {
            "order_id": "67890",
        }
        assert payload == expected

class TestPayloadBuilderEdgeCases(unittest.TestCase):
    """Test suite for payload builder edge cases."""

    def test_empty_symbol(self):
        """Test with empty symbol."""
        payload = build_place_order_payload(
            symbol="",
            quantity=10,
            order_type=OrderType.MARKET,
        )

        expected = {
            "symbol": "",
            "quantity": 10,
            "order_type": "MARKET",
            "variety": "regular",
            "transaction_type": "BUY",
            "product_type": "MIS",
        }
        assert payload == expected

    def test_zero_quantity(self):
        """Test with zero quantity."""
        payload = build_place_order_payload(
            symbol="RELIANCE",
            quantity=0,
            order_type=OrderType.MARKET,
        )

        expected = {
            "symbol": "RELIANCE",
            "quantity": 0,
            "order_type": "MARKET",
            "variety": "regular",
            "transaction_type": "BUY",
            "product_type": "MIS",
        }
        assert payload == expected

    def test_negative_price(self):
        """Test with negative price."""
        payload = build_place_order_payload(
            symbol="RELIANCE",
            quantity=10,
            order_type=OrderType.LIMIT,
            price=-105.0,
        )

        expected = {
            "symbol": "RELIANCE",
            "quantity": 10,
            "order_type": "LIMIT",
            "variety": "regular",
            "transaction_type": "BUY",
            "product_type": "MIS",
            "price": -105.0,
        }
        assert payload == expected

    def test_large_values(self):
        """Test with large values."""
        payload = build_place_order_payload(
            symbol="RELIANCE",
            quantity=1000000,
            order_type=OrderType.LIMIT,
            price=999999.99,
        )

        expected = {
            "symbol": "RELIANCE",
            "quantity": 1000000,
            "order_type": "LIMIT",
            "variety": "regular",
            "transaction_type": "BUY",
            "product_type": "MIS",
            "price": 999999.99,
        }
        assert payload == expected

    def test_special_characters_in_symbol(self):
        """Test with special characters in symbol."""
        payload = build_place_order_payload(
            symbol="RELIANCE&NIFTY",
            quantity=10,
            order_type=OrderType.MARKET,
        )

        expected = {
            "symbol": "RELIANCE&NIFTY",
            "quantity": 10,
            "order_type": "MARKET",
            "variety": "regular",
            "transaction_type": "BUY",
            "product_type": "MIS",
        }
        assert payload == expected

    def test_unicode_symbol(self):
        """Test with unicode symbol."""
        payload = build_place_order_payload(
            symbol="RELIANCE-निफ्टी",
            quantity=10,
            order_type=OrderType.MARKET,
        )

        expected = {
            "symbol": "RELIANCE-निफ्टी",
            "quantity": 10,
            "order_type": "MARKET",
            "variety": "regular",
            "transaction_type": "BUY",
            "product_type": "MIS",
        }
        assert payload == expected

    def test_complex_metadata(self):
        """Test with complex metadata."""
        complex_metadata = {
            "strategy": "momentum",
            "indicators": {
                "rsi": 30.0,
                "macd": 1.5,
                "ema": [50.0, 100.0, 200.0],
            },
            "timeframes": ["1d", "1w", "1m"],
            "targets": {
                "primary": 115.0,
                "secondary": 120.0,
            },
        }

        payload = build_place_smart_order_payload(
            symbol="RELIANCE",
            quantity=10,
            order_type=OrderType.MARKET,
            metadata=complex_metadata,
        )

        expected = {
            "symbol": "RELIANCE",
            "quantity": 10,
            "order_type": "MARKET",
            "strategy": "simple",
            "transaction_type": "BUY",
            "product_type": "MIS",
            "metadata": complex_metadata,
        }
        assert payload == expected

if __name__ == "__main__":
    # Run the tests
    unittest.main(verbosity=2)
