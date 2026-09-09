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

    # The patched create_task never scheduled the start_polling()
    # coroutine; close it to avoid "coroutine was never awaited"
    # RuntimeWarning (F6-L-04 class defect).
    polling_coro = mock_create_task.call_args[0][0]
    polling_coro.close()


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


def _make_context(args=None):
    """Context mock with an explicit args list (auto-attr MagicMock would
    make ``context.args`` truthy and break ``" ".join(...)`` paths)."""
    ctx = MagicMock()
    ctx.args = [] if args is None else args
    return ctx


class TestTelegramCommandHandlers:
    """Operator command-surface tests (F8-H-04 follow-up).

    Covers the Telegram control handlers that the 09Sep branch-coverage
    artifact showed uncovered: /kill, /resume, /positions, /orders,
    /signals, /help, _handle_message routing, and signal/order formatter
    edge branches. kill/resume are the highest-consequence paths in the
    module (they gate all trading).
    """

    @pytest.fixture
    def alert_system(self):
        system = AlertSystem()
        system.bot = AsyncMock()
        return system

    @staticmethod
    def _make_update(message=True, user_id="999", text=None):
        update = MagicMock()
        update.effective_user = MagicMock()
        update.effective_user.id = user_id
        update.message = AsyncMock() if message else None
        if text is not None:
            update.message.text = text
        return update

    # ---------- /kill ----------

    @pytest.mark.asyncio
    async def test_kill_unauthorized_rejected(self, alert_system):
        with patch("loats.alerts.settings") as m:
            m.telegram_admin_ids = []
            update = self._make_update()
            await alert_system._kill_switch(update, _make_context())
            text = update.message.reply_text.call_args.args[0]
            assert "not authorized" in text
            assert alert_system.kill_switch_active is False

    @pytest.mark.asyncio
    async def test_kill_idempotent_rejects_second_activation(self, alert_system):
        alert_system.kill_switch_active = True
        with patch("loats.alerts.settings") as m:
            m.telegram_admin_ids = ["999"]
            update = self._make_update()
            await alert_system._kill_switch(update, _make_context())
            assert "already active" in update.message.reply_text.call_args.args[0]

    @pytest.mark.asyncio
    async def test_kill_success_activates_cancels_and_confirms(self, alert_system):
        with (
            patch("loats.alerts.settings") as m,
            patch("loats.alerts.async_client", new_callable=AsyncMock) as mock_client,
        ):
            m.telegram_admin_ids = ["999"]
            m.telegram_chat_id = "chat1"
            mock_client.get_all_orders.return_value = {
                "data": [
                    {"order_id": "1", "status": "OPEN"},
                    {"order_id": "2", "status": "PENDING"},
                    {"order_id": "3", "status": "FILLED"},
                ]
            }
            update = self._make_update()
            await alert_system._kill_switch(update, _make_context())
            assert alert_system.kill_switch_active is True
            cancelled = [c.args[0] for c in mock_client.cancel_order.await_args_list]
            assert cancelled == ["1", "2"]
            assert (
                "activated successfully"
                in (update.message.reply_text.call_args.args[0])
            )

    @pytest.mark.asyncio
    async def test_kill_fetch_failure_rolls_back(self, alert_system):
        with (
            patch("loats.alerts.settings") as m,
            patch("loats.alerts.async_client", new_callable=AsyncMock) as mock_client,
        ):
            m.telegram_admin_ids = ["999"]
            mock_client.get_all_orders.return_value = None
            update = self._make_update()
            await alert_system._kill_switch(update, _make_context())
            assert alert_system.kill_switch_active is False
            assert "Failed to activate" in (update.message.reply_text.call_args.args[0])

    @pytest.mark.asyncio
    async def test_kill_handler_exception_reports_error(self, alert_system):
        with patch("loats.alerts.settings") as m:
            m.telegram_admin_ids = ["999"]
            update = self._make_update()
            with patch.object(
                AlertSystem,
                "activate_kill_switch",
                AsyncMock(side_effect=RuntimeError("boom")),
            ):
                await alert_system._kill_switch(update, _make_context())
            assert "Error:" in update.message.reply_text.call_args.args[0]

    # ---------- /resume ----------

    @pytest.mark.asyncio
    async def test_resume_unauthorized_rejected(self, alert_system):
        with patch("loats.alerts.settings") as m:
            m.telegram_admin_ids = []
            update = self._make_update()
            await alert_system._resume(update, _make_context())
            assert "not authorized" in update.message.reply_text.call_args.args[0]

    @pytest.mark.asyncio
    async def test_resume_without_active_switch_is_noop(self, alert_system):
        with patch("loats.alerts.settings") as m:
            m.telegram_admin_ids = ["999"]
            update = self._make_update()
            await alert_system._resume(update, _make_context())
            assert "not active" in update.message.reply_text.call_args.args[0]
            assert alert_system.kill_switch_active is False

    @pytest.mark.asyncio
    async def test_resume_success_deactivates_and_confirms(self, alert_system):
        alert_system.kill_switch_active = True
        with patch("loats.alerts.settings") as m:
            m.telegram_admin_ids = ["999"]
            m.telegram_chat_id = "chat1"
            update = self._make_update()
            await alert_system._resume(update, _make_context())
            assert alert_system.kill_switch_active is False
            assert (
                "deactivated successfully"
                in (update.message.reply_text.call_args.args[0])
            )

    # ---------- /positions, /orders, /signals, /help ----------

    @pytest.mark.asyncio
    async def test_positions_failure_reports_error(self):
        system = AlertSystem()  # no bot: every send path fails closed
        with patch("loats.alerts.async_client", new_callable=AsyncMock) as mock_client:
            mock_client.get_position_book.return_value = None
            update = self._make_update()
            await system._positions(update, _make_context())
            assert (
                "Failed to get positions"
                in (update.message.reply_text.call_args.args[0])
            )

    @pytest.mark.asyncio
    async def test_orders_empty_reports_none(self, alert_system):
        with patch("loats.alerts.async_client", new_callable=AsyncMock) as mock_client:
            mock_client.get_all_orders.return_value = {"data": []}
            update = self._make_update()
            await alert_system._orders(update, _make_context())
            assert "No open orders" in update.message.reply_text.call_args.args[0]

    @pytest.mark.asyncio
    async def test_orders_renders_open_order_row(self, alert_system):
        with patch("loats.alerts.async_client", new_callable=AsyncMock) as mock_client:
            mock_client.get_all_orders.return_value = {
                "data": [
                    {
                        "order_id": "O-1",
                        "symbol": "NIFTY",
                        "order_type": "LIMIT",
                        "transaction_type": "BUY",
                        "quantity": 50,
                        "price": "18550.25",
                        "status": "OPEN",
                    }
                ]
            }
            update = self._make_update()
            await alert_system._orders(update, _make_context())
            text = update.message.reply_text.call_args.args[0]
            assert "O-1" in text and "NIFTY" in text and "18550.25" in text

    @pytest.mark.asyncio
    async def test_signals_empty_reports_none(self, alert_system):
        alert_system._explicit_db = AsyncMock()
        alert_system._explicit_db.async_get_latest_signals = AsyncMock(return_value=[])
        update = self._make_update()
        await alert_system._signals(update, _make_context())
        assert "No recent signals" in update.message.reply_text.call_args.args[0]

    @pytest.mark.asyncio
    async def test_signals_renders_recent_rows(self, alert_system):
        from datetime import UTC, datetime

        alert_system._explicit_db = AsyncMock()
        alert_system._explicit_db.async_get_latest_signals = AsyncMock(
            return_value=[
                Signal(
                    symbol="NIFTY",
                    signal_type=SignalType.BUY,
                    strength=0.9,
                    confidence=0.8,
                    indicators={"rsi": 70.0},
                    metadata={},
                    timestamp=datetime.now(UTC),
                )
            ]
        )
        update = self._make_update()
        await alert_system._signals(update, _make_context())
        text = update.message.reply_text.call_args.args[0]
        assert "RECENT SIGNALS" in text and "BUY" in text

    @pytest.mark.asyncio
    async def test_help_delegates_to_start(self, alert_system):
        update = self._make_update()
        await alert_system._help(update, _make_context())
        assert "Available commands" in (update.message.reply_text.call_args.args[0])

    # ---------- _handle_message routing ----------

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("text", "handler"),
        [
            ("status now", "_status"),
            ("my positions", "_positions"),
            ("open orders", "_orders"),
            ("latest signal", "_signals"),
            ("kill it", "_kill_switch"),
            ("resume trading", "_resume"),
        ],
    )
    async def test_handle_message_routes_by_keyword(self, alert_system, text, handler):
        target = AsyncMock()
        update = self._make_update(text=text)
        with patch.object(AlertSystem, handler, target):
            await alert_system._handle_message(update, _make_context())
        target.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_handle_message_unknown_replies_fallback(self, alert_system):
        update = self._make_update(text="hello there")
        await alert_system._handle_message(update, _make_context())
        assert "Didn't understand" in update.message.reply_text.call_args.args[0]

    # ---------- formatter and send edge branches ----------

    @pytest.mark.asyncio
    async def test_send_signal_alert_hold_branch(self, alert_system):
        from datetime import UTC, datetime

        signal = Signal(
            symbol="NIFTY",
            signal_type=SignalType.HOLD,
            strength=0.4,
            confidence=0.5,
            indicators={"rsi": 50.0},
            metadata={},
            timestamp=datetime.now(UTC),
        )
        with patch("loats.alerts.settings") as m:
            m.telegram_chat_id = "chat1"
            assert await alert_system.send_signal_alert(signal) is True

    @pytest.mark.asyncio
    async def test_send_signal_alert_metadata_string_values(self, alert_system):
        from datetime import UTC, datetime

        signal = Signal(
            symbol="NIFTY",
            signal_type=SignalType.SELL,
            strength=0.9,
            confidence=0.8,
            indicators={},
            metadata={"strategy": "test"},
            timestamp=datetime.now(UTC),
        )
        with patch("loats.alerts.settings") as m:
            m.telegram_chat_id = "chat1"
            assert await alert_system.send_signal_alert(signal) is True

    def test_format_alert_message_unknown_type_defaults_info(self, alert_system):
        assert "INFO" in alert_system._format_alert_message("m", "other")

    @pytest.mark.asyncio
    async def test_send_order_alert_unknown_action_defaults_info(self, alert_system):
        from datetime import UTC, datetime

        from loats.models import (
            Order,
            OrderStatus,
            OrderType,
            OrderVariety,
            ProductType,
            TransactionType,
        )

        order = Order(
            order_id="O-9",
            symbol="NIFTY",
            order_type=OrderType.LIMIT,
            transaction_type=TransactionType.BUY,
            quantity=10,
            price=100.0,
            variety=OrderVariety.REGULAR,
            product_type=ProductType.MIS,
            status=OrderStatus.OPEN,
            filled_quantity=0,
            timestamp=datetime.now(UTC),
            stop_loss=None,
            take_profit=None,
            trailing_stop_loss=None,
        )
        with patch("loats.alerts.settings") as m:
            m.telegram_chat_id = "chat1"
            assert await alert_system.send_order_alert(order, "mystery") is True

    @pytest.mark.asyncio
    async def test_send_trade_alert_closed_flat(self, alert_system):
        from datetime import UTC, datetime

        from loats.models import ProductType, Trade, TransactionType

        trade = Trade(
            trade_id="T-1",
            symbol="NIFTY",
            strategy="momentum",
            transaction_type=TransactionType.BUY,
            product_type=ProductType.MIS,
            quantity=10,
            entry_price=100.0,
            status="CLOSED",
            entry_time=datetime.now(UTC),
            exit_price=100.0,
            exit_time=datetime.now(UTC),
            pnl=0.0,
            stop_loss=None,
            take_profit=None,
            trailing_stop_loss=None,
        )
        with patch("loats.alerts.settings") as m:
            m.telegram_chat_id = "chat1"
            assert await alert_system.send_trade_alert(trade, "closed") is True

    @pytest.mark.asyncio
    async def test_send_trade_alert_unknown_action(self, alert_system):
        from datetime import UTC, datetime

        from loats.models import ProductType, Trade, TransactionType

        trade = Trade(
            trade_id="T-2",
            symbol="NIFTY",
            strategy="momentum",
            transaction_type=TransactionType.BUY,
            product_type=ProductType.MIS,
            quantity=10,
            entry_price=100.0,
            status="OPEN",
            entry_time=datetime.now(UTC),
            exit_price=None,
            exit_time=None,
            pnl=None,
            stop_loss=None,
            take_profit=None,
            trailing_stop_loss=None,
        )
        with patch("loats.alerts.settings") as m:
            m.telegram_chat_id = "chat1"
            assert await alert_system.send_trade_alert(trade, "adjusted") is True

    @pytest.mark.asyncio
    async def test_send_funds_alert_missing_data_sends_warning(self, alert_system):
        """No funds data must alert loudly (warning) and report success."""
        with patch("loats.alerts.async_client", new_callable=AsyncMock) as mock_client:
            mock_client.get_funds.return_value = {"data": {}}
            assert await alert_system.send_funds_alert() is True
        assert alert_system.bot.send_message.await_count == 1
        assert (
            "No funds data available"
            in (alert_system.bot.send_message.await_args.kwargs["text"])
        )
