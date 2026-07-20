import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.loats.alerts import AlertSystem
from src.loats.models import (
    Signal,
    SignalType,
)


@pytest.fixture
def mock_settings():
    with patch("src.loats.alerts.settings") as m:
        m.telegram_chat_id = "123"
        token = MagicMock()
        token.get_secret_value.return_value = "token"
        m.telegram_bot_token = token
        yield m


@pytest.mark.asyncio
async def test_alert_system_initialization_no_config():
    with patch("src.loats.alerts.settings") as m:
        m.telegram_bot_token = None
        alert_system = AlertSystem()
        await alert_system.initialize()
        assert alert_system.bot is None


@pytest.mark.asyncio
async def test_alert_system_initialization_success(mock_settings):
    with (
        patch("src.loats.alerts.Bot"),
        patch("src.loats.alerts.Application") as mock_app_cls,
    ):
        alert_system = AlertSystem()
        await alert_system.initialize()
        assert alert_system.bot is not None
        mock_app_cls.builder.return_value.bot.return_value.build.assert_called()


@pytest.mark.asyncio
async def test_alert_system_send_alert(mock_settings):
    alert_system = AlertSystem()
    alert_system.bot = AsyncMock()
    result = await alert_system.send_alert("test message", "info")
    assert result is True
    alert_system.bot.send_message.assert_called()


@pytest.mark.asyncio
async def test_alert_system_send_signal_alert(mock_settings):
    alert_system = AlertSystem()
    alert_system.bot = AsyncMock()
    signal = Signal(
        symbol="TEST",
        signal_type=SignalType.BUY,
        strength=0.9,
        confidence=0.8,
        indicators={"RSI": 70},
        metadata={"count": 1},
        timestamp=datetime.datetime.now(),
    )
    result = await alert_system.send_signal_alert(signal)
    assert result is True


@pytest.mark.asyncio
async def test_alert_system_kill_switch(mock_settings):
    alert_system = AlertSystem()
    alert_system.bot = AsyncMock()
    with patch("src.loats.alerts.async_client", new_callable=AsyncMock) as mock_client:
        mock_client.get_all_orders.return_value = {
            "data": [{"order_id": "1", "status": "OPEN"}]
        }
        result = await alert_system.activate_kill_switch("Manual")
        assert result is True
        assert alert_system.is_kill_switch_active() is True
        result = await alert_system.deactivate_kill_switch("Manual")
        assert result is True
        assert alert_system.is_kill_switch_active() is False


@pytest.mark.asyncio
async def test_alert_system_send_position_alert(mock_settings):
    alert_system = AlertSystem()
    alert_system.bot = AsyncMock()
    with patch("src.loats.alerts.async_client", new_callable=AsyncMock) as mock_client:
        mock_client.get_position_book.return_value = {
            "data": [
                {
                    "symbol": "TEST",
                    "quantity": 10,
                    "average_price": 100,
                    "last_price": 105,
                    "product_type": "DELIVERY",
                    "pnl": 50,
                }
            ]
        }
        result = await alert_system.send_position_alert()
        assert result is True


@pytest.mark.asyncio
async def test_alert_system_handle_commands(mock_settings):
    alert_system = AlertSystem()
    alert_system.bot = AsyncMock()
    mock_update = MagicMock()
    mock_update.message = AsyncMock()
    await alert_system._status(mock_update, None)
    mock_update.message.reply_text.assert_called()
