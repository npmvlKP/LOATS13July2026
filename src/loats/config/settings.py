"""Pydantic settings for LOATS13July2026 configuration."""

from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings with environment variable support."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
    )

    # Environment Configuration
    environment: Literal["development", "production", "test"] = Field(
        "development", description="Environment (development, production, test)"
    )
    sqlite_db_path: Path = Field(
        Path("data/loats.db"), description="Path to SQLite database file"
    )
    audit_log_path: Path = Field(
        Path("data/audit.log"), description="Path to audit log file"
    )
    retention_days: int = Field(
        2555, description="Number of days to retain data (7 years)"
    )

    # Scan Intervals
    ta_scan_interval: int = Field(
        60, description="Technical analysis scan interval in seconds"
    )
    sentiment_scan_interval: int = Field(
        300, description="Sentiment analysis scan interval in seconds"
    )
    signal_scan_interval: int = Field(30, description="Signal scan interval in seconds")

    # Default Trading Parameters
    default_symbol: str = Field("NIFTY", description="Default trading symbol")
    default_timeframe: str = Field("1min", description="Default timeframe for analysis")
    sentiment_threshold: float = Field(
        0.05, description="Sentiment threshold for signal generation"
    )
    request_timeout: float = Field(30.0, description="Request timeout in seconds")

    # OpenAlgo Configuration
    openalgo_api_key: SecretStr = Field(
        SecretStr("default_openalgo_api_key"),
        min_length=1,
        description="OpenAlgo API key",
    )
    openalgo_base_url: str = Field(
        "http://127.0.0.1:5000", description="Base URL for OpenAlgo REST API"
    )
    openalgo_mode: Literal["ANALYZE", "LIVE"] = Field(
        "ANALYZE", description="OpenAlgo mode (ANALYZE only until all gates pass)"
    )

    # Telegram Configuration
    telegram_bot_token: SecretStr = Field(
        SecretStr(""), description="Telegram bot token"
    )
    telegram_chat_id: str = Field("", description="Telegram chat ID")

    # Trading Configuration
    nifty_lot_size: int = Field(25, description="NIFTY lot size")
    max_order_value: Decimal = Field(
        Decimal("200000.00"), description="Maximum order value per order (Rs 2,00,000)"
    )
    max_daily_orders: int = Field(500, description="Maximum orders per day")
    max_ops: int = Field(3, description="Maximum orders per second")
    circuit_limit_pct: Decimal = Field(
        Decimal("0.05"), description="Circuit limit percentage (+-5%)"
    )

    # Risk Management
    max_position_per_symbol: int = Field(
        1000, description="Maximum position per symbol"
    )
    max_total_exposure: Decimal = Field(
        Decimal("1000000.00"), description="Maximum total exposure"
    )

    # NVIDIA NIM Rate Limiting
    nim_max_requests_per_minute: int = Field(
        20, description="Maximum NVIDIA NIM requests per minute"
    )
    nim_min_gap_seconds: Decimal = Field(
        Decimal("3.0"), description="Minimum gap between NVIDIA NIM requests (seconds)"
    )
    nim_max_context_tokens: int = Field(
        4096, description="Maximum context tokens for NVIDIA NIM prompts"
    )

    # Timezone Configuration
    timezone: str = Field(
        "Asia/Kolkata", description="Timezone for all datetime operations"
    )

    @field_validator("max_order_value", "max_total_exposure", "circuit_limit_pct")
    @classmethod
    def validate_decimals(cls, v: Decimal) -> Decimal:
        """Ensure decimal values have proper precision for financial calculations."""
        return v.quantize(Decimal("0.01"))

    @field_validator("nim_min_gap_seconds")
    @classmethod
    def validate_nim_gap(cls, v: Decimal) -> Decimal:
        """Ensure NIM gap has proper precision."""
        return v.quantize(Decimal("0.1"))

    @field_validator("environment")
    @classmethod
    def validate_environment(cls, v: str) -> str:
        """Validate environment value."""
        if v not in ["development", "production", "test"]:
            raise ValueError(
                "Environment must be one of: development, production, test"
            )
        return v

    @field_validator("retention_days")
    @classmethod
    def validate_retention_days(cls, v: int) -> int:
        """Validate retention days."""
        if v < 0:
            raise ValueError("Retention days must be non-negative")
        return v

    @field_validator(
        "ta_scan_interval", "sentiment_scan_interval", "signal_scan_interval"
    )
    @classmethod
    def validate_scan_intervals(cls, v: int) -> int:
        """Validate scan intervals."""
        if v <= 0:
            raise ValueError("Scan intervals must be positive")
        return v

    @field_validator("sentiment_threshold")
    @classmethod
    def validate_sentiment_threshold(cls, v: float) -> float:
        """Validate sentiment threshold."""
        if not (0 <= v <= 1):
            raise ValueError("Sentiment threshold must be between 0 and 1")
        return v

    @field_validator("request_timeout")
    @classmethod
    def validate_request_timeout(cls, v: float) -> float:
        """Validate request timeout."""
        if v <= 0:
            raise ValueError("Request timeout must be positive")
        return v

    def initialize(self) -> None:
        """Initialize settings (placeholder method for backward compatibility)."""
        pass


# Global settings instance with lazy initialization to avoid import-time validation errors
@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """
    Get global settings instance with lazy initialization.
    Avoids import-time validation errors on fresh checkouts by
    deferring actual Settings creation until first use.
    """
    return Settings()  # type: ignore[call-arg]


# Alias for backward compatibility
settings: Settings = get_settings()
