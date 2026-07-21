"""
Alerts module LOATS13July2026.
Implements Telegram alerts kill switch functionality with circuit breaker protection.
"""

import html
from datetime import UTC, datetime
from typing import Any

from telegram import Bot, Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)
from typing import cast

from src.loats.config import settings
from src.loats.database import db
from src.loats.logging import get_logger
from src.loats.models import Order, Signal, SignalType, Trade
from src.loats.openalgo import async_client
from src.loats.utils.circuit_breaker import (
    OPENALGO_CIRCUIT_BREAKER,
    TELEGRAM_CIRCUIT_BREAKER,
    CircuitBreakerOpenError,
)
from src.loats.utils.retry import OPENALGO_RETRY_CONFIG, retry_async

logger = get_logger(__name__)


class AlertSystem:
    """Alert system using Telegram bot notifications and kill switch."""

    def __init__(self) -> None:
        """Initialize AlertSystem."""
        self.bot: Bot | None = None
        self.application: Application = cast(Application, None)
        self.kill_switch_active: bool = False
        self.alert_cooldown: dict[str, datetime] = {}
        self.cooldown_period: int = 300  # 5 minutes
        self._running: bool = False

    async def initialize(self) -> None:
        """Initialize Telegram bot."""
        try:
            if not settings.telegram_bot_token:
                logger.warning(
                    "Telegram bot token not configured. Alerts will not be sent."
                )
                return
            if not settings.telegram_chat_id:
                logger.warning(
                    "Telegram chat ID not configured. Alerts will not be sent."
                )
                return

            self.bot = Bot(token=settings.telegram_bot_token.get_secret_value())
            self.application = Application.builder().bot(self.bot).build()

            self.application.add_handler(CommandHandler("start", self._start))
            self.application.add_handler(CommandHandler("status", self._status))
            self.application.add_handler(CommandHandler("kill", self._kill_switch))
            self.application.add_handler(CommandHandler("resume", self._resume))
            self.application.add_handler(CommandHandler("positions", self._positions))
            self.application.add_handler(CommandHandler("orders", self._orders))
            self.application.add_handler(CommandHandler("signals", self._signals))
            self.application.add_handler(CommandHandler("help", self._help))
            self.application.add_handler(
                MessageHandler(filters.TEXT & ~filters.COMMAND, self._handle_message)
            )

            logger.info("Telegram alert system initialized")
        except Exception as e:
            logger.error(f"Failed to initialize Telegram bot: {e}")
            raise

    async def start(self) -> None:
        """Start Telegram bot in non-blocking mode.

        Uses Application.start() which starts polling in the background,
        allowing other async tasks (like scheduler) to run concurrently.
        """
        if not self.application:
            return
        if self._running:
            logger.warning("Telegram bot already running")
            return
        try:
            # Initialize the application (required before start)
            await self.application.initialize()
            # Start polling in background - this is non-blocking
            await self.application.start()
            self._running = True
            logger.info("Telegram bot started")
        except Exception as e:
            logger.error(f"Failed to start Telegram bot: {e}")
            raise

    async def shutdown(self) -> None:
        """Shutdown Telegram bot gracefully."""
        if not self.application:
            return
        if not self._running:
            return
        try:
            # Stop the application gracefully
            await self.application.stop()
            self._running = False
            logger.info("Telegram bot shutdown complete")
        except Exception as e:
            logger.error(f"Error shutting down Telegram bot: {e}")
            raise

    async def _safe_send_message(
        self, chat_id: str, text: str, parse_mode: str = "HTML"
    ) -> bool:
        """Send message with circuit breaker and retry protection."""
        if not self.bot:
            return False

        # Capture bot reference to ensure type narrowing in lambda
        bot: Bot = self.bot
        try:
            await TELEGRAM_CIRCUIT_BREAKER.call_async(
                retry_async(OPENALGO_RETRY_CONFIG)(
                    lambda: bot.send_message(
                        chat_id=chat_id,
                        text=text,
                        parse_mode=parse_mode,
                    )
                )
            )
            return True
        except CircuitBreakerOpenError as e:
            logger.warning("Telegram circuit breaker open: %s", e)
            return False
        except Exception as e:
            logger.error("Failed to send Telegram message after retries: %s", e)
            return False

    async def send_alert(self, message: str, alert_type: str = "info") -> bool:
        """Send alert via Telegram with circuit breaker protection."""
        if not self.bot or not settings.telegram_chat_id:
            logger.debug(f"Alert not sent (bot not configured): {message}")
            return False

        # Check cooldown
        now = datetime.now(UTC)
        if alert_type in self.alert_cooldown:
            if (
                now - self.alert_cooldown[alert_type]
            ).total_seconds() < self.cooldown_period:
                logger.debug(f"Alert cooldown active for {alert_type}: {message}")
                return False

        try:
            formatted_message = self._format_alert_message(message, alert_type)
            success = await self._safe_send_message(
                chat_id=settings.telegram_chat_id,
                text=formatted_message,
                parse_mode="HTML",
            )
            if success:
                self.alert_cooldown[alert_type] = now
                logger.info(f"Alert sent: [{alert_type}] {message}")
            return success
        except Exception as e:
            logger.error(f"Failed to send alert: {e}")
            return False

    def _format_alert_message(self, message: str, alert_type: str) -> str:
        timestamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
        if alert_type == "warning":
            return f"⚠️ <b>WARNING</b> [{timestamp}]\n\n{message}"
        elif alert_type == "error":
            return f"🚨 <b>ERROR</b> [{timestamp}]\n\n{message}"
        elif alert_type == "success":
            return f"✅ <b>SUCCESS</b> [{timestamp}]\n\n{message}"
        else:
            return f"ℹ️ <b>INFO</b> [{timestamp}]\n\n{message}"

    async def send_signal_alert(self, signal: Signal) -> bool:
        """Send alert for trading signal."""
        try:
            if signal.signal_type == SignalType.BUY:
                alert_type = "success"
                emoji = "🟢"
            elif signal.signal_type == SignalType.SELL:
                alert_type = "warning"
                emoji = "🔴"
            else:
                alert_type = "info"
                emoji = "⚪"

            indicators = "\n".join(
                [f"{name}: {value:.4f}" for name, value in signal.indicators.items()]
            )
            metadata = "\n".join(
                [
                    f"{key}: {value}"
                    for key, value in signal.metadata.items()
                    if key != "indicators_count"
                ]
            )

            message = (
                f"{emoji} <b>TRADING SIGNAL</b> {emoji}\n\n"
                f"<b>Symbol:</b> {signal.symbol}\n"
                f"<b>Type:</b> {signal.signal_type.value}\n"
                f"<b>Strength:</b> {signal.strength:.2f}\n"
                f"<b>Confidence:</b> {signal.confidence:.2f}\n"
                f"<b>Timestamp:</b> {signal.timestamp.strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                f"<b>Indicators:</b>\n{indicators}\n\n"
                f"<b>Metadata:</b>\n{metadata}"
            )
            return await self.send_alert(message, alert_type)
        except Exception as e:
            logger.error(f"Failed to format signal alert: {e}")
            return False

    async def send_order_alert(self, order: Order, action: str = "created") -> bool:
        """Send alert for order."""
        try:
            if action == "filled":
                alert_type = "success"
                emoji = "🎯"
            elif action == "cancelled":
                alert_type = "warning"
                emoji = "❌"
            elif action == "rejected":
                alert_type = "error"
                emoji = "🚫"
            else:
                alert_type = "info"
                emoji = "📝"

            price_str = f"{order.price}" if order.price else "MARKET"

            message = (
                f"{emoji} <b>ORDER {action.upper()}</b> {emoji}\n\n"
                f"<b>Order ID:</b> {order.order_id}\n"
                f"<b>Symbol:</b> {order.symbol}\n"
                f"<b>Type:</b> {order.order_type.value}\n"
                f"<b>Transaction:</b> {order.transaction_type.value}\n"
                f"<b>Quantity:</b> {order.quantity}\n"
                f"<b>Price:</b> {price_str}\n"
                f"<b>Status:</b> {order.status.value}\n"
                f"<b>Filled:</b> {order.filled_quantity}/{order.quantity}\n"
                f"<b>Timestamp:</b> {order.timestamp.strftime('%Y-%m-%d %H:%M:%S')}"
            )

            if order.stop_loss:
                message += f"\n<b>Stop Loss:</b> {order.stop_loss}"
            if order.take_profit:
                message += f"\n<b>Take Profit:</b> {order.take_profit}"
            if order.trailing_stop_loss:
                message += f"\n<b>Trailing Stop:</b> {order.trailing_stop_loss}"

            return await self.send_alert(message, alert_type)
        except Exception as e:
            logger.error(f"Failed to format order alert: {e}")
            return False

    async def send_trade_alert(self, trade: Trade, action: str = "opened") -> bool:
        """Send alert for trade."""
        try:
            if action == "closed":
                if trade.pnl is not None and trade.pnl >= 0:
                    alert_type = "success"
                    emoji = "💰"
                elif trade.pnl is not None and trade.pnl < 0:
                    alert_type = "error"
                    emoji = "💸"
                else:
                    alert_type = "info"
                    emoji = "🔄"
            elif action == "opened":
                alert_type = "info"
                emoji = "📈"
            else:
                alert_type = "info"
                emoji = "🔄"

            message = (
                f"{emoji} <b>TRADE {action.upper()}</b> {emoji}\n\n"
                f"<b>Trade ID:</b> {trade.trade_id}\n"
                f"<b>Symbol:</b> {trade.symbol}\n"
                f"<b>Strategy:</b> {trade.strategy}\n"
                f"<b>Type:</b> {(trade.transaction_type.value if trade.transaction_type else 'N/A')}\n"
                f"<b>Quantity:</b> {trade.quantity}\n"
                f"<b>Entry Price:</b> {trade.entry_price:.2f}\n"
                f"<b>Status:</b> {trade.status}\n"
                f"<b>Entry Time:</b> {trade.entry_time.strftime('%Y-%m-%d %H:%M:%S')}"
            )

            if trade.exit_price:
                message += f"\n<b>Exit Price:</b> {trade.exit_price:.2f}"
            if trade.exit_time:
                message += f"\n<b>Exit Time:</b> {trade.exit_time.strftime('%Y-%m-%d %H:%M:%S')}"
            if trade.pnl is not None:
                pnl_color = "green" if trade.pnl >= 0 else "red"
                message += (
                    f"\n<b>PnL:</b> <span color='{pnl_color}'>{trade.pnl:.2f}</span>"
                )
            if trade.stop_loss:
                message += f"\n<b>Stop Loss:</b> {trade.stop_loss:.2f}"
            if trade.take_profit:
                message += f"\n<b>Take Profit:</b> {trade.take_profit:.2f}"
            if trade.trailing_stop_loss:
                message += f"\n<b>Trailing Stop:</b> {trade.trailing_stop_loss:.2f}"

            return await self.send_alert(message, alert_type)
        except Exception as e:
            logger.error(f"Failed to format trade alert: {e}")
            return False

    async def send_system_alert(self, message: str, alert_type: str = "info") -> bool:
        """Send system-level alert."""
        try:
            header = {
                "warning": "⚠️ SYSTEM WARNING",
                "error": "🚨 SYSTEM ERROR",
                "success": "✅ SYSTEM UPDATE",
                "info": "ℹ️ SYSTEM INFO",
            }.get(alert_type, "ℹ️ SYSTEM ALERT")
            full_message = f"{header}\n\n{message}"
            return await self.send_alert(full_message, alert_type)
        except Exception as e:
            logger.error(f"Failed to format system alert: {e}")
            return False

    async def _safe_get_position_book(self) -> dict[str, Any] | None:
        """Get position book with circuit breaker and retry protection."""
        try:
            return await OPENALGO_CIRCUIT_BREAKER.call_async(  # type: ignore[no-any-return]
                retry_async(OPENALGO_RETRY_CONFIG)(
                    lambda: async_client.get_position_book()
                )
            )
        except CircuitBreakerOpenError as e:
            logger.warning("OpenAlgo circuit breaker open for get_position_book: %s", e)
            return None
        except Exception as e:
            logger.error("Failed to get position book after retries: %s", e)
            return None

    async def _safe_get_funds(self) -> dict[str, Any] | None:
        """Get funds with circuit breaker and retry protection."""
        try:
            return await OPENALGO_CIRCUIT_BREAKER.call_async(  # type: ignore[no-any-return]
                retry_async(OPENALGO_RETRY_CONFIG)(lambda: async_client.get_funds())
            )
        except CircuitBreakerOpenError as e:
            logger.warning("OpenAlgo circuit breaker open for get_funds: %s", e)
            return None
        except Exception as e:
            logger.error("Failed to get funds after retries: %s", e)
            return None

    async def send_position_alert(self) -> bool:
        """Send alert for current positions."""
        try:
            position_data = await self._safe_get_position_book()
            if not position_data or not position_data.get("data"):
                return await self.send_system_alert("No open positions found", "info")

            positions = position_data["data"]
            message = "📊 <b>CURRENT POSITIONS</b>\n\n"
            for pos in positions:
                pnl_color = "green" if pos.get("pnl", 0) >= 0 else "red"
                message += (
                    f"<b>Symbol:</b> {pos['symbol']}\n"
                    f"<b>Quantity:</b> {pos['quantity']}\n"
                    f"<b>Avg Price:</b> {pos['average_price']:.2f}\n"
                    f"<b>Last Price:</b> {pos['last_price']:.2f}\n"
                    f"<b>PnL:</b> <span color='{pnl_color}'>{pos.get('pnl', 0):.2f}</span>\n"
                    f"<b>Product:</b> {pos['product_type']}\n\n"
                )
            return await self.send_alert(message, "info")
        except Exception as e:
            logger.error(f"Failed to get positions alert: {e}")
            return False

    async def send_funds_alert(self) -> bool:
        """Send alert for current funds."""
        try:
            funds_data = await self._safe_get_funds()
            if not funds_data or not funds_data.get("data"):
                return await self.send_system_alert(
                    "No funds data available", "warning"
                )

            funds = funds_data["data"]
            message = (
                f"💵 <b>ACCOUNT FUNDS</b>\n\n"
                f"<b>Available Cash:</b> {funds['available_cash']:.2f}\n"
                f"<b>Utilized Margin:</b> {funds['utilized_margin']:.2f}\n"
                f"<b>Available Margin:</b> {funds['available_margin']:.2f}\n"
                f"<b>Total Equity:</b> {funds['total_equity']:.2f}\n"
            )
            return await self.send_alert(message, "info")
        except Exception as e:
            logger.error(f"Failed to get funds alert: {e}")
            return False

    async def _safe_get_all_orders(self) -> dict[str, Any] | None:
        """Get all orders with circuit breaker and retry protection."""
        try:
            return await OPENALGO_CIRCUIT_BREAKER.call_async(  # type: ignore[no-any-return]
                retry_async(OPENALGO_RETRY_CONFIG)(
                    lambda: async_client.get_all_orders()
                )
            )
        except CircuitBreakerOpenError as e:
            logger.warning("OpenAlgo circuit breaker open for get_all_orders: %s", e)
            return None
        except Exception as e:
            logger.error("Failed to get all orders after retries: %s", e)
            return None

    async def _safe_cancel_order(self, order_id: str) -> bool:
        """Cancel order with circuit breaker and retry protection."""
        try:
            await OPENALGO_CIRCUIT_BREAKER.call_async(
                retry_async(OPENALGO_RETRY_CONFIG)(
                    lambda: async_client.cancel_order(order_id)
                )
            )
            return True
        except CircuitBreakerOpenError as e:
            logger.warning("OpenAlgo circuit breaker open for cancel_order: %s", e)
            return False
        except Exception as e:
            logger.error("Failed to cancel order %s after retries: %s", order_id, e)
            return False

    async def activate_kill_switch(self, reason: str = "Manual activation") -> bool:
        """Activate kill switch to stop all trading activities."""
        if self.kill_switch_active:
            logger.warning("Kill switch already active.")
            return False
        try:
            self.kill_switch_active = True
            logger.warning(f"Kill switch activated: {reason}")

            # Cancel all open orders with retry and circuit breaker
            orders_data = await self._safe_get_all_orders()
            if orders_data is None:
                # Could not fetch orders - rollback kill switch
                self.kill_switch_active = False
                logger.error("Failed to fetch orders - kill switch rollback")
                return False

            if orders_data.get("data"):
                orders = orders_data["data"]
                for order in orders:
                    if order["status"] in ["OPEN", "PENDING"]:
                        await self._safe_cancel_order(order["order_id"])

            message = (
                f"🚨 <b>KILL SWITCH ACTIVATED</b> 🚨\n\n"
                f"<b>Reason:</b> {reason}\n"
                f"<b>Timestamp:</b> {datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                "All open orders cancelled. No new orders will be placed."
            )
            return await self.send_alert(message, "error")
        except Exception as e:
            logger.error(f"Failed to activate kill switch: {e}")
            self.kill_switch_active = False
            return False

    async def deactivate_kill_switch(self, reason: str = "Manual deactivation") -> bool:
        """Deactivate kill switch to resume trading activities."""
        if not self.kill_switch_active:
            logger.warning("Kill switch not active.")
            return False
        try:
            self.kill_switch_active = False
            logger.info(f"Kill switch deactivated: {reason}")
            message = (
                f"<b>KILL SWITCH DEACTIVATED</b> ✅\n\n"
                f"<b>Reason:</b> {reason}\n"
                f"<b>Timestamp:</b> {datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                "Trading activities can now resume."
            )
            return await self.send_alert(message, "success")
        except Exception as e:
            logger.error(f"Failed to deactivate kill switch: {e}")
            return False

    def is_kill_switch_active(self) -> bool:
        """Check if kill switch is active."""
        return self.kill_switch_active

    def get_circuit_breaker_status(self) -> dict[str, Any]:
        """Get circuit breaker status for monitoring.

        Returns:
            Dictionary with OpenAlgo and Telegram circuit breaker status
        """
        return {
            "openalgo": OPENALGO_CIRCUIT_BREAKER.get_status(),
            "telegram": TELEGRAM_CIRCUIT_BREAKER.get_status(),
        }

    def _is_authorized_admin(self, update: Update) -> bool:
        """Check if user is authorized admin based on telegram_admin_ids setting."""
        if not settings.telegram_admin_ids:
            # No admin list configured - reject all commands for safety
            logger.warning(
                "Telegram admin ID allow-list is empty. "
                "Configure TELEGRAM_ADMIN_IDS for security."
            )
            return False

        if not update.effective_user:
            return False

        user_id = str(update.effective_user.id)
        return user_id in settings.telegram_admin_ids

    # Telegram command handlers
    async def _start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /start command."""
        try:
            message = (
                "📈 <b>LOATS13July2026 Trading System</b> 📈\n\n"
                "Welcome to LOATS trading system alert bot!\n\n"
                "Available commands:\n"
                "/status - Get system status\n"
                "/positions - View current positions\n"
                "/orders - View open orders\n"
                "/signals - View recent signals\n"
                "/kill - Activate kill switch\n"
                "/resume - Resume trading\n"
                "/help - Show help message"
            )
            if update.message:
                await update.message.reply_text(message, parse_mode="HTML")
        except Exception as e:
            logger.error(f"Error in /start command: {e}")

    async def _status(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /status command."""
        try:
            status = (
                "🟢 ACTIVE" if not self.kill_switch_active else "🔴 KILL SWITCH ACTIVE"
            )
            message = (
                f"📊 <b>SYSTEM STATUS</b>\n\n"
                f"<b>Status:</b> {status}\n"
                f"<b>Timestamp:</b> {datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S')}"
            )
            if update.message:
                await update.message.reply_text(message, parse_mode="HTML")
        except Exception as e:
            logger.error(f"Error in /status command: {e}")

    async def _kill_switch(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle /kill command."""
        try:
            # Check admin authorization
            if not self._is_authorized_admin(update):
                logger.warning(
                    f"Unauthorized kill switch attempt from user: "
                    f"{update.effective_user.id if update.effective_user else 'unknown'}"
                )
                if update.message:
                    await update.message.reply_text(
                        "⛔ Unauthorized: You are not authorized to issue this command. "
                        "Configure TELEGRAM_ADMIN_IDS with your user ID."
                    )
                return

            if self.kill_switch_active:
                if update.message:
                    await update.message.reply_text("⚠️ Kill switch is already active.")
                return

            reason = (
                html.escape(" ".join(context.args))
                if context.args
                else "Manual activation via Telegram"
            )
            success = await self.activate_kill_switch(reason)
            if update.message:
                if success:
                    await update.message.reply_text(
                        "🚨 Kill switch activated successfully."
                    )
                else:
                    await update.message.reply_text("Failed to activate kill switch.")
        except Exception as e:
            logger.error(f"Error in /kill command: {e}")
            if update.message:
                await update.message.reply_text(f"❌ Error: {e!s}")

    async def _resume(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /resume command."""
        try:
            # Check admin authorization
            if not self._is_authorized_admin(update):
                logger.warning(
                    f"Unauthorized resume attempt from user: "
                    f"{update.effective_user.id if update.effective_user else 'unknown'}"
                )
                if update.message:
                    await update.message.reply_text(
                        "⛔ Unauthorized: You are not authorized to issue this command. "
                        "Configure TELEGRAM_ADMIN_IDS with your user ID."
                    )
                return

            if not self.kill_switch_active:
                if update.message:
                    await update.message.reply_text("ℹ️ Kill switch is not active.")
                return

            reason = (
                html.escape(" ".join(context.args))
                if context.args
                else "Manual deactivation via Telegram"
            )
            success = await self.deactivate_kill_switch(reason)
            if update.message:
                if success:
                    await update.message.reply_text(
                        "✅ Kill switch deactivated successfully."
                    )
                else:
                    await update.message.reply_text("Failed to deactivate kill switch.")
        except Exception as e:
            logger.error(f"Error in /resume command: {e}")
            if update.message:
                await update.message.reply_text(f"❌ Error: {e!s}")

    async def _positions(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle /positions command."""
        try:
            success = await self.send_position_alert()
            if not success and update.message:
                await update.message.reply_text("Failed to get positions.")
        except Exception as e:
            logger.error(f"Error in /positions command: {e}")
            if update.message:
                await update.message.reply_text(f"❌ Error: {e!s}")

    async def _orders(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /orders command."""
        try:
            orders_data = await self._safe_get_all_orders()
            if not orders_data or not orders_data.get("data"):
                if update.message:
                    await update.message.reply_text("ℹ️ No open orders found.")
                return

            orders = orders_data["data"]
            message = "📋 <b>OPEN ORDERS</b>\n\n"
            for order in orders:
                if order["status"] in ["OPEN", "PENDING"]:
                    message += (
                        f"<b>Order ID:</b> {order['order_id']}\n"
                        f"<b>Symbol:</b> {order['symbol']}\n"
                        f"<b>Type:</b> {order['order_type']}\n"
                        f"<b>Transaction:</b> {order['transaction_type']}\n"
                        f"<b>Quantity:</b> {order['quantity']}\n"
                        f"<b>Price:</b> {order.get('price', 'MARKET')}\n"
                        f"<b>Status:</b> {order['status']}\n\n"
                    )

            if update.message:
                await update.message.reply_text(message, parse_mode="HTML")
        except Exception as e:
            logger.error(f"Error in /orders command: {e}")
            if update.message:
                await update.message.reply_text(f"❌ Error: {e!s}")

    async def _signals(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle /signals command."""
        try:
            signals = db.get_latest_signals(settings.default_symbol, limit=5)
            if not signals:
                if update.message:
                    await update.message.reply_text("ℹ️ No recent signals found.")
                return

            message = "📈 <b>RECENT SIGNALS</b>\n\n"
            for signal in signals:
                emoji = {
                    SignalType.BUY: "🟢",
                    SignalType.SELL: "🔴",
                    SignalType.HOLD: "⚪",
                    SignalType.NEUTRAL: "⚪",
                }.get(signal.signal_type, "ℹ️")
                message += (
                    f"{emoji} <b>{signal.signal_type.value}</b> (Strength: {signal.strength:.2f})\n"
                    f"<b>Time:</b> {signal.timestamp.strftime('%H:%M:%S')}\n"
                    f"<b>Indicators:</b> {len(signal.indicators)}\n\n"
                )

            if update.message:
                await update.message.reply_text(message, parse_mode="HTML")
        except Exception as e:
            logger.error(f"Error in /signals command: {e}")
            if update.message:
                await update.message.reply_text(f"❌ Error: {e!s}")

    async def _help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /help command."""
        try:
            await self._start(update, context)
        except Exception as e:
            logger.error(f"Error in /help command: {e}")
            if update.message:
                await update.message.reply_text(f"❌ Error: {e!s}")

    async def _handle_message(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle non-command messages."""
        try:
            if update.message and update.message.text:
                message_text = update.message.text.lower()
                if "status" in message_text:
                    await self._status(update, context)
                elif "position" in message_text or "holdings" in message_text:
                    await self._positions(update, context)
                elif "order" in message_text:
                    await self._orders(update, context)
                elif "signal" in message_text:
                    await self._signals(update, context)
                elif "kill" in message_text:
                    await self._kill_switch(update, context)
                elif "resume" in message_text or "start" in message_text:
                    await self._resume(update, context)
                else:
                    if update.message:
                        await update.message.reply_text(
                            "ℹ️ Didn't understand that. Type /help to see available commands."
                        )
        except Exception as e:
            logger.error(f"Error handling message: {e}")
            if update.message:
                await update.message.reply_text(f"❌ Error: {e!s}")


# Export a default instance
alerts = AlertSystem()
