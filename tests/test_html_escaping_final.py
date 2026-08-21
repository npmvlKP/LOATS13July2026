from unittest.mock import AsyncMock, patch

import pytest

from loats.alerts import AlertSystem
from loats.models import Order, OrderStatus, OrderType, TransactionType


@pytest.mark.asyncio
async def test_html_escaping_final():
    """Final test to verify HTML escaping is working."""
    # Create an order with HTML content
    order = Order(
        order_id="<script>test</script>",
        symbol="AAPL",
        order_type=OrderType.LIMIT,
        transaction_type=TransactionType.BUY,
        quantity=10,
        price=100.50,
        status=OrderStatus.OPEN,
        filled_quantity=0,
        timestamp="2023-01-01T00:00:00",
        variety="regular",
        product_type="MIS",
    )

    # Mock the send_alert method to capture the message
    with patch.object(
        AlertSystem, "send_alert", new_callable=AsyncMock
    ) as mock_send_alert:
        alert_system = AlertSystem()
        await alert_system.send_order_alert(order, "created")

        # Get the message that was sent
        call_args = mock_send_alert.call_args
        message = call_args[0][0]

        # Verify HTML escaping is working correctly
        assert "&lt;script&gt;test&lt;/script&gt;" in message
        assert "<script>test</script>" not in message

        print("OK HTML escaping is working correctly!")
