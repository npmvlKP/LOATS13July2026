"""
Database module for LOATS13July2026.
Implements SQLite database with audit trail and JSONL dual-write.
"""

import hashlib
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, TypeVar

import pandas as pd
from pydantic import BaseModel

from .config import settings
from .logging import get_logger
from .models import (
    AuditLogEntry,
    FundsData,
    HistoricalData,
    Order,
    Position,
    QuoteData,
    Signal,
    Trade,
)

logger = get_logger(__name__)
T = TypeVar("T", bound=BaseModel)


class Database:
    """SQLite database with audit trail functionality."""

    def __init__(
        self,
        db_path: Path | None = None,
        audit_log_path: Path | None = None,
        retention_days: int | None = None,
    ):
        """
        Initialize Database.

        Args:
            db_path: Path to SQLite database file
            audit_log_path: Path to audit log JSONL file
            retention_days: Number of days to retain data (defaults to settings)
        """
        self.db_path = db_path or settings.sqlite_db_path
        self.audit_log_path = audit_log_path or settings.audit_log_path
        self.retention_days = retention_days or settings.retention_days

        # Ensure directories exist
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.audit_log_path.parent.mkdir(parents=True, exist_ok=True)

        # Create audit log file if it doesn't exist (touch)
        if not self.audit_log_path.exists():
            self.audit_log_path.touch()

        # Initialize database
        self._initialize_database()

    def initialize(self) -> None:
        """Initialize database schema (public alias for _initialize_database)."""
        self._initialize_database()

    def cleanup(self) -> None:
        """Clean up old data (public alias for _cleanup_old_data)."""
        self._cleanup_old_data()

    def vacuum(self) -> None:
        """Vacuum the database to reclaim space."""
        with self._get_connection() as conn:
            conn.execute("VACUUM")
            conn.commit()

    def _initialize_database(self) -> None:
        """Initialize database schema."""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Create tables if they don't exist
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS trades (
                    trade_id TEXT PRIMARY KEY,
                    symbol TEXT NOT NULL,
                    quantity INTEGER NOT NULL,
                    entry_price REAL NOT NULL,
                    exit_price REAL,
                    entry_time TEXT NOT NULL,
                    exit_time TEXT,
                    transaction_type TEXT NOT NULL,
                    product_type TEXT NOT NULL,
                    pnl REAL,
                    status TEXT NOT NULL,
                    strategy TEXT NOT NULL,
                    stop_loss REAL,
                    take_profit REAL,
                    trailing_stop_loss REAL,
                    metadata TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS signals (
                    signal_id TEXT PRIMARY KEY,
                    symbol TEXT NOT NULL,
                    signal_type TEXT NOT NULL,
                    strength REAL NOT NULL,
                    timestamp TEXT NOT NULL,
                    indicators TEXT NOT NULL,
                    metadata TEXT,
                    confidence REAL,
                    created_at TEXT NOT NULL
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS audit_log (
                    entry_id TEXT PRIMARY KEY,
                    timestamp TEXT NOT NULL,
                    action TEXT NOT NULL,
                    entity_type TEXT NOT NULL,
                    entity_id TEXT NOT NULL,
                    user TEXT NOT NULL,
                    metadata TEXT,
                    previous_state TEXT,
                    new_state TEXT,
                    sha256_hash TEXT NOT NULL
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS historical_data (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    open REAL NOT NULL,
                    high REAL NOT NULL,
                    low REAL NOT NULL,
                    close REAL NOT NULL,
                    volume INTEGER NOT NULL,
                    interval TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(symbol, timestamp, interval)
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS quotes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    last_price REAL NOT NULL,
                    open REAL NOT NULL,
                    high REAL NOT NULL,
                    low REAL NOT NULL,
                    close REAL NOT NULL,
                    volume INTEGER NOT NULL,
                    timestamp TEXT NOT NULL,
                    change REAL NOT NULL,
                    change_percent REAL NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(symbol, timestamp)
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS positions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    quantity INTEGER NOT NULL,
                    average_price REAL NOT NULL,
                    last_price REAL NOT NULL,
                    pnl REAL NOT NULL,
                    product_type TEXT NOT NULL,
                    buy_quantity INTEGER NOT NULL,
                    sell_quantity INTEGER NOT NULL,
                    timestamp TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(symbol, timestamp)
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS funds (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    available_cash REAL NOT NULL,
                    utilized_margin REAL NOT NULL,
                    available_margin REAL NOT NULL,
                    total_equity REAL NOT NULL,
                    timestamp TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(timestamp)
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS orders (
                    order_id TEXT PRIMARY KEY,
                    symbol TEXT NOT NULL,
                    quantity INTEGER NOT NULL,
                    order_type TEXT NOT NULL,
                    price REAL,
                    trigger_price REAL,
                    variety TEXT NOT NULL,
                    transaction_type TEXT NOT NULL,
                    product_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    filled_quantity INTEGER NOT NULL,
                    average_price REAL,
                    stop_loss REAL,
                    take_profit REAL,
                    trailing_stop_loss REAL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)

            # Create indexes for performance
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_trades_symbol ON trades(symbol)",
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_trades_status ON trades(status)",
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_signals_symbol ON signals(symbol)",
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_signals_timestamp ON signals(timestamp)",
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_historical_symbol ON historical_data(symbol)",
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_historical_timestamp ON historical_data(timestamp)",
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_quotes_symbol ON quotes(symbol)",
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_quotes_timestamp ON quotes(timestamp)",
            )

            conn.commit()

    def _get_connection(self) -> sqlite3.Connection:
        """Get a database connection with WAL mode enabled."""
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA temp_store=MEMORY")
        conn.execute("PRAGMA cache_size=-10000")  # 10MB cache
        return conn

    def _model_to_dict(self, model: BaseModel) -> dict[str, Any]:
        """Convert Pydantic model to dictionary."""
        return json.loads(model.model_dump_json())

    def _dict_to_model(self, data: dict[str, Any], model_class: type[T]) -> T:
        """Convert dictionary to Pydantic model."""
        return model_class(**data)

    def _calculate_sha256(self, data: dict[str, Any]) -> str:
        """Calculate SHA-256 hash of a dictionary."""
        data_str = json.dumps(data, sort_keys=True)
        return hashlib.sha256(data_str.encode()).hexdigest()

    def _log_audit(
        self,
        action: str,
        entity_type: str,
        entity_id: str,
        user: str = "system",
        metadata: dict[str, Any] | None = None,
        previous_state: dict[str, Any] | None = None,
        new_state: dict[str, Any] | None = None,
    ) -> None:
        """
        Log an audit entry and write to JSONL file.

        Args:
            action: Action performed
            entity_type: Type of entity
            entity_id: ID of entity
            user: User performing the action
            metadata: Additional metadata
            previous_state: State before the action
            new_state: State after the action
        """
        entry = AuditLogEntry(
            timestamp=datetime.now(timezone.utc),
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            user=user,
            metadata=metadata or {},
            previous_state=previous_state,
            new_state=new_state,
        )

        # Calculate hash over the entry data WITHOUT the sha256_hash field
        entry_data = self._model_to_dict(entry)
        # Remove sha256_hash (currently None) from the data used for hashing
        hash_data = {k: v for k, v in entry_data.items() if k != "sha256_hash"}
        entry.sha256_hash = self._calculate_sha256(hash_data)

        # Re-serialize with the hash set for JSONL
        entry_data = self._model_to_dict(entry)

        # Write to database
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO audit_log (
                    entry_id, timestamp, action, entity_type, entity_id,
                    user, metadata, previous_state, new_state, sha256_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    entry.entry_id,
                    entry.timestamp.isoformat(),
                    entry.action,
                    entry.entity_type,
                    entry.entity_id,
                    entry.user,
                    json.dumps(entry.metadata),
                    json.dumps(entry.previous_state) if entry.previous_state else None,
                    json.dumps(entry.new_state) if entry.new_state else None,
                    entry.sha256_hash,
                ),
            )
            conn.commit()

        # Write to JSONL file (append-only)
        with Path(self.audit_log_path).open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry_data) + "\n")

    def _cleanup_old_data(self) -> None:
        """Clean up data older than retention period.

        Trades are filtered by entry_time, other tables by created_at.
        """
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=self.retention_days)
        cutoff_str = cutoff_date.isoformat()

        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Delete old trades (by entry_time as the business timestamp)
            cursor.execute(
                "DELETE FROM trades WHERE entry_time < ?",
                (cutoff_str,),
            )

            # Delete old signals
            cursor.execute(
                "DELETE FROM signals WHERE created_at < ?",
                (cutoff_str,),
            )

            # Delete old historical data
            cursor.execute(
                "DELETE FROM historical_data WHERE created_at < ?",
                (cutoff_str,),
            )

            # Delete old quotes
            cursor.execute(
                "DELETE FROM quotes WHERE created_at < ?",
                (cutoff_str,),
            )

            conn.commit()

        logger.info(f"Cleaned up data older than {cutoff_str}")

    # ------------------------------------------------------------------
    # Trade CRUD methods
    # ------------------------------------------------------------------

    def create_trade(self, trade: Trade) -> bool:
        """
        Create a new trade record.

        Args:
            trade: Trade model instance

        Returns:
            True if successful
        """
        now = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO trades (
                    trade_id, symbol, quantity, entry_price, exit_price,
                    entry_time, exit_time, transaction_type, product_type,
                    pnl, status, strategy, stop_loss, take_profit,
                    trailing_stop_loss, metadata, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    trade.trade_id,
                    trade.symbol,
                    trade.quantity,
                    trade.entry_price,
                    trade.exit_price,
                    (
                        trade.entry_time.isoformat()
                        if isinstance(trade.entry_time, datetime)
                        else str(trade.entry_time)
                    ),
                    (
                        trade.exit_time.isoformat()
                        if trade.exit_time and isinstance(trade.exit_time, datetime)
                        else trade.exit_time
                    ),
                    trade.transaction_type.value,
                    trade.product_type.value,
                    trade.pnl,
                    trade.status,
                    trade.strategy,
                    trade.stop_loss,
                    trade.take_profit,
                    trade.trailing_stop_loss,
                    json.dumps(trade.metadata) if trade.metadata else None,
                    now,
                    now,
                ),
            )
            conn.commit()

        self._log_audit(
            action="CREATE",
            entity_type="trade",
            entity_id=trade.trade_id,
            new_state=self._model_to_dict(trade),
        )
        return True

    def get_trade(self, trade_id: str) -> Trade | None:
        """
        Retrieve a trade by ID.

        Args:
            trade_id: Trade identifier

        Returns:
            Trade model or None if not found
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM trades WHERE trade_id = ?", (trade_id,))
            row = cursor.fetchone()

        if row is None:
            return None

        return self._row_to_trade(row)

    def update_trade(self, trade: Trade) -> bool:
        """
        Update an existing trade record.

        Args:
            trade: Trade model instance with updated fields

        Returns:
            True if successful
        """
        now = datetime.now(timezone.utc).isoformat()

        # Get previous state for audit
        previous = self.get_trade(trade.trade_id)
        previous_state = self._model_to_dict(previous) if previous else None

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE trades SET
                    symbol = ?, quantity = ?, entry_price = ?, exit_price = ?,
                    entry_time = ?, exit_time = ?, transaction_type = ?,
                    product_type = ?, pnl = ?, status = ?, strategy = ?,
                    stop_loss = ?, take_profit = ?, trailing_stop_loss = ?,
                    metadata = ?, updated_at = ?
                WHERE trade_id = ?
            """,
                (
                    trade.symbol,
                    trade.quantity,
                    trade.entry_price,
                    trade.exit_price,
                    (
                        trade.entry_time.isoformat()
                        if isinstance(trade.entry_time, datetime)
                        else str(trade.entry_time)
                    ),
                    (
                        trade.exit_time.isoformat()
                        if trade.exit_time and isinstance(trade.exit_time, datetime)
                        else trade.exit_time
                    ),
                    trade.transaction_type.value,
                    trade.product_type.value,
                    trade.pnl,
                    trade.status,
                    trade.strategy,
                    trade.stop_loss,
                    trade.take_profit,
                    trade.trailing_stop_loss,
                    json.dumps(trade.metadata) if trade.metadata else None,
                    now,
                    trade.trade_id,
                ),
            )
            conn.commit()

        self._log_audit(
            action="UPDATE",
            entity_type="trade",
            entity_id=trade.trade_id,
            previous_state=previous_state,
            new_state=self._model_to_dict(trade),
        )
        return True

    def get_open_trades(self, symbol: str | None = None) -> list[Trade]:
        """
        Get all open trades, optionally filtered by symbol.

        Args:
            symbol: Optional symbol filter

        Returns:
            List of open Trade models
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if symbol:
                cursor.execute(
                    "SELECT * FROM trades WHERE status = 'OPEN' AND symbol = ? ORDER BY entry_time DESC",
                    (symbol,),
                )
            else:
                cursor.execute(
                    "SELECT * FROM trades WHERE status = 'OPEN' ORDER BY entry_time DESC",
                )
            rows = cursor.fetchall()

        return [self._row_to_trade(row) for row in rows]

    def _row_to_trade(self, row: Any) -> Trade:
        """Convert a database row to Trade model."""
        from src.loats.models import ProductType, TransactionType

        return Trade(
            trade_id=row[0],
            symbol=row[1],
            quantity=row[2],
            entry_price=row[3],
            exit_price=row[4],
            entry_time=datetime.fromisoformat(row[5])
            if row[5]
            else datetime.now(timezone.utc),
            exit_time=datetime.fromisoformat(row[6]) if row[6] else None,
            transaction_type=TransactionType(row[7]),
            product_type=ProductType(row[8]),
            pnl=row[9],
            status=row[10],
            strategy=row[11],
            stop_loss=row[12],
            take_profit=row[13],
            trailing_stop_loss=row[14],
            metadata=json.loads(row[15]) if row[15] else {},
        )

    # ------------------------------------------------------------------
    # Signal CRUD methods
    # ------------------------------------------------------------------

    def create_signal(self, signal: Signal) -> bool:
        """
        Create a new signal record.

        Args:
            signal: Signal model instance

        Returns:
            True if successful
        """
        now = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO signals (
                    signal_id, symbol, signal_type, strength, timestamp,
                    indicators, metadata, confidence, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    signal.signal_id,
                    signal.symbol,
                    signal.signal_type.value,
                    signal.strength,
                    signal.timestamp.isoformat(),
                    json.dumps(signal.indicators),
                    json.dumps(signal.metadata) if signal.metadata else None,
                    signal.confidence,
                    now,
                ),
            )
            conn.commit()

        self._log_audit(
            action="CREATE",
            entity_type="signal",
            entity_id=signal.signal_id,
            new_state=self._model_to_dict(signal),
        )
        return True

    def get_latest_signals(self, symbol: str, limit: int = 10) -> list[Signal]:
        """
        Get latest signals for a symbol.

        Args:
            symbol: Symbol to filter by
            limit: Maximum number of signals to return

        Returns:
            List of Signal models ordered by timestamp descending
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT * FROM signals WHERE symbol = ?
                ORDER BY timestamp DESC LIMIT ?
            """,
                (symbol, limit),
            )
            rows = cursor.fetchall()

        return [self._row_to_signal(row) for row in rows]

    def _row_to_signal(self, row: Any) -> Signal:
        """Convert a database row to Signal model."""
        from src.loats.models import SignalType

        return Signal(
            signal_id=row[0],
            symbol=row[1],
            signal_type=SignalType(row[2]),
            strength=row[3],
            timestamp=datetime.fromisoformat(row[4]),
            indicators=json.loads(row[5]) if row[5] else {},
            metadata=json.loads(row[6]) if row[6] else {},
            confidence=row[7],
        )

    # ------------------------------------------------------------------
    # Historical Data methods
    # ------------------------------------------------------------------

    def store_historical_data(self, data: list[HistoricalData]) -> bool:
        """
        Store historical data records.

        Args:
            data: List of HistoricalData models

        Returns:
            True if successful
        """
        now = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            for item in data:
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO historical_data (
                        symbol, timestamp, open, high, low, close,
                        volume, interval, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        item.symbol,
                        item.timestamp.isoformat(),
                        item.open,
                        item.high,
                        item.low,
                        item.close,
                        item.volume,
                        item.interval,
                        now,
                    ),
                )
            conn.commit()
        return True

    def get_historical_data(
        self,
        symbol: str,
        interval: str,
        start_date: datetime,
        end_date: datetime,
    ) -> list[HistoricalData]:
        """
        Get historical data for a symbol within a date range.

        Args:
            symbol: Symbol to filter by
            interval: Time interval
            start_date: Start of date range
            end_date: End of date range

        Returns:
            List of HistoricalData models
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT symbol, timestamp, open, high, low, close, volume, interval
                FROM historical_data
                WHERE symbol = ? AND interval = ? AND timestamp >= ? AND timestamp <= ?
                ORDER BY timestamp ASC
            """,
                (
                    symbol,
                    interval,
                    start_date.isoformat(),
                    end_date.isoformat(),
                ),
            )
            rows = cursor.fetchall()

        return [
            HistoricalData(
                symbol=row[0],
                timestamp=datetime.fromisoformat(row[1]),
                open=row[2],
                high=row[3],
                low=row[4],
                close=row[5],
                volume=row[6],
                interval=row[7],
            )
            for row in rows
        ]

    # ------------------------------------------------------------------
    # Quote methods
    # ------------------------------------------------------------------

    def store_quote(self, quote: QuoteData) -> bool:
        """
        Store a quote record.

        Args:
            quote: QuoteData model instance

        Returns:
            True if successful
        """
        now = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO quotes (
                    symbol, last_price, open, high, low, close, volume,
                    timestamp, change, change_percent, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    quote.symbol,
                    quote.last_price,
                    quote.open,
                    quote.high,
                    quote.low,
                    quote.close,
                    quote.volume,
                    quote.timestamp.isoformat(),
                    quote.change,
                    quote.change_percent,
                    now,
                ),
            )
            conn.commit()
        return True

    def get_latest_quote(self, symbol: str) -> QuoteData | None:
        """
        Get the latest quote for a symbol.

        Args:
            symbol: Symbol to query

        Returns:
            QuoteData model or None
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT symbol, last_price, open, high, low, close, volume,
                       timestamp, change, change_percent
                FROM quotes WHERE symbol = ?
                ORDER BY timestamp DESC LIMIT 1
            """,
                (symbol,),
            )
            row = cursor.fetchone()

        if row is None:
            return None

        return QuoteData(
            symbol=row[0],
            last_price=row[1],
            open=row[2],
            high=row[3],
            low=row[4],
            close=row[5],
            volume=row[6],
            timestamp=datetime.fromisoformat(row[7]),
            change=row[8],
            change_percent=row[9],
        )

    # ------------------------------------------------------------------
    # Position methods
    # ------------------------------------------------------------------

    def store_position(self, position: Position) -> bool:
        """
        Store a position record.

        Args:
            position: Position model instance

        Returns:
            True if successful
        """
        now = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO positions (
                    symbol, quantity, average_price, last_price, pnl,
                    product_type, buy_quantity, sell_quantity, timestamp, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    position.symbol,
                    position.quantity,
                    position.average_price,
                    position.last_price,
                    position.pnl,
                    position.product_type.value,
                    position.buy_quantity,
                    position.sell_quantity,
                    now,
                    now,
                ),
            )
            conn.commit()
        return True

    def get_position(self, symbol: str) -> Position | None:
        """
        Get the latest position for a symbol.

        Args:
            symbol: Symbol to query

        Returns:
            Position model or None
        """
        from src.loats.models import ProductType

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT symbol, quantity, average_price, last_price, pnl,
                       product_type, buy_quantity, sell_quantity
                FROM positions WHERE symbol = ?
                ORDER BY timestamp DESC LIMIT 1
            """,
                (symbol,),
            )
            row = cursor.fetchone()

        if row is None:
            return None

        return Position(
            symbol=row[0],
            quantity=row[1],
            average_price=row[2],
            last_price=row[3],
            pnl=row[4],
            product_type=ProductType(row[5]),
            buy_quantity=row[6],
            sell_quantity=row[7],
        )

    # ------------------------------------------------------------------
    # Funds methods
    # ------------------------------------------------------------------

    def store_funds(self, funds: FundsData) -> bool:
        """
        Store funds data.

        Args:
            funds: FundsData model instance

        Returns:
            True if successful
        """
        now = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO funds (
                    available_cash, utilized_margin, available_margin,
                    total_equity, timestamp, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
            """,
                (
                    funds.available_cash,
                    funds.utilized_margin,
                    funds.available_margin,
                    funds.total_equity,
                    funds.timestamp.isoformat(),
                    now,
                ),
            )
            conn.commit()
        return True

    def get_latest_funds(self) -> FundsData | None:
        """
        Get the latest funds data.

        Returns:
            FundsData model or None
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT available_cash, utilized_margin, available_margin,
                       total_equity, timestamp
                FROM funds ORDER BY timestamp DESC LIMIT 1
            """,
            )
            row = cursor.fetchone()

        if row is None:
            return None

        return FundsData(
            available_cash=row[0],
            utilized_margin=row[1],
            available_margin=row[2],
            total_equity=row[3],
            timestamp=datetime.fromisoformat(row[4]),
        )

    # ------------------------------------------------------------------
    # Order methods
    # ------------------------------------------------------------------

    def store_order(self, order: Order) -> bool:
        """
        Store an order record.

        Args:
            order: Order model instance

        Returns:
            True if successful
        """
        now = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO orders (
                    order_id, symbol, quantity, order_type, price,
                    trigger_price, variety, transaction_type, product_type,
                    status, timestamp, filled_quantity, average_price,
                    stop_loss, take_profit, trailing_stop_loss, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    order.order_id,
                    order.symbol,
                    order.quantity,
                    order.order_type.value,
                    order.price,
                    order.trigger_price,
                    order.variety.value,
                    order.transaction_type.value,
                    order.product_type.value,
                    order.status.value,
                    order.timestamp.isoformat(),
                    order.filled_quantity,
                    order.average_price,
                    order.stop_loss,
                    order.take_profit,
                    order.trailing_stop_loss,
                    now,
                    now,
                ),
            )
            conn.commit()

        self._log_audit(
            action="CREATE",
            entity_type="order",
            entity_id=order.order_id,
            new_state=self._model_to_dict(order),
        )
        return True

    def get_order(self, order_id: str) -> Order | None:
        """
        Get an order by ID.

        Args:
            order_id: Order identifier

        Returns:
            Order model or None
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM orders WHERE order_id = ?", (order_id,))
            row = cursor.fetchone()

        if row is None:
            return None

        return self._row_to_order(row)

    def update_order_status(self, order_id: str, status: str) -> bool:
        """
        Update the status of an order.

        Args:
            order_id: Order identifier
            status: New status value

        Returns:
            True if successful
        """
        now = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE orders SET status = ?, updated_at = ? WHERE order_id = ?",
                (status, now, order_id),
            )
            conn.commit()
        return True

    def get_open_orders(self, symbol: str | None = None) -> list[Order]:
        """
        Get all open orders, optionally filtered by symbol.

        Args:
            symbol: Optional symbol filter

        Returns:
            List of open Order models
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if symbol:
                cursor.execute(
                    "SELECT * FROM orders WHERE status = 'OPEN' AND symbol = ? ORDER BY timestamp DESC",
                    (symbol,),
                )
            else:
                cursor.execute(
                    "SELECT * FROM orders WHERE status = 'OPEN' ORDER BY timestamp DESC",
                )
            rows = cursor.fetchall()

        return [self._row_to_order(row) for row in rows]

    def _row_to_order(self, row: Any) -> Order:
        """Convert a database row to Order model."""
        from src.loats.models import (
            OrderStatus as OrderStatusEnum,
        )
        from src.loats.models import (
            OrderType as OrderTypeEnum,
        )
        from src.loats.models import (
            OrderVariety,
            ProductType,
            TransactionType,
        )

        return Order(
            order_id=row[0],
            symbol=row[1],
            quantity=row[2],
            order_type=OrderTypeEnum(row[3]),
            price=row[4],
            trigger_price=row[5],
            variety=OrderVariety(row[6]),
            transaction_type=TransactionType(row[7]),
            product_type=ProductType(row[8]),
            status=OrderStatusEnum(row[9]),
            timestamp=datetime.fromisoformat(row[10]),
            filled_quantity=row[11],
            average_price=row[12],
            stop_loss=row[13],
            take_profit=row[14],
            trailing_stop_loss=row[15],
        )

    # ------------------------------------------------------------------
    # Audit log methods
    # ------------------------------------------------------------------

    def get_audit_log(
        self,
        entity_type: str | None = None,
        limit: int = 100,
    ) -> list[AuditLogEntry]:
        """
        Get audit log entries.

        Args:
            entity_type: Optional entity type filter
            limit: Maximum number of entries

        Returns:
            List of AuditLogEntry models
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if entity_type:
                cursor.execute(
                    "SELECT * FROM audit_log WHERE entity_type = ? ORDER BY timestamp DESC LIMIT ?",
                    (entity_type, limit),
                )
            else:
                cursor.execute(
                    "SELECT * FROM audit_log ORDER BY timestamp DESC LIMIT ?",
                    (limit,),
                )
            rows = cursor.fetchall()

        return [self._row_to_audit_entry(row) for row in rows]

    def _row_to_audit_entry(self, row: Any) -> AuditLogEntry:
        """Convert a database row to AuditLogEntry model."""
        return AuditLogEntry(
            entry_id=row[0],
            timestamp=datetime.fromisoformat(row[1]),
            action=row[2],
            entity_type=row[3],
            entity_id=row[4],
            user=row[5],
            metadata=json.loads(row[6]) if row[6] else {},
            previous_state=json.loads(row[7]) if row[7] else None,
            new_state=json.loads(row[8]) if row[8] else None,
            sha256_hash=row[9],
        )

    def verify_audit_log_integrity(self) -> bool:
        """
        Verify the integrity of the audit log by checking SHA-256 hashes.

        Returns:
            True if all entries are valid, False if corruption is detected
        """
        try:
            with Path(self.audit_log_path).open(encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    data = json.loads(line)
                    stored_hash = data.get("sha256_hash")
                    if stored_hash is None:
                        return False
                    # Recalculate hash excluding the hash field itself
                    check_data = {k: v for k, v in data.items() if k != "sha256_hash"}
                    calculated_hash = self._calculate_sha256(check_data)
                    if calculated_hash != stored_hash:
                        return False
            return True
        except (json.JSONDecodeError, KeyError, FileNotFoundError):
            return False

    # ------------------------------------------------------------------
    # Utility methods
    # ------------------------------------------------------------------

    def get_dataframe(
        self,
        query: str,
        params: tuple[Any, ...] = (),
    ) -> pd.DataFrame:
        """
        Execute a query and return results as a pandas DataFrame.

        Args:
            query: SQL query string
            params: Query parameters

        Returns:
            pandas DataFrame with query results
        """
        with self._get_connection() as conn:
            df = pd.read_sql_query(query, conn, params=params)
        return df

    def execute_query(
        self,
        query: str,
        params: tuple[Any, ...] = (),
    ) -> bool:
        """
        Execute a write query (INSERT/UPDATE/DELETE/CREATE).

        Args:
            query: SQL query string
            params: Query parameters

        Returns:
            True if successful
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            conn.commit()
        return True

    def close(self) -> None:
        """Close database connections."""
        # SQLite connections are closed automatically when they go out of scope


# Create module-level singleton instance
db = Database()
