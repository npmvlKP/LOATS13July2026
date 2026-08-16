import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from loats.alerts import AlertSystem
from loats.models import (
    Signal,
    SignalType,
)


@pytest.fixture
def mock_settings():
    with patch("loats.alerts.settings") as m:
        m.telegram_chat_id = "123"
        token = MagicMock()
        token.get_secret_value.return_value = "token"
        m.telegram_bot_token = token
        yield m


@pytest.mark.asyncio
async def test_alert_system_initialization_no_config():
    with patch("loats.alerts.settings") as m:
        m.telegram_bot_token = None
        alert_system = AlertSystem()
        await alert_system.initialize()
        assert alert_system.bot is None


@pytest.mark.asyncio
async def test_alert_system_initialization_success(mock_settings):
    with (
        patch("loats.alerts.Bot"),
        patch("loats.alerts.Application") as mock_app_cls,
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
    with patch("loats.alerts.async_client", new_callable=AsyncMock) as mock_client:
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
    with patch("loats.alerts.async_client", new_callable=AsyncMock) as mock_client:
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


@pytest.mark.asyncio
async def test_alert_system_initialize_bot_success(mock_settings):
    """Test _initialize_bot method (lines 80-88)."""
    alert_system = AlertSystem()
    with patch("loats.alerts.Bot") as mock_bot_class:
        mock_bot = AsyncMock()
        mock_bot_class.return_value = mock_bot
        bot = await alert_system._initialize_bot()
        assert bot == mock_bot
        assert alert_system.bot == mock_bot


@pytest.mark.asyncio
async def test_alert_system_initialize_bot_missing_token():
    """Test _initialize_bot method with missing token (lines 82-84)."""
    with patch("loats.alerts.settings") as mock_settings:
        mock_settings.telegram_bot_token = None
        alert_system = AlertSystem()
        with pytest.raises(ValueError, match="Telegram bot token not configured"):
            await alert_system._initialize_bot()


@pytest.mark.asyncio
async def test_alert_system_initialize_bot_missing_chat_id():
    """Test _initialize_bot method with missing chat ID (lines 85-87)."""
    with patch("loats.alerts.settings") as mock_settings:
        mock_settings.telegram_bot_token = MagicMock()
        mock_settings.telegram_bot_token.get_secret_value.return_value = "token"
        mock_settings.telegram_chat_id = None
        alert_system = AlertSystem()
        with pytest.raises(ValueError, match="Telegram chat ID not configured"):
            await alert_system._initialize_bot()


@pytest.mark.asyncio
async def test_alert_system_start_no_application(mock_settings):
    """Test start method when application is None (lines 129-130)."""
    alert_system = AlertSystem()
    alert_system.application = None
    await alert_system.start()
    # Should return early without error


@pytest.mark.asyncio
async def test_alert_system_start_already_running(mock_settings):
    """Test start method when already running (lines 131-133)."""
    alert_system = AlertSystem()
    alert_system.application = AsyncMock()
    alert_system._running = True
    await alert_system.start()
    # Should return early without starting again


@pytest.mark.asyncio
async def test_alert_system_start_success(mock_settings):
    """Test start method successful execution (lines 135-155)."""
    alert_system = AlertSystem()
    mock_app = AsyncMock()
    mock_updater = AsyncMock()
    mock_app.updater = mock_updater
    alert_system.application = mock_app

    with patch("asyncio.create_task") as mock_create_task:
        await alert_system.start()
        mock_app.initialize.assert_called()
        mock_app.start.assert_called()
        mock_create_task.assert_called()
        assert alert_system._running is True


@pytest.mark.asyncio
async def test_alert_system_start_no_updater(mock_settings):
    """Test start method when updater is None (lines 148-149)."""
    alert_system = AlertSystem()
    mock_app = AsyncMock()
    mock_app.updater = None
    alert_system.application = mock_app

    await alert_system.start()
    mock_app.initialize.assert_called()
    mock_app.start.assert_called()
    assert alert_system._running is True


@pytest.mark.asyncio
async def test_alert_system_start_exception_handling(mock_settings):
    """Test start method exception handling (lines 153-155)."""
    alert_system = AlertSystem()
    mock_app = AsyncMock()
    mock_app.start.side_effect = Exception("Test error")
    alert_system.application = mock_app

    with pytest.raises(Exception, match="Test error"):
        await alert_system.start()
    assert alert_system._running is False


@pytest.mark.asyncio
async def test_alert_system_shutdown_no_application(mock_settings):
    """Test shutdown method when application is None."""
    alert_system = AlertSystem()
    alert_system.application = None
    await alert_system.shutdown()
    # Should handle gracefully


@pytest.mark.asyncio
async def test_alert_system_shutdown_not_running(mock_settings):
    """Test shutdown method when not running."""
    alert_system = AlertSystem()
    mock_app = AsyncMock()
    alert_system.application = mock_app
    alert_system._running = False
    await alert_system.shutdown()
    # Should handle gracefully


@pytest.mark.asyncio
async def test_alert_system_shutdown_no_polling_task(mock_settings):
    """Test shutdown method when no polling task exists."""
    alert_system = AlertSystem()
    mock_app = AsyncMock()
    mock_updater = AsyncMock()
    mock_app.updater = mock_updater
    alert_system.application = mock_app
    alert_system._running = True
    alert_system._polling_task = None

    await alert_system.shutdown()
    mock_updater.stop.assert_called()
    mock_app.stop.assert_called()
