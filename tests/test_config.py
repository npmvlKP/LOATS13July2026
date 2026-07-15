"""
Tests for configuration module.
"""

import os
from pathlib import Path
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from src.loats.config import Settings, get_settings, settings


class TestConfig:
    """Test suite for configuration module."""

    def test_settings_initialization(self) -> None:
        """Test Settings initialization with default values."""
        # Temporarily unset the ENVIRONMENT variable to test default behavior
        import os

        original_env = os.environ.get("ENVIRONMENT")
        if "ENVIRONMENT" in os.environ:
            del os.environ["ENVIRONMENT"]

        try:
            test_settings = Settings()

            assert test_settings.environment == "development"
            assert test_settings.sqlite_db_path == Path("data/loats.db")
            assert test_settings.audit_log_path == Path("data/audit.log")
            assert test_settings.retention_days == 2555  # 7 years
            assert test_settings.ta_scan_interval == 60  # 1 minute
            assert test_settings.sentiment_scan_interval == 300  # 5 minutes
            assert test_settings.signal_scan_interval == 30  # 30 seconds
            assert test_settings.default_symbol == "NIFTY"
            assert test_settings.default_timeframe == "1min"
            assert test_settings.sentiment_threshold == 0.05
            assert test_settings.request_timeout == 30.0
        finally:
            # Restore the original environment
            if original_env is not None:
                os.environ["ENVIRONMENT"] = original_env

    def test_settings_from_env(self) -> None:
        """Test Settings initialization from environment variables."""
        env_vars = {
            "ENVIRONMENT": "production",
            "SQLITE_DB_PATH": "/custom/path/loats.db",
            "AUDIT_LOG_PATH": "/custom/path/audit.log",
            "RETENTION_DAYS": "365",
            "TA_SCAN_INTERVAL": "120",
            "SENTIMENT_SCAN_INTERVAL": "600",
            "SIGNAL_SCAN_INTERVAL": "60",
            "DEFAULT_SYMBOL": "BANKNIFTY",
            "DEFAULT_TIMEFRAME": "5min",
            "SENTIMENT_THRESHOLD": "0.1",
            "REQUEST_TIMEOUT": "45.0",
            "OPENALGO_API_KEY": "test_api_key_123",
            "OPENALGO_BASE_URL": "https://api.testopenalgo.com",
            "TELEGRAM_BOT_TOKEN": "test_bot_token_456",
            "TELEGRAM_CHAT_ID": "987654321",
        }

        with patch.dict(os.environ, env_vars):
            test_settings = Settings()

            assert test_settings.environment == "production"
            assert test_settings.sqlite_db_path == Path("/custom/path/loats.db")
            assert test_settings.audit_log_path == Path("/custom/path/audit.log")
            assert test_settings.retention_days == 365
            assert test_settings.ta_scan_interval == 120
            assert test_settings.sentiment_scan_interval == 600
            assert test_settings.signal_scan_interval == 60
            assert test_settings.default_symbol == "BANKNIFTY"
            assert test_settings.default_timeframe == "5min"
            assert test_settings.sentiment_threshold == 0.1
            assert test_settings.request_timeout == 45.0
            assert (
                test_settings.openalgo_api_key.get_secret_value() == "test_api_key_123"
            )
            assert test_settings.openalgo_base_url == "https://api.testopenalgo.com"
            assert (
                test_settings.telegram_bot_token.get_secret_value()
                == "test_bot_token_456"
            )
            assert test_settings.telegram_chat_id == "987654321"

    def test_settings_validation(self) -> None:
        """Test Settings validation."""
        # Test invalid environment
        with pytest.raises(ValidationError):
            Settings(environment="invalid")

        # Test invalid retention days
        with pytest.raises(ValidationError):
            Settings(retention_days=-1)

        # Test invalid scan intervals
        with pytest.raises(ValidationError):
            Settings(ta_scan_interval=0)
        with pytest.raises(ValidationError):
            Settings(sentiment_scan_interval=0)
        with pytest.raises(ValidationError):
            Settings(signal_scan_interval=0)

        # Test invalid sentiment threshold
        with pytest.raises(ValidationError):
            Settings(sentiment_threshold=-0.1)
        with pytest.raises(ValidationError):
            Settings(sentiment_threshold=1.1)

        # Test invalid request timeout
        with pytest.raises(ValidationError):
            Settings(request_timeout=0)

        # Test that environment validation works
        with pytest.raises(ValidationError):
            Settings(environment="invalid")

    def test_get_settings(self) -> None:
        """Test get_settings function."""
        # Test that get_settings returns the global settings instance
        returned_settings = get_settings()
        assert returned_settings is settings

    def test_settings_initialize(self) -> None:
        """Test Settings.initialize method."""
        # Create a temporary .env file
        env_content = """
        ENVIRONMENT=test
        OPENALGO_API_KEY=test_key_from_env
        TELEGRAM_BOT_TOKEN=test_bot_from_env
        """

        with patch("builtins.open", create=True) as mock_open:
            mock_open.return_value.__enter__.return_value.read.return_value = (
                env_content
            )

            test_settings = Settings()
            test_settings.initialize()

            # Should load from .env file
            assert (
                test_settings.openalgo_api_key.get_secret_value() == "test_key_from_env"
            )
            assert (
                test_settings.telegram_bot_token.get_secret_value()
                == "test_bot_from_env"
            )

    def test_settings_repr(self) -> None:
        """Test Settings __repr__ method."""
        # Temporarily unset the ENVIRONMENT variable to test default behavior
        import os

        original_env = os.environ.get("ENVIRONMENT")
        if "ENVIRONMENT" in os.environ:
            del os.environ["ENVIRONMENT"]

        try:
            test_settings = Settings()
            repr_str = repr(test_settings)

            assert "Settings(" in repr_str
            assert "environment=" in repr_str
            assert "sqlite_db_path=" in repr_str
            # Sensitive fields should be masked
            assert "openalgo_api_key=SecretStr('**********')" in repr_str
        finally:
            # Restore the original environment
            if original_env is not None:
                os.environ["ENVIRONMENT"] = original_env

    def test_settings_str(self) -> None:
        """Test Settings __str__ method."""
        # Temporarily unset the ENVIRONMENT variable to test default behavior
        import os

        original_env = os.environ.get("ENVIRONMENT")
        if "ENVIRONMENT" in os.environ:
            del os.environ["ENVIRONMENT"]

        try:
            test_settings = Settings()
            str_str = str(test_settings)

            # The string representation should contain key fields
            assert "environment=" in str_str
            assert "sqlite_db_path=" in str_str
            assert "openalgo_api_key=SecretStr('**********')" in str_str
        finally:
            # Restore the original environment
            if original_env is not None:
                os.environ["ENVIRONMENT"] = original_env
