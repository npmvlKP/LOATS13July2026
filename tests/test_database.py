"""
Tests for database module.
"""

from datetime import UTC, datetime, timedelta

from src.loats.database import Database
from src.loats.models import (
    FundsData,
    HistoricalData,
    Order,
    OrderStatus,
    Position,
    ProductType,
    QuoteData,
    Signal,
    Trade,
)


class TestDatabase:
    """Test suite for Database class."""

    def test_database_initialization(self, db: Database) -> None:
        """Test database initialization."""
        assert db.db_path.exists()
        assert db.audit_log_path.exists()

        # Verify tables were created
        with db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [row[0] for row in cursor.fetchall()]

            expected_tables = [
                "trades",
                "signals",
                "audit_log",
                "historical_data",
                "quotes",
                "positions",
                "funds",
                "orders",
            ]
            for table in expected_tables:
                assert table in tables

    def test_model_to_dict_conversion(self, db: Database, sample_trade: Trade) -> None:
        """Test model to dict conversion."""
        trade_dict = db._model_to_dict(sample_trade)
        assert isinstance(trade_dict, dict)
        assert trade_dict["symbol"] == "TEST"
        assert trade_dict["quantity"] == 10

    def test_dict_to_model_conversion(self, db: Database, sample_trade: Trade) -> None:
        """Test dict to model conversion."""
        trade_dict = db._model_to_dict(sample_trade)
        converted_trade = db._dict_to_model(trade_dict, Trade)

        assert isinstance(converted_trade, Trade)
        assert converted_trade.symbol == sample_trade.symbol
        assert converted_trade.quantity == sample_trade.quantity
        assert converted_trade.entry_price == sample_trade.entry_price

    def test_calculate_sha256(self, db: Database) -> None:
        """Test SHA-256 hash calculation."""
        test_data = {"key": "value", "number": 42}
        hash1 = db._calculate_sha256(test_data)

        # Same data should produce same hash
        hash2 = db._calculate_sha256(test_data)
        assert hash1 == hash2

        # Different data should produce different hash
        test_data2 = {"key": "value", "number": 43}
        hash3 = db._calculate_sha256(test_data2)
        assert hash1 != hash3

        # Hash should be a valid SHA-256 hash
        assert len(hash1) == 64
        assert isinstance(hash1, str)

    def test_create_and_get_trade(self, db: Database, sample_trade: Trade) -> None:
        """Test create and get trade operations."""
        # Create trade
        result = db.create_trade(sample_trade)
        assert result is True

        # Get trade
        retrieved_trade = db.get_trade(sample_trade.trade_id)
        assert retrieved_trade is not None
        assert retrieved_trade.trade_id == sample_trade.trade_id
        assert retrieved_trade.symbol == sample_trade.symbol
        assert retrieved_trade.quantity == sample_trade.quantity
        assert retrieved_trade.entry_price == sample_trade.entry_price
        assert retrieved_trade.status == "OPEN"

    def test_update_trade(self, db: Database, sample_trade: Trade) -> None:
        """Test update trade operation."""
        # Create trade
        db.create_trade(sample_trade)

        # Update trade
        updated_trade = Trade(
            **sample_trade.model_dump(
                exclude={"exit_price", "exit_time", "pnl", "status"}
            ),
            exit_price=105.0,
            exit_time=datetime.now(),
            pnl=50.0,
            status="CLOSED",
        )

        result = db.update_trade(updated_trade)
        assert result is True

        # Verify update
        retrieved_trade = db.get_trade(sample_trade.trade_id)
        assert retrieved_trade is not None
        assert retrieved_trade.exit_price == 105.0
        assert retrieved_trade.pnl == 50.0
        assert retrieved_trade.status == "CLOSED"

    def test_get_open_trades(self, db: Database, sample_trade: Trade) -> None:
        """Test get open trades operation."""
        # Create open trade
        db.create_trade(sample_trade)

        # Create closed trade
        closed_trade = Trade(
            **sample_trade.model_dump(
                exclude={"trade_id", "exit_price", "exit_time", "pnl", "status"}
            ),
            trade_id="trade_closed_123",
            exit_price=105.0,
            exit_time=datetime.now(),
            pnl=50.0,
            status="CLOSED",
        )
        db.create_trade(closed_trade)

        # Get open trades
        open_trades = db.get_open_trades()
        assert len(open_trades) == 1
        assert open_trades[0].trade_id == sample_trade.trade_id
        assert open_trades[0].status == "OPEN"

        # Filter by symbol
        open_trades = db.get_open_trades("TEST")
        assert len(open_trades) == 1

        open_trades = db.get_open_trades("NONEXISTENT")
        assert len(open_trades) == 0

    def test_create_and_get_signal(self, db: Database, sample_signal: Signal) -> None:
        """Test create and get signal operations."""
        # Create signal
        result = db.create_signal(sample_signal)
        assert result is True

        # Get latest signals
        signals = db.get_latest_signals("TEST", limit=1)
        assert len(signals) == 1
        assert signals[0].signal_id == sample_signal.signal_id
        assert signals[0].symbol == sample_signal.symbol
        assert signals[0].signal_type == sample_signal.signal_type
        assert signals[0].strength == sample_signal.strength

    def test_get_latest_signals(self, db: Database, sample_signal: Signal) -> None:
        """Test get latest signals operation."""
        # Create multiple signals
        for i in range(5):
            signal = Signal(
                **sample_signal.model_dump(
                    exclude={"signal_id", "timestamp", "strength"}
                ),
                signal_id=f"signal_{i}",
                timestamp=datetime.now() - timedelta(minutes=i),
                strength=0.8 - (i * 0.1),
            )
            db.create_signal(signal)

        # Get latest signals
        signals = db.get_latest_signals("TEST", limit=3)
        assert len(signals) == 3
        assert signals[0].strength > signals[1].strength > signals[2].strength

        # Test with non-existent symbol
        signals = db.get_latest_signals("NONEXISTENT", limit=3)
        assert len(signals) == 0

    def test_store_and_get_historical_data(
        self,
        db: Database,
        sample_historical_data: list[HistoricalData],
    ) -> None:
        """Test store and get historical data operations."""
        # Normalize timestamps to UTC for comparison
        normalized_data = []
        for item in sample_historical_data:
            normalized_item = item.model_copy()
            if normalized_item.timestamp.tzinfo is None:
                normalized_item.timestamp = normalized_item.timestamp.replace(
                    tzinfo=UTC
                )
            else:
                normalized_item.timestamp = normalized_item.timestamp.astimezone(UTC)
            normalized_data.append(normalized_item)

        # Store historical data
        result = db.store_historical_data(normalized_data)
        assert result is True

        # Get historical data
        start_date = datetime(2023, 1, 1, 9, 0, tzinfo=UTC)
        end_date = datetime(2023, 1, 1, 10, 0, tzinfo=UTC)
        retrieved_data = db.get_historical_data("TEST", "1min", start_date, end_date)

        assert len(retrieved_data) == 3
        # Both should now be UTC-aware
        assert retrieved_data[0].timestamp == normalized_data[0].timestamp
        assert retrieved_data[0].open == sample_historical_data[0].open
        assert retrieved_data[1].close == sample_historical_data[1].close

    def test_store_and_get_quote(self, db: Database) -> None:
        """Test store and get quote operations."""
        # Create quote
        quote = QuoteData(
            symbol="TEST",
            last_price=101.5,
            open=100.0,
            high=102.0,
            low=99.5,
            close=101.0,
            volume=10000,
            timestamp=datetime.now(),
            change=1.5,
            change_percent=1.5,
        )

        # Store quote
        result = db.store_quote(quote)
        assert result is True

        # Get latest quote
        retrieved_quote = db.get_latest_quote("TEST")
        assert retrieved_quote is not None
        assert retrieved_quote.symbol == quote.symbol
        assert retrieved_quote.last_price == quote.last_price
        assert retrieved_quote.volume == quote.volume

        # Test with non-existent symbol
        retrieved_quote = db.get_latest_quote("NONEXISTENT")
        assert retrieved_quote is None

    def test_store_and_get_position(self, db: Database) -> None:
        """Test store and get position operations."""
        # Create position
        position = Position(
            symbol="TEST",
            quantity=10,
            average_price=100.0,
            last_price=101.5,
            pnl=15.0,
            product_type=ProductType.MIS,
            buy_quantity=10,
            sell_quantity=0,
        )

        # Store position
        result = db.store_position(position)
        assert result is True

        # Get position
        retrieved_position = db.get_position("TEST")
        assert retrieved_position is not None
        assert retrieved_position.symbol == position.symbol
        assert retrieved_position.quantity == position.quantity
        assert retrieved_position.pnl == position.pnl

        # Test with non-existent symbol
        retrieved_position = db.get_position("NONEXISTENT")
        assert retrieved_position is None

    def test_store_and_get_funds(self, db: Database) -> None:
        """Test store and get funds operations."""
        # Create funds data
        funds = FundsData(
            available_cash=50000.0,
            utilized_margin=1000.0,
            available_margin=49000.0,
            total_equity=50000.0,
            timestamp=datetime.now(),
        )

        # Store funds
        result = db.store_funds(funds)
        assert result is True

        # Get latest funds
        retrieved_funds = db.get_latest_funds()
        assert retrieved_funds is not None
        assert retrieved_funds.available_cash == funds.available_cash
        assert retrieved_funds.total_equity == funds.total_equity

    def test_store_and_get_order(self, db: Database, sample_order: Order) -> None:
        """Test store and get order operations."""
        # Store order
        result = db.store_order(sample_order)
        assert result is True

        # Get order
        retrieved_order = db.get_order(sample_order.order_id)
        assert retrieved_order is not None
        assert retrieved_order.order_id == sample_order.order_id
        assert retrieved_order.symbol == sample_order.symbol
        assert retrieved_order.status == sample_order.status

        # Test with non-existent order
        retrieved_order = db.get_order("nonexistent_order")
        assert retrieved_order is None

    def test_update_order_status(self, db: Database, sample_order: Order) -> None:
        """Test update order status operation."""
        # Store order
        db.store_order(sample_order)

        # Update order status
        result = db.update_order_status(
            sample_order.order_id,
            OrderStatus.COMPLETED.value,
        )
        assert result is True

        # Verify update
        retrieved_order = db.get_order(sample_order.order_id)
        assert retrieved_order is not None
        assert retrieved_order.status == OrderStatus.COMPLETED

    def test_get_open_orders(self, db: Database, sample_order: Order) -> None:
        """Test get open orders operation."""
        # Store open order
        db.store_order(sample_order)

        # Store completed order
        completed_order = Order(
            **sample_order.model_dump(exclude={"order_id", "status"}),
            order_id="order_completed_123",
            status=OrderStatus.COMPLETED,
        )
        db.store_order(completed_order)

        # Get open orders
        open_orders = db.get_open_orders()
        assert len(open_orders) == 1
        assert open_orders[0].order_id == sample_order.order_id
        assert open_orders[0].status == OrderStatus.OPEN

        # Filter by symbol
        open_orders = db.get_open_orders("TEST")
        assert len(open_orders) == 1

        open_orders = db.get_open_orders("NONEXISTENT")
        assert len(open_orders) == 0

    def test_get_audit_log(self, db: Database, sample_trade: Trade) -> None:
        """Test get audit log operation."""
        # Create trade to generate audit log entries
        db.create_trade(sample_trade)
        db.update_trade(
            Trade(
                **sample_trade.model_dump(
                    exclude={"exit_price", "exit_time", "pnl", "status"}
                ),
                exit_price=105.0,
                exit_time=datetime.now(),
                pnl=50.0,
                status="CLOSED",
            ),
        )

        # Get audit log
        audit_log = db.get_audit_log(limit=10)
        assert len(audit_log) >= 2  # At least CREATE and UPDATE actions

        # Verify audit log entries
        create_entry = None
        update_entry = None

        for entry in audit_log:
            if entry.action == "CREATE" and entry.entity_type == "trade":
                create_entry = entry
            elif entry.action == "UPDATE" and entry.entity_type == "trade":
                update_entry = entry

        assert create_entry is not None
        assert update_entry is not None
        assert create_entry.entity_id == sample_trade.trade_id
        assert update_entry.entity_id == sample_trade.trade_id

        # Test filtering
        filtered_log = db.get_audit_log(entity_type="trade", limit=5)
        assert len(filtered_log) >= 2

        filtered_log = db.get_audit_log(entity_type="nonexistent", limit=5)
        assert len(filtered_log) == 0

    def test_audit_log_integrity(self, db: Database, sample_trade: Trade) -> None:
        """Test audit log integrity verification."""
        # Create trade to generate audit log entries
        db.create_trade(sample_trade)

        # Verify integrity
        result = db.verify_audit_log_integrity()
        assert result is True

        # Corrupt the audit log
        with open(db.audit_log_path, "a", encoding="utf-8") as f:
            f.write('{"corrupted": "data"}\n')

        # Integrity should fail
        result = db.verify_audit_log_integrity()
        assert result is False

    def test_cleanup_old_data(self, db: Database, sample_trade: Trade) -> None:
        """Test cleanup old data."""
        # Create trade with old timestamp
        old_trade = Trade(
            **sample_trade.model_dump(exclude={"trade_id", "entry_time"}),
            trade_id="old_trade_123",
            entry_time=datetime.now() - timedelta(days=31)
        )
        db.create_trade(old_trade)

        # Create recent trade
        recent_trade = Trade(
            **sample_trade.model_dump(exclude={"trade_id", "entry_time"}),
            trade_id="recent_trade_123",
            entry_time=datetime.now()
        )
        db.create_trade(recent_trade)

        # Run cleanup
        db._cleanup_old_data()

        # Verify old trade was deleted
        old_trade_retrieved = db.get_trade("old_trade_123")
        assert old_trade_retrieved is None

        # Verify recent trade still exists
        recent_trade_retrieved = db.get_trade("recent_trade_123")
        assert recent_trade_retrieved is not None

    def test_get_dataframe(
        self,
        db: Database,
        sample_historical_data: list[HistoricalData],
    ) -> None:
        """Test get_dataframe method."""
        # Store historical data
        db.store_historical_data(sample_historical_data)

        # Get as dataframe
        df = db.get_dataframe(
            "SELECT * FROM historical_data WHERE symbol = ?",
            ("TEST",),
        )

        assert len(df) == 3
        assert "symbol" in df.columns
        assert "timestamp" in df.columns
        assert "open" in df.columns
        assert df.iloc[0]["symbol"] == "TEST"

    def test_execute_query(self, db: Database) -> None:
        """Test execute_query method."""
        # Create a test table
        result = db.execute_query("""
            CREATE TABLE IF NOT EXISTS test_table (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                value REAL
            )
        """)
        assert result is True

        # Insert data
        result = db.execute_query(
            "INSERT INTO test_table (name, value) VALUES (?, ?)",
            ("test", 42.0),
        )
        assert result is True

        # Verify data was inserted
        df = db.get_dataframe("SELECT * FROM test_table")
        assert len(df) == 1
        assert df.iloc[0]["name"] == "test"
        assert df.iloc[0]["value"] == 42.0

    def test_vacuum(self, db: Database) -> None:
        """Test vacuum method."""
        # This is a no-op test since vacuum doesn't return anything
        # Just ensure it doesn't raise an exception
        db.vacuum()
        assert True
