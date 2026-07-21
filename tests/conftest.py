"""
Pytest configuration and fixtures for LOATS13July2026.
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import Generator
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from src.loats.database import Database
from src.loats.models import (
    HistoricalData,
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

if TYPE_CHECKING:
    from src.loats.config._settings import Settings


@pytest.fixture(autouse=True)
def configure_test_logging() -> None:
    """Configure logging for test environment."""
    from src.loats.logging import configure_logging

    configure_logging(test_mode=True)


@pytest.fixture
def test_settings() -> Settings:
    """Create test settings with temporary paths."""
    from pydantic import SecretStr
    from src.loats.config._settings import Settings

    # Create temporary directory for test data
    with tempfile.TemporaryDirectory() as temp_dir:
        test_settings = Settings(
            environment="test",
            sqlite_db_path=Path(temp_dir) / "test_loats.db",
            audit_log_path=Path(temp_dir) / "test_audit.log",
            openalgo_api_key=SecretStr("test_api_key"),
            openalgo_base_url="https://test.openalgo.com",
            telegram_bot_token=SecretStr("test_bot_token"),
            telegram_chat_id="123456789",
        )
        yield test_settings


@pytest.fixture
def db() -> Generator[Database, None, None]:
    """Create a test database instance."""
    from pydantic import SecretStr
    from src.loats.config._settings import Settings

    # Create temporary directory for test data
    temp_dir = tempfile.mkdtemp()

    # Create test settings
    test_settings = Settings(
        environment="test",
        sqlite_db_path=Path(temp_dir) / "test_loats.db",
        audit_log_path=Path(temp_dir) / "test_audit.log",
        openalgo_api_key=SecretStr("test_api_key"),
        openalgo_base_url="https://test.openalgo.com",
        telegram_bot_token=SecretStr("test_bot_token"),
        telegram_chat_id="123456789",
    )

    # Use the test settings with temporary paths
    db_instance = Database(
        db_path=test_settings.sqlite_db_path,
        audit_log_path=test_settings.audit_log_path,
    )
    db_instance.retention_days = 30  # Short retention for testing cleanup

    # Initialize the database
    db_instance._initialize_database()

    yield db_instance

    # Clean up - close connections and force garbage collection
    # to release Windows file locks before removing temp directory
    db_instance.close()
    import gc
    import shutil

    gc.collect()
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def sample_trade() -> Trade:
    """Create a sample trade for testing."""
    return Trade(
        symbol="TEST",
        quantity=10,
        entry_price=100.0,
        entry_time=datetime(2023, 1, 1, 10, 0),
        transaction_type=TransactionType.BUY,
        product_type=ProductType.MIS,
        strategy="test_strategy",
        stop_loss=95.0,
        take_profit=110.0,
        trailing_stop_loss=5.0,
    )


@pytest.fixture
def sample_order() -> Order:
    """Create a sample order for testing."""
    return Order(
        order_id="test_order_123",
        symbol="TEST",
        quantity=10,
        order_type=OrderType.LIMIT,
        price=100.0,
        variety=OrderVariety.REGULAR,
        transaction_type=TransactionType.BUY,
        product_type=ProductType.MIS,
        status=OrderStatus.OPEN,
        timestamp=datetime(2023, 1, 1, 10, 0),
        filled_quantity=0,
    )


@pytest.fixture
def sample_signal() -> Signal:
    """Create a sample signal for testing."""
    return Signal(
        symbol="TEST",
        signal_type=SignalType.BUY,
        strength=0.8,
        timestamp=datetime(2023, 1, 1, 10, 0),
        indicators={
            "rsi": 25.0,
            "macd": 1.5,
            "supertrend": 99.5,
        },
        confidence=0.85,
        metadata={"scan_type": "ta", "timeframe": "1min"},
    )


@pytest.fixture
def sample_historical_data() -> list[HistoricalData]:
    """Create sample historical data for testing."""
    return [
        HistoricalData(
            symbol="TEST",
            timestamp=datetime(2023, 1, 1, 9, 15),
            open=99.5,
            high=100.5,
            low=99.0,
            close=100.0,
            volume=1000,
            interval="1min",
        ),
        HistoricalData(
            symbol="TEST",
            timestamp=datetime(2023, 1, 1, 9, 16),
            open=100.0,
            high=101.0,
            low=99.5,
            close=100.5,
            volume=1200,
            interval="1min",
        ),
        HistoricalData(
            symbol="TEST",
            timestamp=datetime(2023, 1, 1, 9, 17),
            open=100.5,
            high=101.5,
            low=100.0,
            close=101.0,
            volume=1500,
            interval="1min",
        ),
    ]


def pytest_configure(config: pytest.Config) -> None:
    """Pytest configuration hook."""
    # Ensure test environment variable is set
    os.environ["ENVIRONMENT"] = "test"

    # Create a .env.test file for test configuration
    env_path = Path(__file__).parent.parent / ".env.test"
    if not env_path.exists():
        with open(env_path, "w", encoding="utf-8") as f:
            f.write("""# Test environment configuration
ENVIRONMENT=test
OPENALGO_API_KEY=test_api_key
OPENALGO_BASE_URL=https://test.openalgo.com
TELEGRAM_BOT_TOKEN=test_bot_token
TELEGRAM_CHAT_ID=123456789
""")
