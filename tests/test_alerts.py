"""Tests alerts module."""
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from telegram import Bot, Update
from telegram.error import InvalidToken
from telegram.ext import (
    Application,
)

from src.loats.alerts import AlertSystem
from src.loats.models import (
    Order,
    OrderStatus,
    OrderType,
    OrderVariety,
    ProductType,
    Signal,
    SignalType,
    Trade,
    TransactionType,
)


class TestAlertSystem:
    """Test cases for AlertSystem class."""

    @pytest.fixture
    def alert_system(self):
        """Create a fresh AlertSystem instance for each test."""
        return AlertSystem()

    @pytest.fixture
    def mock_bot(self):
        """Create a mock Telegram bot."""
        bot = MagicMock(spec=Bot)
        bot.send_message = AsyncMock()
        return bot

    @pytest.fixture
    def mock_application(self):
        """Create a mock Telegram application."""
        app = MagicMock(spec=Application)
        app.shutdown = AsyncMock()

        # Create a proper async coroutine for run_polling
        async def run_polling_coro():
            return None

        app.run_polling = MagicMock(return_value=run_polling_coro())
        return app

    @pytest.fixture
    def sample_signal(self):
        """Create a sample signal for testing."""
        return Signal(
            signal_id="test_signal_1",
            symbol="NIFTY",
            signal_type=SignalType.BUY,
            strength=0.85,
            confidence=0.92,
            timestamp=datetime.now(UTC),
            indicators={
                "rsi": 65.4,
                "macd": 12.3,
                "supertrend": 18500.5,
            },
            metadata={
                "strategy": "momentum",
                "timeframe": "15m",
                "indicators_count": 3,
            },
        )

    @pytest.fixture
    def sample_order(self):
        """Create a sample order for testing."""
        return Order(
            order_id="test_order_1",
            symbol="NIFTY",
            order_type=OrderType.LIMIT,
            transaction_type=TransactionType.BUY,
            quantity=50,
            price=18550.25,
            variety=OrderVariety.REGULAR,
            product_type=ProductType.MIS,
            status=OrderStatus.OPEN,
            filled_quantity=0,
            timestamp=datetime.now(UTC),
            stop_loss=18500.0,
            take_profit=18600.0,
            trailing_stop_loss=18520.0,
        )

    @pytest.fixture
    def sample_trade(self):
        """Create a sample trade for testing."""
        return Trade(
            trade_id="test_trade_1",
            symbol="NIFTY",
            strategy="momentum",
            transaction_type=TransactionType.BUY,
            product_type=ProductType.MIS,
            quantity=50,
            entry_price=18550.25,
            status="OPEN",
            entry_time=datetime.now(UTC),
            exit_price=None,
            exit_time=None,
            pnl=None,
            stop_loss=18500.0,
            take_profit=18600.0,
            trailing_stop_loss=18520.0,
        )

    def test_alert_system_initialization(self, alert_system):
        """Test AlertSystem initializes correctly."""
        assert alert_system.bot is None
        assert alert_system.application is None
        assert alert_system.kill_switch_active is False
        assert isinstance(alert_system.alert_cooldown, dict)
        assert alert_system.cooldown_period == 300

    def test_is_kill_switch_active_initial_state(self, alert_system):
        """Test kill switch status is initially False."""
        assert alert_system.is_kill_switch_active() is False

    @pytest.mark.asyncio
    async def test_initialize_without_token(self, alert_system):
        """Test initialization fails gracefully without bot token."""
        with patch("src.loats.alerts.settings") as mock_settings:
            mock_settings.telegram_bot_token.get_secret_value.return_value = ""
            with patch("src.loats.alerts.Bot", side_effect=InvalidToken("Invalid token")):
                with pytest.raises(InvalidToken):
                    await alert_system.initialize()
        assert alert_system.bot is None

    @pytest.mark.asyncio
    async def test_initialize_without_chat_id(self, alert_system):
        """Test initialization fails gracefully without chat ID."""
        with patch("src.loats.alerts.settings") as mock_settings:
            mock_settings.telegram_bot_token.get_secret_value.return_value = "test_token"
            mock_settings.telegram_chat_id = None
            await alert_system.initialize()
        assert alert_system.bot is None

    @pytest.mark.asyncio
    async def test_initialize_success(self, alert_system, mock_bot):
        """Test successful initialization."""
        with patch("src.loats.alerts.settings") as mock_settings, \
             patch("src.loats.alerts.Bot") as mock_bot_class, \
             patch("src.loats.alerts.Application") as mock_app_class:
            mock_settings.telegram_bot_token.get_secret_value.return_value = "test_token"
            mock_settings.telegram_chat_id = "test_chat_id"
            mock_bot_class.return_value = mock_bot

            mock_app = MagicMock()
            mock_app.add_handler = MagicMock()
            mock_app_class.builder.return_value.bot.return_value.build.return_value = mock_app

            await alert_system.initialize()

        assert alert_system.bot == mock_bot
        assert alert_system.application == mock_app

    @pytest.mark.asyncio
    async def test_start_without_application(self, alert_system):
        """Test start() does nothing without application."""
        await alert_system.start()
        # Should not raise any exception

    @pytest.mark.asyncio
    async def test_start_success(self, alert_system, mock_application):
        """Test successful bot start."""
        alert_system.application = mock_application
        await alert_system.start()
        # Should not raise any exception

    @pytest.mark.asyncio
    async def test_shutdown_without_application(self, alert_system):
        """Test shutdown() does nothing without application."""
        await alert_system.shutdown()
        # Should not raise any exception

    @pytest.mark.asyncio
    async def test_shutdown_success(self, alert_system, mock_application):
        """Test successful bot shutdown."""
        alert_system.application = mock_application
        await alert_system.shutdown()
        mock_application.shutdown.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_alert_without_bot(self, alert_system):
        """Test send_alert returns False without bot."""
        result = await alert_system.send_alert("Test message")
        assert result is False

    @pytest.mark.asyncio
    async def test_send_alert_success(self, alert_system, mock_bot):
        """Test successful alert sending."""
        alert_system.bot = mock_bot
        with patch("src.loats.alerts.settings") as mock_settings:
            mock_settings.telegram_chat_id = "test_chat_id"
            result = await alert_system.send_alert("Test message", "info")

        assert result is True
        mock_bot.send_message.assert_called_once()
        assert "info" in alert_system.alert_cooldown

    @pytest.mark.asyncio
    async def test_send_alert_cooldown(self, alert_system, mock_bot):
        """Test alert cooldown prevents spamming."""
        alert_system.bot = mock_bot
        with patch("src.loats.alerts.settings") as mock_settings:
            mock_settings.telegram_chat_id = "test_chat_id"

            # Send first alert
            result1 = await alert_system.send_alert("Test message", "info")
            assert result1 is True

            # Send second alert immediately (should be blocked by cooldown)
            result2 = await alert_system.send_alert("Test message 2", "info")
            assert result2 is False
            assert mock_bot.send_message.call_count == 1

    def test_format_alert_message_info(self, alert_system):
        """Test formatting info alert message."""
        message = "Test info message"
        formatted = alert_system._format_alert_message(message, "info")
        assert "ℹ️" in formatted
        assert "INFO" in formatted
        assert message in formatted

    def test_format_alert_message_warning(self, alert_system):
        """Test formatting warning alert message."""
        message = "Test warning message"
        formatted = alert_system._format_alert_message(message, "warning")
        assert "⚠️" in formatted
        assert "WARNING" in formatted
        assert message in formatted

    def test_format_alert_message_error(self, alert_system):
        """Test formatting error alert message."""
        message = "Test error message"
        formatted = alert_system._format_alert_message(message, "error")
        assert "🚨" in formatted
        assert "ERROR" in formatted
        assert message in formatted

    def test_format_alert_message_success(self, alert_system):
        """Test formatting success alert message."""
        message = "Test success message"
        formatted = alert_system._format_alert_message(message, "success")
        assert "✅" in formatted
        assert "SUCCESS" in formatted
        assert message in formatted

    @pytest.mark.asyncio
    async def test_send_signal_alert_buy(self, alert_system, mock_bot, sample_signal):
        """Test sending BUY signal alert."""
        alert_system.bot = mock_bot
        with patch("src.loats.alerts.settings") as mock_settings:
            mock_settings.telegram_chat_id = "test_chat_id"
            result = await alert_system.send_signal_alert(sample_signal)

        assert result is True
        mock_bot.send_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_signal_alert_sell(self, alert_system, mock_bot):
        """Test sending SELL signal alert."""
        signal = Signal(
            signal_id="test_signal_2",
            symbol="NIFTY",
            signal_type=SignalType.SELL,
            strength=0.85,
            confidence=0.92,
            timestamp=datetime.now(UTC),
            indicators={"rsi": 65.4},
            metadata={},
        )
        alert_system.bot = mock_bot
        with patch("src.loats.alerts.settings") as mock_settings:
            mock_settings.telegram_chat_id = "test_chat_id"
            result = await alert_system.send_signal_alert(signal)

        assert result is True

    @pytest.mark.asyncio
    async def test_send_signal_alert_exception(self, alert_system, sample_signal):
        """Test signal alert handles exceptions."""
        with patch.object(alert_system, "send_alert", side_effect=Exception("Test error")):
            result = await alert_system.send_signal_alert(sample_signal)
        assert result is False

    @pytest.mark.asyncio
    async def test_send_order_alert_created(self, alert_system, mock_bot, sample_order):
        """Test sending order created alert."""
        alert_system.bot = mock_bot
        with patch("src.loats.alerts.settings") as mock_settings:
            mock_settings.telegram_chat_id = "test_chat_id"
            result = await alert_system.send_order_alert(sample_order, "created")

        assert result is True
        mock_bot.send_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_order_alert_filled(self, alert_system, mock_bot, sample_order):
        """Test sending order filled alert."""
        sample_order.status = OrderStatus.COMPLETED
        sample_order.filled_quantity = 50
        alert_system.bot = mock_bot
        with patch("src.loats.alerts.settings") as mock_settings:
            mock_settings.telegram_chat_id = "test_chat_id"
            result = await alert_system.send_order_alert(sample_order, "filled")

        assert result is True

    @pytest.mark.asyncio
    async def test_send_order_alert_exception(self, alert_system, sample_order):
        """Test order alert handles exceptions."""
        with patch.object(alert_system, "send_alert", side_effect=Exception("Test error")):
            result = await alert_system.send_order_alert(sample_order, "created")
        assert result is False

    @pytest.mark.asyncio
    async def test_send_trade_alert_opened(self, alert_system, mock_bot, sample_trade):
        """Test sending trade opened alert."""
        alert_system.bot = mock_bot
        with patch("src.loats.alerts.settings") as mock_settings:
            mock_settings.telegram_chat_id = "test_chat_id"
            result = await alert_system.send_trade_alert(sample_trade, "opened")

        assert result is True
        mock_bot.send_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_trade_alert_closed_profit(self, alert_system, mock_bot):
        """Test sending trade closed profit alert."""
        trade = Trade(
            trade_id="test_trade_2",
            symbol="NIFTY",
            strategy="momentum",
            transaction_type=TransactionType.BUY,
            product_type=ProductType.MIS,
            quantity=50,
            entry_price=18500.0,
            status="CLOSED",
            entry_time=datetime.now(UTC),
            exit_price=18600.0,
            exit_time=datetime.now(UTC),
            pnl=5000.0,
            stop_loss=18500.0,
            take_profit=18600.0,
        )
        alert_system.bot = mock_bot
        with patch("src.loats.alerts.settings") as mock_settings:
            mock_settings.telegram_chat_id = "test_chat_id"
            result = await alert_system.send_trade_alert(trade, "closed")

        assert result is True

    @pytest.mark.asyncio
    async def test_send_trade_alert_closed_loss(self, alert_system, mock_bot):
        """Test sending trade closed loss alert."""
        trade = Trade(
            trade_id="test_trade_3",
            symbol="NIFTY",
            strategy="momentum",
            transaction_type=TransactionType.BUY,
            product_type=ProductType.MIS,
            quantity=50,
            entry_price=18600.0,
            status="CLOSED",
            entry_time=datetime.now(UTC),
            exit_price=18500.0,
            exit_time=datetime.now(UTC),
            pnl=-5000.0,
            stop_loss=18500.0,
            take_profit=18600.0,
        )
        alert_system.bot = mock_bot
        with patch("src.loats.alerts.settings") as mock_settings:
            mock_settings.telegram_chat_id = "test_chat_id"
            result = await alert_system.send_trade_alert(trade, "closed")

        assert result is True

    @pytest.mark.asyncio
    async def test_send_trade_alert_exception(self, alert_system, sample_trade):
        """Test trade alert handles exceptions."""
        with patch.object(alert_system, "send_alert", side_effect=Exception("Test error")):
            result = await alert_system.send_trade_alert(sample_trade, "opened")
        assert result is False

    @pytest.mark.asyncio
    async def test_send_system_alert(self, alert_system, mock_bot):
        """Test sending system alert."""
        alert_system.bot = mock_bot
        with patch("src.loats.alerts.settings") as mock_settings:
            mock_settings.telegram_chat_id = "test_chat_id"
            result = await alert_system.send_system_alert("System restart required", "warning")

        assert result is True
        mock_bot.send_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_system_alert_exception(self, alert_system):
        """Test system alert handles exceptions."""
        with patch.object(alert_system, "send_alert", side_effect=Exception("Test error")):
            result = await alert_system.send_system_alert("Test message", "info")
        assert result is False

    @pytest.mark.asyncio
    async def test_activate_kill_switch_already_active(self, alert_system):
        """Test activating an already active kill switch."""
        alert_system.kill_switch_active = True
        result = await alert_system.activate_kill_switch("Test reason")
        assert result is False

    @pytest.mark.asyncio
    async def test_activate_kill_switch_success(self, alert_system, mock_bot):
        """Test successful kill switch activation."""
        alert_system.bot = mock_bot
        with patch("src.loats.alerts.settings") as mock_settings, \
             patch("src.loats.alerts.async_client") as mock_openalgo:
            mock_settings.telegram_chat_id = "test_chat_id"
            mock_openalgo.get_all_orders = AsyncMock(return_value={"data": []})
            mock_openalgo.cancel_order = AsyncMock(return_value={"success": True})

            result = await alert_system.activate_kill_switch("Emergency stop")

        assert result is True
        assert alert_system.kill_switch_active is True

    @pytest.mark.asyncio
    async def test_activate_kill_switch_with_open_orders(self, alert_system, mock_bot):
        """Test kill switch cancels open orders."""
        alert_system.bot = mock_bot
        with patch("src.loats.alerts.settings") as mock_settings, \
             patch("src.loats.alerts.async_client") as mock_openalgo:
            mock_settings.telegram_chat_id = "test_chat_id"
            mock_openalgo.get_all_orders = AsyncMock(return_value={
                "data": [
                    {"order_id": "order1", "status": "OPEN"},
                    {"order_id": "order2", "status": "PENDING"},
                    {"order_id": "order3", "status": "FILLED"},
                ]
            })
            mock_openalgo.cancel_order = AsyncMock(return_value={"success": True})

            result = await alert_system.activate_kill_switch("Emergency stop")

        assert result is True
        assert alert_system.kill_switch_active is True
        assert mock_openalgo.cancel_order.call_count == 2  # Should cancel 2 orders

    @pytest.mark.asyncio
    async def test_activate_kill_switch_exception(self, alert_system):
        """Test kill switch handles exceptions."""
        with patch("src.loats.alerts.async_client") as mock_openalgo:
            mock_openalgo.get_all_orders.side_effect = Exception("API error")
            result = await alert_system.activate_kill_switch("Emergency stop")

        assert result is False
        assert alert_system.kill_switch_active is False

    @pytest.mark.asyncio
    async def test_deactivate_kill_switch_not_active(self, alert_system):
        """Test deactivating an inactive kill switch."""
        result = await alert_system.deactivate_kill_switch("Resume trading")
        assert result is False

    @pytest.mark.asyncio
    async def test_deactivate_kill_switch_success(self, alert_system, mock_bot):
        """Test successful kill switch deactivation."""
        alert_system.kill_switch_active = True
        alert_system.bot = mock_bot
        with patch("src.loats.alerts.settings") as mock_settings:
            mock_settings.telegram_chat_id = "test_chat_id"
            result = await alert_system.deactivate_kill_switch("Resume trading")

        assert result is True
        assert alert_system.kill_switch_active is False

    @pytest.mark.asyncio
    async def test_deactivate_kill_switch_exception(self, alert_system):
        """Test kill switch deactivation handles exceptions."""
        alert_system.kill_switch_active = True
        with patch.object(alert_system, "send_alert", side_effect=Exception("Test error")):
            result = await alert_system.deactivate_kill_switch("Resume trading")
        assert result is False

    @pytest.mark.asyncio
    async def test_send_position_alert_no_positions(self, alert_system, mock_bot):
        """Test position alert when no positions exist."""
        alert_system.bot = mock_bot
        with patch("src.loats.alerts.settings") as mock_settings, \
             patch("src.loats.alerts.async_client") as mock_openalgo:
            mock_settings.telegram_chat_id = "test_chat_id"
            mock_openalgo.get_position_book = AsyncMock(return_value={"data": None})

            result = await alert_system.send_position_alert()
        assert result is True

    @pytest.mark.asyncio
    async def test_send_position_alert_with_positions(self, alert_system, mock_bot):
        """Test position alert with open positions."""
        alert_system.bot = mock_bot
        with patch("src.loats.alerts.settings") as mock_settings, \
             patch("src.loats.alerts.async_client") as mock_openalgo:
            mock_settings.telegram_chat_id = "test_chat_id"
            mock_openalgo.get_position_book = AsyncMock(return_value={
                "data": [
                    {
                        "symbol": "NIFTY",
                        "quantity": 50,
                        "average_price": 18500.0,
                        "last_price": 18550.0,
                        "pnl": 2500.0,
                        "product_type": "MIS",
                    }
                ]
            })

            result = await alert_system.send_position_alert()
        assert result is True

    @pytest.mark.asyncio
    async def test_send_position_alert_exception(self, alert_system):
        """Test position alert handles exceptions."""
        with patch("src.loats.alerts.async_client") as mock_openalgo:
            mock_openalgo.get_position_book.side_effect = Exception("API error")
            result = await alert_system.send_position_alert()
        assert result is False

    @pytest.mark.asyncio
    async def test_send_funds_alert_no_data(self, alert_system, mock_bot):
        """Test funds alert when no data available."""
        alert_system.bot = mock_bot
        with patch("src.loats.alerts.settings") as mock_settings, \
             patch("src.loats.alerts.async_client") as mock_openalgo:
            mock_settings.telegram_chat_id = "test_chat_id"
            mock_openalgo.get_funds = AsyncMock(return_value={"data": None})

            result = await alert_system.send_funds_alert()
        assert result is True

    @pytest.mark.asyncio
    async def test_send_funds_alert_with_data(self, alert_system, mock_bot):
        """Test funds alert with account data."""
        alert_system.bot = mock_bot
        with patch("src.loats.alerts.settings") as mock_settings, \
             patch("src.loats.alerts.async_client") as mock_openalgo:
            mock_settings.telegram_chat_id = "test_chat_id"
            mock_openalgo.get_funds = AsyncMock(return_value={
                "data": {
                    "available_cash": 100000.0,
                    "utilized_margin": 50000.0,
                    "available_margin": 50000.0,
                    "total_equity": 150000.0,
                }
            })

            result = await alert_system.send_funds_alert()
        assert result is True

    @pytest.mark.asyncio
    async def test_send_funds_alert_exception(self, alert_system):
        """Test funds alert handles exceptions."""
        with patch("src.loats.alerts.async_client") as mock_openalgo:
            mock_openalgo.get_funds.side_effect = Exception("API error")
            result = await alert_system.send_funds_alert()
        assert result is False

    @pytest.mark.asyncio
    async def test_start_command_handler(self, alert_system):
        """Test /start command handler."""
        mock_update = MagicMock(spec=Update)
        mock_update.message = MagicMock()
        mock_update.message.reply_text = AsyncMock()
        mock_context = MagicMock()

        await alert_system._start(mock_update, mock_context)
        mock_update.message.reply_text.assert_called_once()

    @pytest.mark.asyncio
    async def test_status_command_handler(self, alert_system):
        """Test /status command handler."""
        mock_update = MagicMock(spec=Update)
        mock_update.message = MagicMock()
        mock_update.message.reply_text = AsyncMock()
        mock_context = MagicMock()

        await alert_system._status(mock_update, mock_context)
        mock_update.message.reply_text.assert_called_once()

    @pytest.mark.asyncio
    async def test_kill_command_handler_already_active(self, alert_system):
        """Test /kill command when kill switch is already active."""
        alert_system.kill_switch_active = True
        mock_update = MagicMock(spec=Update)
        mock_update.message = MagicMock()
        mock_update.message.reply_text = AsyncMock()
        mock_context = MagicMock()

        await alert_system._kill_switch(mock_update, mock_context)
        mock_update.message.reply_text.assert_called_once_with("⚠️ Kill switch is already active.")

    @pytest.mark.asyncio
    async def test_kill_command_handler_with_reason(self, alert_system, mock_bot):
        """Test /kill command with custom reason."""
        alert_system.bot = mock_bot
        mock_update = MagicMock(spec=Update)
        mock_update.message = MagicMock()
        mock_update.message.reply_text = AsyncMock()
        mock_context = MagicMock()
        mock_context.args = ["API", "failure"]

        with patch("src.loats.alerts.settings") as mock_settings, \
             patch("src.loats.alerts.async_client") as mock_openalgo:
            mock_settings.telegram_chat_id = "test_chat_id"
            mock_openalgo.get_all_orders = AsyncMock(return_value={"data": []})
            mock_openalgo.cancel_order = AsyncMock(return_value={"success": True})

            await alert_system._kill_switch(mock_update, mock_context)

        assert alert_system.kill_switch_active is True

    @pytest.mark.asyncio
    async def test_resume_command_handler_not_active(self, alert_system):
        """Test /resume command when kill switch is not active."""
        mock_update = MagicMock(spec=Update)
        mock_update.message = MagicMock()
        mock_update.message.reply_text = AsyncMock()
        mock_context = MagicMock()

        await alert_system._resume(mock_update, mock_context)
        mock_update.message.reply_text.assert_called_once()

    @pytest.mark.asyncio
    async def test_resume_command_handler_success(self, alert_system, mock_bot):
        """Test successful /resume command."""
        alert_system.kill_switch_active = True
        alert_system.bot = mock_bot
        mock_update = MagicMock(spec=Update)
        mock_update.message = MagicMock()
        mock_update.message.reply_text = AsyncMock()
        mock_context = MagicMock()

        with patch("src.loats.alerts.settings") as mock_settings:
            mock_settings.telegram_chat_id = "test_chat_id"
            await alert_system._resume(mock_update, mock_context)

        assert alert_system.kill_switch_active is False

    @pytest.mark.asyncio
    async def test_positions_command_handler(self, alert_system):
        """Test /positions command handler."""
        mock_update = MagicMock(spec=Update)
        mock_update.message = MagicMock()
        mock_update.message.reply_text = AsyncMock()
        mock_context = MagicMock()

        with patch.object(alert_system, "send_position_alert", return_value=True):
            await alert_system._positions(mock_update, mock_context)
            # Should not call reply_text on success
            assert mock_update.message.reply_text.call_count == 0

    @pytest.mark.asyncio
    async def test_positions_command_handler_failure(self, alert_system):
        """Test /positions command handler failure."""
        mock_update = MagicMock(spec=Update)
        mock_update.message = MagicMock()
        mock_update.message.reply_text = AsyncMock()
        mock_context = MagicMock()

        with patch.object(alert_system, "send_position_alert", return_value=False):
            await alert_system._positions(mock_update, mock_context)
        mock_update.message.reply_text.assert_called_once()

    @pytest.mark.asyncio
    async def test_orders_command_handler_no_orders(self, alert_system):
        """Test /orders command when no orders exist."""
        mock_update = MagicMock(spec=Update)
        mock_update.message = MagicMock()
        mock_update.message.reply_text = AsyncMock()
        mock_context = MagicMock()

        with patch("src.loats.alerts.async_client") as mock_openalgo:
            mock_openalgo.get_all_orders = AsyncMock(return_value={"data": None})
            await alert_system._orders(mock_update, mock_context)
        mock_update.message.reply_text.assert_called_once()

    @pytest.mark.asyncio
    async def test_orders_command_handler_with_orders(self, alert_system):
        """Test /orders command with open orders."""
        mock_update = MagicMock(spec=Update)
        mock_update.message = MagicMock()
        mock_update.message.reply_text = AsyncMock()
        mock_context = MagicMock()

        with patch("src.loats.alerts.async_client") as mock_openalgo:
            mock_openalgo.get_all_orders = AsyncMock(return_value={
                "data": [
                    {
                        "order_id": "order1",
                        "symbol": "NIFTY",
                        "order_type": "LIMIT",
                        "transaction_type": "BUY",
                        "quantity": 50,
                        "price": 18500.0,
                        "status": "OPEN",
                    }
                ]
            })
            await alert_system._orders(mock_update, mock_context)
        mock_update.message.reply_text.assert_called_once()

    @pytest.mark.asyncio
    async def test_signals_command_handler_no_signals(self, alert_system):
        """Test /signals command when no signals exist."""
        mock_update = MagicMock(spec=Update)
        mock_update.message = MagicMock()
        mock_update.message.reply_text = AsyncMock()
        mock_context = MagicMock()

        with patch("src.loats.alerts.Database") as mock_db:
            mock_db.return_value.get_latest_signals.return_value = []
            await alert_system._signals(mock_update, mock_context)
        mock_update.message.reply_text.assert_called_once()

    @pytest.mark.asyncio
    async def test_signals_command_handler_with_signals(
        self, alert_system, sample_signal
    ):
        """Test /signals command with recent signals."""
        mock_update = MagicMock(spec=Update)
        mock_update.message = MagicMock()
        mock_update.message.reply_text = AsyncMock()
        mock_context = MagicMock()

        with patch("src.loats.alerts.Database") as mock_db, \
             patch("src.loats.alerts.settings") as mock_settings:
            mock_db.return_value.get_latest_signals.return_value = [sample_signal]
            mock_settings.default_symbol = "NIFTY"
            await alert_system._signals(mock_update, mock_context)
        mock_update.message.reply_text.assert_called_once()

    @pytest.mark.asyncio
    async def test_help_command_handler(self, alert_system):
        """Test /help command handler."""
        mock_update = MagicMock(spec=Update)
        mock_update.message = MagicMock()
        mock_update.message.reply_text = AsyncMock()
        mock_context = MagicMock()

        with patch.object(alert_system, "_start") as mock_start:
            await alert_system._help(mock_update, mock_context)
        mock_start.assert_called_once_with(mock_update, mock_context)

    @pytest.mark.asyncio
    async def test_handle_message_status(self, alert_system):
        """Test handling message with 'status' keyword."""
        mock_update = MagicMock(spec=Update)
        mock_update.message = MagicMock()
        mock_update.message.text = "What's the status?"
        mock_context = MagicMock()

        with patch.object(alert_system, "_status") as mock_status:
            await alert_system._handle_message(mock_update, mock_context)
        mock_status.assert_called_once_with(mock_update, mock_context)

    @pytest.mark.asyncio
    async def test_handle_message_position(self, alert_system):
        """Test handling message with 'position' keyword."""
        mock_update = MagicMock(spec=Update)
        mock_update.message = MagicMock()
        mock_update.message.text = "Show my positions"
        mock_context = MagicMock()

        with patch.object(alert_system, "_positions") as mock_positions:
            await alert_system._handle_message(mock_update, mock_context)
        mock_positions.assert_called_once_with(mock_update, mock_context)

    @pytest.mark.asyncio
    async def test_handle_message_order(self, alert_system):
        """Test handling message with 'order' keyword."""
        mock_update = MagicMock(spec=Update)
        mock_update.message = MagicMock()
        mock_update.message.text = "Check my orders"
        mock_context = MagicMock()

        with patch.object(alert_system, "_orders") as mock_orders:
            await alert_system._handle_message(mock_update, mock_context)
        mock_orders.assert_called_once_with(mock_update, mock_context)

    @pytest.mark.asyncio
    async def test_handle_message_signal(self, alert_system):
        """Test handling message with 'signal' keyword."""
        mock_update = MagicMock(spec=Update)
        mock_update.message = MagicMock()
        mock_update.message.text = "Any new signals?"
        mock_context = MagicMock()

        with patch.object(alert_system, "_signals") as mock_signals:
            await alert_system._handle_message(mock_update, mock_context)
        mock_signals.assert_called_once_with(mock_update, mock_context)

    @pytest.mark.asyncio
    async def test_handle_message_kill(self, alert_system):
        """Test handling message with 'kill' keyword."""
        mock_update = MagicMock(spec=Update)
        mock_update.message = MagicMock()
        mock_update.message.text = "Kill trading now"
        mock_context = MagicMock()

        with patch.object(alert_system, "_kill_switch") as mock_kill:
            await alert_system._handle_message(mock_update, mock_context)
        mock_kill.assert_called_once_with(mock_update, mock_context)

    @pytest.mark.asyncio
    async def test_handle_message_resume(self, alert_system):
        """Test handling message with 'resume' keyword."""
        mock_update = MagicMock(spec=Update)
        mock_update.message = MagicMock()
        mock_update.message.text = "Resume trading"
        mock_context = MagicMock()

        with patch.object(alert_system, "_resume") as mock_resume:
            await alert_system._handle_message(mock_update, mock_context)
        mock_resume.assert_called_once_with(mock_update, mock_context)

    @pytest.mark.asyncio
    async def test_handle_message_unknown(self, alert_system):
        """Test handling unknown message."""
        mock_update = MagicMock(spec=Update)
        mock_update.message = MagicMock()
        mock_update.message.text = "I don't understand this"
        mock_update.message.reply_text = AsyncMock()
        mock_context = MagicMock()

        await alert_system._handle_message(mock_update, mock_context)
        mock_update.message.reply_text.assert_called_once()
