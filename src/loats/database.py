"""
Database module for LOATS13July2026.
Implements SQLite database with audit trail and JSONL dual-write.
"""

import hashlib
import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, TypeVar

from pydantic import BaseModel

from .config import settings
from .logging import get_logger
from .models import (
    AuditLogEntry,
)

logger = get_logger(__name__)
T = TypeVar("T", bound=BaseModel)


class Database:
    """SQLite database with audit trail functionality."""

    def __init__(self, db_path: Path | None = None, audit_log_path: Path | None = None):
        """
        Initialize Database.

        Args:
            db_path: Path to SQLite database file
            audit_log_path: Path to audit log JSONL file
        """
        # Import settings here to avoid circular imports

        self.db_path = db_path or settings.sqlite_db_path
        self.audit_log_path = audit_log_path or settings.audit_log_path
        self.retention_days = settings.retention_days

        # Ensure directories exist
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.audit_log_path.parent.mkdir(parents=True, exist_ok=True)

        # Initialize database
        self._initialize_database()

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
            timestamp=datetime.now(),
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            user=user,
            metadata=metadata or {},
            previous_state=previous_state,
            new_state=new_state,
        )

        # Calculate hash
        entry_data = self._model_to_dict(entry)
        entry.sha256_hash = self._calculate_sha256(entry_data)

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
        with open(self.audit_log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry_data) + "\n")

    def _cleanup_old_data(self) -> None:
        """Clean up data older than retention period."""
        cutoff_date = datetime.now() - timedelta(days=self.retention_days)

        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Delete old trades
            cursor.execute(
                """
                DELETE FROM trades
                WHERE created_at < ?
            """,
                (cutoff_date.isoformat(),),
            )

            # Delete old signals
            cursor.execute(
                """
                DELETE FROM signals
                WHERE created_at < ?
            """,
                (cutoff_date.isoformat(),),
            )

            # Delete old historical data
            cursor.execute(
                """
                DELETE FROM historical_data
                WHERE created_at < ?
            """,
                (cutoff_date.isoformat(),),
            )

            # Delete old quotes
            cursor.execute(
                """
                DELETE FROM quotes
                WHERE created_at < ?
            """,
                (cutoff_date.isoformat(),),
            )

            conn.commit()

        logger.info(f"Cleaned up data older than {cutoff_date.isoformat()}")

    # [Rest of the Database class methods remain exactly the same...]

    def close(self) -> None:
        """Close database connections."""
        # SQLite connections are closed automatically when they go out of scope


# Note: Database instance creation is deferred to avoid circular imports
# Applications should create their own Database instances as needed
