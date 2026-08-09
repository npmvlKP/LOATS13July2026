"""
Test HTML escaping fix for R5-5 issue.
Verifies that send_order_alert and send_trade_alert properly escape HTML content.
"""
import pytest
from unittest.mock import AsyncMock, patch
from src.loats.alerts import AlertSystem
from src.loats.models import Order, OrderType, OrderStatus, TransactionType, Trade, OrderVariety, ProductType

@pytest.mark.asyncio
async def test_send_order_alert_html_escaping():
    """Test that send_order_alert properly escapes HTML in order fields."""
    # Create an order with potentially dangerous HTML content
    order = Order(
        order_id="<script>alert('xss')</script>",
        symbol="AAPL<script>malicious()</script>",
        order_type=OrderType.LIMIT,
        transaction_type=TransactionType.BUY,
        quantity=10,
        price=100.50,
        status=OrderStatus.OPEN,
        filled_quantity=0,
        timestamp="2023-01-01T00:00:00",
        variety=OrderVariety.REGULAR,
        product_type=ProductType.MIS
    )

    # Mock the send_alert method to capture the message
    with patch.object(AlertSystem, 'send_alert', new_callable=AsyncMock) as mock_send_alert:
        alert_system = AlertSystem()
        await alert_system.send_order_alert(order, "created")

        # Verify send_alert was called
        assert mock_send_alert.called

        # Get the message that was sent
        call_args = mock_send_alert.call_args
        message = call_args[0][0]  # First positional argument

        # Verify HTML escaping is applied - should contain escaped versions
        assert "<script>alert(&#x27;xss&#x27;)</script>" in message
        assert "<script>malicious()</script>" in message
        # Verify raw HTML tags are NOT present (security fix working)
        assert "<script>" not in message
        assert "</script>" not in message

        print("✅ Order alert HTML escaping test passed")

@pytest.mark.asyncio
async def test_send_trade_alert_html_escaping():
    """Test that send_trade_alert properly escapes HTML in trade fields."""
    # Create a trade with potentially dangerous HTML content
    trade = Trade(
        trade_id="<img src=x onerror=alert(1)>",
        symbol="MSFT<img src=x onerror=alert(1)>",
        strategy="<b>Test Strategy</b>",
        transaction_type=TransactionType.SELL,
        quantity=5,
        entry_price=150.75,
        status="OPEN",
        entry_time="2023-01-01T00:00:00"
    )

    # Mock the send_alert method to capture the message
    with patch.object(AlertSystem, 'send_alert', new_callable=AsyncMock) as mock_send_alert:
        alert_system = AlertSystem()
        await alert_system.send_trade_alert(trade, "opened")

        # Verify send_alert was called
        assert mock_send_alert.called

        # Get the message that was sent
        call_args = mock_send_alert.call_args
        message = call_args[0][0]  # First positional argument

        # Verify HTML escaping is applied - should contain escaped versions
        assert "<img src=x onerror=alert(1)>" in message
        assert "<b>Test Strategy</b>" in message
        # Verify raw HTML tags are NOT present (security fix working)
        assert "<img" not in message
        assert "<b>" not in message

        print("✅ Trade alert HTML escaping test passed")

@pytest.mark.asyncio
async def test_consistency_with_other_alerts():
    """Test that HTML escaping is consistent across all alert methods."""
    alert_system = AlertSystem()

    # Test signal alert (should already have HTML escaping)
    with patch.object(AlertSystem, 'send_alert', new_callable=AsyncMock) as mock_send_alert:
        from src.loats.models import Signal, SignalType
        signal = Signal(
            signal_id="1",
            symbol="<test>",
            signal_type=SignalType.BUY,
            strength=0.8,
            confidence=0.9,
            timestamp="2023-01-01T00:00:00",
            indicators={"rsi": 70.0},
            metadata={"source": "<script>test</script>"}
        )
        await alert_system.send_signal_alert(signal)

        # Verify signal alert escapes HTML - should contain escaped versions
        call_args = mock_send_alert.call_args
        signal_message = call_args[0][0]
        assert "<test>" in signal_message
        assert "<script>test</script>" in signal_message
        # Verify raw HTML tags are NOT present (security working)
        assert "<test>" not in signal_message
        assert "<script>" not in signal_message

    print("✅ Consistency test passed - all alert methods use HTML escaping")

if __name__ == "__main__":
    import asyncio
    asyncio.run(test_send_order_alert_html_escaping())
    asyncio.run(test_send_trade_alert_html_escaping())
    asyncio.run(test_consistency_with_other_alerts())
    print("🎉 All HTML escaping tests passed!")