"""Pytest configuration fixtures LOATS13July2026."""

from __future__ import annotations

import collections.abc
import datetime
import gc
import os
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from loats.database import Database
from loats.models import (
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
    from loats.config.settings import Settings

from loats.loats_logging import configure_logging


@pytest.fixture(autouse=True)
def configure_test_logging() -> None:
    """Configure logging test environment."""
    configure_logging(test_mode=True)


@pytest.fixture
def test_settings() -> Settings:
    """Create test settings for temporary paths."""
    from pydantic import SecretStr

    from loats.config.settings import Settings

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        test_settings = Settings(
            environment="test",
            sqlite_db_path=temp_path / "test_loats.db",
            audit_log_path=temp_path / "test_audit.log",
            openalgo_api_key=SecretStr("test_api_key"),
            openalgo_base_url="https://test.openalgo.com",
            telegram_bot_token=SecretStr("test_bot_token"),
            telegram_chat_id="123456789",
        )
        yield test_settings


@pytest.fixture
def db(test_settings) -> collections.abc.Generator[Database, None, None]:
    """Create test database instance."""
    db_instance = Database(
        db_path=test__cfg().sqlite_db_path,
        audit_log_path=test_settings.audit_log_path,
    )
    db_instance.retention_days = 30
    db_instance._initialize_database()
    yield db_instance
    db_instance.close()
    gc.collect()


@pytest.fixture
def sample_trade() -> Trade:
    """Create sample trade testing."""
    return Trade(
        symbol="TEST",
        quantity=10,
        entry_price=100.0,
        entry_time=datetime.datetime(2023, 1, 1, 10, 0),
        transaction_type=TransactionType.BUY,
        product_type=ProductType.MIS,
        strategy="test_strategy",
        stop_loss=95.0,
        take_profit=110.0,
        trailing_stop_loss=5.0,
    )


@pytest.fixture
def sample_order() -> Order:
    """Create sample order testing."""
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
        timestamp=datetime.datetime(2023, 1, 1, 10, 0),
        filled_quantity=0,
    )


@pytest.fixture
def sample_signal() -> Signal:
    """Create sample signal testing."""
    return Signal(
        symbol="TEST",
        signal_type=SignalType.BUY,
        strength=0.8,
        timestamp=datetime.datetime(2023, 1, 1, 10, 0),
        indicators={"rsi": 25.0, "macd": 1.5, "supertrend": 99.5},
        confidence=0.85,
        metadata={"scan_type": "ta", "timeframe": "1min"},
    )


@pytest.fixture
def sample_historical_data() -> list[HistoricalData]:
    """Create sample historical data testing."""
    return [
        HistoricalData(
            symbol="TEST",
            timestamp=datetime.datetime(2023, 1, 1, 9, 15),
            open=99.5,
            high=100.5,
            low=99.0,
            close=100.0,
            volume=1000,
            interval="1min",
        ),
        HistoricalData(
            symbol="TEST",
            timestamp=datetime.datetime(2023, 1, 1, 9, 16),
            open=100.0,
            high=101.0,
            low=99.5,
            close=100.5,
            volume=1200,
            interval="1min",
        ),
        HistoricalData(
            symbol="TEST",
            timestamp=datetime.datetime(2023, 1, 1, 9, 17),
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
    os.environ["ENVIRONMENT"] = "test"
    # Set test environment variables directly instead of writing to disk
    os.environ["OPENALGO_API_KEY"] = "test_api_key"
    os.environ["OPENALGO_BASE_URL"] = "https://test.openalgo.com"
    os.environ["TELEGRAM_BOT_TOKEN"] = "test_bot_token"
    os.environ["TELEGRAM_CHAT_ID"] = "123456789"


@pytest.fixture(autouse=True, scope="function")
async def clear_cache_before_each_test() -> None:
    """Clear cache before each test to prevent stale data."""
    from loats.utils.cache import cache_manager

    if cache_manager._cache:
        await cache_manager.clear()


@pytest.fixture(autouse=True, scope="function")
def reset_metrics_before_each_test() -> None:
    """Reset metrics manager state before each test to ensure isolation."""
    from loats.metrics import MetricsManager

    manager = MetricsManager()
    manager.reset_for_testing()


@pytest.fixture(autouse=True, scope="function")
def reset_circuit_breakers_before_each_test() -> None:
    """Reset circuit breakers state before each test to ensure isolation."""
    from loats.utils.circuit_breaker import (
        OPENALGO_CIRCUIT_BREAKER,
        TELEGRAM_CIRCUIT_BREAKER,
    )

    # Reset both global circuit breakers to ensure test isolation
    OPENALGO_CIRCUIT_BREAKER.reset()
    TELEGRAM_CIRCUIT_BREAKER.reset()


@pytest.fixture(autouse=True, scope="function")
def reset_rate_limiters_before_each_test() -> None:
    """Reset rate limiter singletons before each test to ensure isolation."""
    from loats.utils.rate_limiter import (
        _order_rate_limiter_instance,
        _rate_limiter_lock,
        _smart_order_rate_limiter_instance,
        _smart_rate_limiter_lock,
    )

    # Reset both global rate limiter singletons to ensure test isolation
    with _rate_limiter_lock:
        _order_rate_limiter_instance = None

    with _smart_rate_limiter_lock:
        _smart_order_rate_limiter_instance = None
