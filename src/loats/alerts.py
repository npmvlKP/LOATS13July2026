"""
Alerts module for LOATS13July2026.
Implements Telegram alerts and kill switch functionality.
"""

import asyncio
from datetime import datetime, timezone

from telegram import Bot, Update  # type: ignore
from telegram.ext import (  # type: ignore
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from .config import settings
from .database import db
from .logging import get_logger
from .models import Order, Signal, SignalType, Trade
from .openalgo import client as openalgo_client

logger = get_logger(__name__)


class AlertSystem:
    """Alert system using Telegram bot for notifications and kill switch."""

    def __init__(self):
        """Initialize AlertSystem."""
        self.bot: Bot | None = None
        self.application: Application | None = None
        self.kill_switch_active = False
        self.alert_cooldown: dict[str, datetime] = {}
        self.cooldown_period = 300  # 5 minutes cooldown between duplicate alerts

    async def initialize(self) -> None:
        """Initialize the Telegram bot."""
        try:
            if not settings.telegram_bot_token.get_secret_value():
                logger.warning(
                    "Telegram bot token not configured. Alerts will not be sent.",
                )
                return

            if not settings.telegram_chat_id:
                logger.warning(
                    "Telegram chat ID not configured. Alerts will not be sent.",
                )
                return

            # Initialize Telegram bot
            self.bot = Bot(token=settings.telegram_bot_token.get_secret_value())
            self.application = Application.builder().bot(self.bot).build()

            # Add command handlers
            self.application.add_handler(CommandHandler("start", self._start))
            self.application.add_handler(CommandHandler("status", self._status))
            self.application.add_handler(CommandHandler("kill", self._kill_switch))
            self.application.add_handler(CommandHandler("resume", self._resume))
            self.application.add_handler(CommandHandler("positions", self._positions))
            self.application.add_handler(CommandHandler("orders", self._orders))
            self.application.add_handler(CommandHandler("signals", self._signals))
            self.application.add_handler(CommandHandler("help", self._help))

            # Add message handler for text commands
            self.application.add_handler(
                MessageHandler(filters.TEXT & ~filters.COMMAND, self._handle_message),
            )

            logger.info("Telegram alert system initialized")

        except Exception as e:
            logger.error(f"Failed to initialize Telegram bot: {e}")
            raise

    async def start(self) -> None:
        """Start the Telegram bot."""
        if self.application:
            try:
                # Start polling in background
                asyncio.create_task(self.application.run_polling())
                logger.info("Telegram bot started")
            except Exception as e:
                logger.error(f"Failed to start Telegram bot: {e}")
                raise

    async def shutdown(self) -> None:
        """Shutdown the Telegram bot."""
        if self.application:
            try:
                await self.application.shutdown()
                logger.info("Telegram bot shutdown complete")
            except Exception as e:
                logger.error(f"Error shutting down Telegram bot: {e}")
                raise

    async def send_alert(self, message: str, alert_type: str = "info") -> bool:
        """
        Send an alert via Telegram.

        Args:
            message: Alert message
            alert_type: Type of alert (info, warning, error, success)

        Returns:
            True if alert was sent successfully, False otherwise
        """
        if not self.bot or not settings.telegram_chat_id:
            logger.debug(f"Alert not sent (bot not configured): {message}")
            return False

        # Check cooldown to avoid spamming
        if alert_type in self.alert_cooldown:
            if (
                datetime.now(timezone.utc) - self.alert_cooldown[alert_type]
            ).total_seconds() < self.cooldown_period:
                logger.debug(f"Alert cooldown active for {alert_type}: {message}")
                return False

        try:
            # Format message based on alert type
            formatted_message = self._format_alert_message(message, alert_type)

            # Send message
            await self.bot.send_message(
                chat_id=settings.telegram_chat_id,
                text=formatted_message,
                parse_mode="HTML",
            )

            # Update cooldown
            self.alert_cooldown[alert_type] = datetime.now(timezone.utc)
            logger.info(f"Alert sent: {alert_type} - {message}")
            return True

        except Exception as e:
            logger.error(f"Failed to send alert: {e}")
            return False

    def _format_alert_message(self, message: str, alert_type: str) -> str:
        """
        Format alert message with appropriate styling.

        Args:
            message: Original message
            alert_type: Type of alert

        Returns:
            Formatted message
        """
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

        if alert_type == "warning":
            return f"⚠️ <b>WARNING</b> | {timestamp}\n\n{message}"
        if alert_type == "error":
            return f"🚨 <b>ERROR</b> | {timestamp}\n\n{message}"
        if alert_type == "success":
            return f"✅ <b>SUCCESS</b> | {timestamp}\n\n{message}"
        # info
        return f"ℹ️ <b>INFO</b> | {timestamp}\n\n{message}"

    async def send_signal_alert(self, signal: Signal) -> bool:
        """
        Send alert for a trading signal.

        Args:
            signal: Signal object

        Returns:
            True if alert was sent successfully
        """
        try:
            # Determine alert type based on signal
            if signal.signal_type == SignalType.BUY:
                alert_type = "success"
                emoji = "🟢"
            elif signal.signal_type == SignalType.SELL:
                alert_type = "warning"
                emoji = "🔴"
            else:
                alert_type = "info"
                emoji = "⚪"

            # Format indicators
            indicators = "\n".join(
                f"  • {name}: {value:.4f}" for name, value in signal.indicators.items()
            )

            # Format metadata
            metadata = "\n".join(
                f"  • {key}: {value}"
                for key, value in signal.metadata.items()
                if key != "indicators_count"
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
        """
        Send alert for an order.

        Args:
            order: Order object
            action: Action performed (created, filled, cancelled, etc.)

        Returns:
            True if alert was sent successfully
        """
        try:
            # Determine alert type based on action and order status
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

            message = (
                f"{emoji} <b>ORDER {action.upper()}</b> {emoji}\n\n"
                f"<b>Order ID:</b> {order.order_id}\n"
                f"<b>Symbol:</b> {order.symbol}\n"
                f"<b>Type:</b> {order.order_type.value}\n"
                f"<b>Transaction:</b> {order.transaction_type.value}\n"
                f"<b>Quantity:</b> {order.quantity}\n"
                f"<b>Price:</b> {order.price or 'MARKET'}\n"
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
        """
        Send alert for a trade.

        Args:
            trade: Trade object
            action: Action performed (opened, closed, updated)

        Returns:
            True if alert was sent successfully
        """
        try:
            # Determine alert type based on action and trade status
            if action == "closed" and trade.pnl and trade.pnl > 0:
                alert_type = "success"
                emoji = "💰"
            elif action == "closed" and trade.pnl and trade.pnl < 0:
                alert_type = "error"
                emoji = "💸"
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
                f"<b>Type:</b> {trade.transaction_type.value}\n"
                f"<b>Quantity:</b> {trade.quantity}\n"
                f"<b>Entry Price:</b> {trade.entry_price:.2f}\n"
                f"<b>Status:</b> {trade.status}\n"
                f"<b>Entry Time:</b> {trade.entry_time.strftime('%Y-%m-%d %H:%M:%S')}"
            )

            if trade.exit_price:
                message += f"\n<b>Exit Price:</b> {trade.exit_price:.2f}"
            if trade.exit_time:
                message += f"\n<b>Exit Time:</b> {trade.exit_time.strftime('%Y-%m-%d %H:%M:%S')}"
            if trade.pnl:
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
        """
        Send system-level alert.

        Args:
            message: Alert message
            alert_type: Type of alert

        Returns:
            True if alert was sent successfully
        """
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

    async def send_position_alert(self) -> bool:
        """
        Send alert with current positions.

        Returns:
            True if alert was sent successfully
        """
        try:
            # Get current positions from OpenAlgo
            with openalgo_client as client:
                position_data = await client.get_position_book()

            if not position_data.get("data"):
                return await self.send_system_alert("No open positions found", "info")

            positions = position_data["data"]
            message = "📊 <b>CURRENT POSITIONS</b>\n\n"

            for pos in positions:
                pnl_color = "green" if pos["pnl"] >= 0 else "red"
                message += (
                    f"<b>Symbol:</b> {pos['symbol']}\n"
                    f"<b>Quantity:</b> {pos['quantity']}\n"
                    f"<b>Avg Price:</b> {pos['average_price']:.2f}\n"
                    f"<b>Last Price:</b> {pos['last_price']:.2f}\n"
                    f"<b>PnL:</b> <span color='{pnl_color}'>{pos['pnl']:.2f}</span>\n"
                    f"<b>Product:</b> {pos['product_type']}\n\n"
                )

            return await self.send_alert(message, "info")

        except Exception as e:
            logger.error(f"Failed to get positions for alert: {e}")
            return False

    async def send_funds_alert(self) -> bool:
        """
        Send alert with current funds.

        Returns:
            True if alert was sent successfully
        """
        try:
            # Get current funds from OpenAlgo
            with openalgo_client as client:
                funds_data = await client.get_funds()

            if not funds_data.get("data"):
                return await self.send_system_alert(
                    "No funds data available",
                    "warning",
                )

            funds = funds_data["data"]
            message = "💵 <b>ACCOUNT FUNDS</b>\n\n"

            message += (
                f"<b>Available Cash:</b> {funds['available_cash']:.2f}\n"
                f"<b>Utilized Margin:</b> {funds['utilized_margin']:.2f}\n"
                f"<b>Available Margin:</b> {funds['available_margin']:.2f}\n"
                f"<b>Total Equity:</b> {funds['total_equity']:.2f}\n"
            )

            return await self.send_alert(message, "info")

        except Exception as e:
            logger.error(f"Failed to get funds for alert: {e}")
            return False

    async def activate_kill_switch(self, reason: str = "Manual activation") -> bool:
        """
        Activate the kill switch to stop all trading activities.

        Args:
            reason: Reason for activation

        Returns:
            True if kill switch was activated successfully
        """
        if self.kill_switch_active:
            logger.warning("Kill switch already active")
            return False

        try:
            self.kill_switch_active = True
            logger.warning(f"Kill switch activated: {reason}")

            # Cancel all open orders
            with openalgo_client as client:
                orders = await client.get_order_status("")  # Get all orders
                for order in orders.get("data", []):
                    if order["status"] in ["OPEN", "PENDING"]:
                        await client.cancel_order(order["order_id"])

            # Send alert
            message = (
                "🚨 <b>KILL SWITCH ACTIVATED</b> 🚨\n\n"
                f"<b>Reason:</b> {reason}\n"
                f"<b>Timestamp:</b> {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                "All open orders have been cancelled. No new orders will be placed."
            )

            return await self.send_alert(message, "error")

        except Exception as e:
            logger.error(f"Failed to activate kill switch: {e}")
            self.kill_switch_active = False
            return False

    async def deactivate_kill_switch(self, reason: str = "Manual deactivation") -> bool:
        """
        Deactivate the kill switch to resume trading activities.

        Args:
            reason: Reason for deactivation

        Returns:
            True if kill switch was deactivated successfully
        """
        if not self.kill_switch_active:
            logger.warning("Kill switch not active")
            return False

        try:
            self.kill_switch_active = False
            logger.info(f"Kill switch deactivated: {reason}")

            # Send alert
            message = (
                "✅ <b>KILL SWITCH DEACTIVATED</b> ✅\n\n"
                f"<b>Reason:</b> {reason}\n"
                f"<b>Timestamp:</b> {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                "Trading activities can now resume."
            )

            return await self.send_alert(message, "success")

        except Exception as e:
            logger.error(f"Failed to deactivate kill switch: {e}")
            return False

    def is_kill_switch_active(self) -> bool:
        """
        Check if kill switch is active.

        Returns:
            True if kill switch is active
        """
        return self.kill_switch_active

    # Telegram command handlers

    async def _start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /start command."""
        try:
            message = (
                "📈 <b>LOATS13July2026 Trading System</b> 📈\n\n"
                "Welcome to the LOATS trading system alert bot!\n\n"
                "Available commands:\n"
                "/status - System status\n"
                "/positions - Current positions\n"
                "/orders - Open orders\n"
                "/signals - Recent signals\n"
                "/kill - Activate kill switch\n"
                "/resume - Resume trading\n"
                "/help - Show this help message"
            )
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
                f"<b>Timestamp:</b> {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')}"
            )
            await update.message.reply_text(message, parse_mode="HTML")
        except Exception as e:
            logger.error(f"Error in /status command: {e}")

    async def _kill_switch(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        """Handle /kill command."""
        try:
            if self.kill_switch_active:
                await update.message.reply_text("⚠️ Kill switch is already active")
                return

            reason = (
                " ".join(context.args)
                if context.args
                else "Manual activation via Telegram"
            )
            success = await self.activate_kill_switch(reason)

            if success:
                await update.message.reply_text("🚨 Kill switch activated successfully")
            else:
                await update.message.reply_text("❌ Failed to activate kill switch")
        except Exception as e:
            logger.error(f"Error in /kill command: {e}")
            await update.message.reply_text(f"❌ Error: {e!s}")

    async def _resume(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /resume command."""
        try:
            if not self.kill_switch_active:
                await update.message.reply_text("ℹ️ Kill switch is not active")
                return

            reason = (
                " ".join(context.args)
                if context.args
                else "Manual deactivation via Telegram"
            )
            success = await self.deactivate_kill_switch(reason)

            if success:
                await update.message.reply_text(
                    "✅ Kill switch deactivated successfully",
                )
            else:
                await update.message.reply_text("❌ Failed to deactivate kill switch")
        except Exception as e:
            logger.error(f"Error in /resume command: {e}")
            await update.message.reply_text(f"❌ Error: {e!s}")

    async def _positions(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        """Handle /positions command."""
        try:
            success = await self.send_position_alert()
            if not success:
                await update.message.reply_text("❌ Failed to get positions")
        except Exception as e:
            logger.error(f"Error in /positions command: {e}")
            await update.message.reply_text(f"❌ Error: {e!s}")

    async def _orders(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /orders command."""
        try:
            # Get open orders from OpenAlgo
            with openalgo_client as client:
                orders_data = await client.get_order_status("")  # Get all orders

            if not orders_data.get("data"):
                await update.message.reply_text("ℹ️ No open orders found")
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

            await update.message.reply_text(message, parse_mode="HTML")
        except Exception as e:
            logger.error(f"Error in /orders command: {e}")
            await update.message.reply_text(f"❌ Error: {e!s}")

    async def _signals(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        """Handle /signals command."""
        try:
            # Get recent signals from database
            signals = db.get_latest_signals(settings.default_symbol, limit=5)

            if not signals:
                await update.message.reply_text("ℹ️ No recent signals found")
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
                    f"{emoji} <b>{signal.signal_type.value}</b> | {signal.strength:.2f}\n"
                    f"<b>Time:</b> {signal.timestamp.strftime('%H:%M:%S')}\n"
                    f"<b>Indicators:</b> {len(signal.indicators)}\n\n"
                )

            await update.message.reply_text(message, parse_mode="HTML")
        except Exception as e:
            logger.error(f"Error in /signals command: {e}")
            await update.message.reply_text(f"❌ Error: {e!s}")

    async def _help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /help command."""
        try:
            await self._start(update, context)
        except Exception as e:
            logger.error(f"Error in /help command: {e}")
            await update.message.reply_text(f"❌ Error: {e!s}")

    async def _handle_message(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        """Handle non-command messages."""
        try:
            message = update.message.text.lower()
            if "status" in message:
                await self._status(update, context)
            elif "position" in message or "holdings" in message:
                await self._positions(update, context)
            elif "order" in message:
                await self._orders(update, context)
            elif "signal" in message:
                await self._signals(update, context)
            elif "kill" in message:
                await self._kill_switch(update, context)
            elif "resume" in message or "start" in message:
                await self._resume(update, context)
            else:
                await update.message.reply_text(
                    "ℹ️ I didn't understand that. Type /help for available commands.",
                )
        except Exception as e:
            logger.error(f"Error handling message: {e}")
            await update.message.reply_text(f"❌ Error: {e!s}")


# Export default instance
alerts = AlertSystem()
