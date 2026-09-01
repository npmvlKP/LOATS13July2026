"""Pydantic settings for LOATS13July2026 configuration."""

from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

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
    default_timeframe: str = Field(
        "1min",
        description=(
            "Default candlestick timeframe for technical analysis "
            "(e.g., '1min', '5min', '15min')"
        ),
    )
    sentiment_threshold: float = Field(
        0.05, description="Sentiment threshold for signal generation"
    )
    composite_strength_threshold: float = Field(
        0.5, description="Minimum composite strength threshold for trade decisions"
    )
    request_timeout: float = Field(30.0, description="Request timeout in seconds")

    # OpenAlgo Configuration
    openalgo_api_key: SecretStr = Field(
        description="OpenAlgo API key (REQUIRED - no default)",
    )
    openalgo_base_url: str = Field(
        "http://127.0.0.1:5000", description="Base URL for OpenAlgo REST API"
    )
    openalgo_mode: Literal["ANALYZE", "LIVE"] = Field(
        "ANALYZE", description="OpenAlgo mode (ANALYZE only until all gates pass)"
    )
    analyzer_routing_enabled: bool = Field(
        False,
        description=(
            "Enable routing to Analyzer service "
            "(default False to prevent default-on fabrication)"
        ),
    )
    # CMP Rule 12 trailing-stop driver (default False = risk-off; enable
    # explicitly for the CMP strategy to update trailing stops each cycle).
    enable_trailing_stops: bool = Field(
        False,
        description="Enable trailing stop updates in CMP strategy cycle",
    )

    # Telegram Configuration
    telegram_bot_token: SecretStr = Field(
        SecretStr(""), description="Telegram bot token"
    )
    telegram_chat_id: str = Field("", description="Telegram chat ID")
    telegram_admin_ids: list[str] = Field(
        default_factory=list,
        description="List of Telegram user IDs authorized to issue "
        "/kill and /resume commands",
    )
    # Trading Configuration
    nifty_lot_size: int = Field(25, description="NIFTY lot size")
    # CMP Rule 7 modification counter ceiling (HC-23). 25 keeps the rule
    # chain within its weekly advance lock-step without over-ratcheting.
    max_modifications: int = Field(
        25, description="Maximum allowed Rule 7 modifications per week"
    )
    # Backward compatibility alias retained in HC-23 external verification.
    mods: int = Field(25, description="Maximum allowed Rule 7 modifications")
    # CMP Rule 11 position-limit envelope (HC-23). NIFTY = 5 lots, BANKNIFTY
    # = 3 lots (mirrored in rules.check_position_limits).
    max_nifty_positions: int = Field(5, description="Max open positions (NIFTY)")
    max_banknifty_positions: int = Field(
        3, description="Max open positions (BANKNIFTY)"
    )
    # Legacy aliases used by production modules/tests.
    max_open_positions: int = Field(5, description="Max open positions (NIFTY)")
    min_open_positions: int = Field(3, description="Min open positions (BANKNIFTY)")
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
    max_position_size: int = Field(
        1000, description="Maximum position size for risk management"
    )
    max_margin_utilization: float = Field(
        0.8, description="Maximum margin utilization ratio (0.0-1.0)"
    )

    # Timezone Configuration
    timezone: str = Field(
        "Asia/Kolkata", description="Timezone for all datetime operations"
    )

    # Metrics Configuration
    metrics_port: int = Field(8001, description="Port for Prometheus metrics server")

    # Dev-only warning suppression
    loats_suppress_nltk_warning: bool = Field(
        False,
        description="Set True to suppress newspaper4k dev-only NLTK tokenizer warning",
    )

    # VIX Configuration
    vix_symbol: str = Field("INDIAVIX", description="Symbol for India VIX index")
    vix_cache_ttl_seconds: int = Field(
        30, description="TTL for VIX cache in seconds (30-60 recommended)"
    )
    vix_fail_mode: Literal["block_all", "block_buy"] = Field(
        "block_all", description="VIX fail-safe mode: block_all or block_buy"
    )
    vix_stale_threshold_seconds: int = Field(
        60, description="Threshold for considering VIX data stale (seconds)"
    )

    # Decision Queue Configuration (TODO-27c bounded queue + backpressure)
    decision_queue_maxsize: int = Field(
        100,
        description="Max size for TradeDecision queue (bounded)",
    )
    rss_feeds: list[str] = Field(
        default=[
            "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms",
            "https://www.moneycontrol.com/rss/latestnews.xml",
            "https://www.livemint.com/rss/markets",
        ],
        description="Validated RSS feeds (bloombergquint removed)",
    )

    @field_validator("max_order_value", "max_total_exposure", "circuit_limit_pct")
    @classmethod
    def validate_decimals(cls, v: Decimal) -> Decimal:
        """Ensure decimal values have proper precision for financial calculations."""
        return v.quantize(Decimal("0.01"))

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

    @field_validator("sentiment_threshold", "composite_strength_threshold")
    @classmethod
    def validate_threshold(cls, v: float) -> float:
        """Validate threshold values."""
        if not (0 <= v <= 1):
            raise ValueError("Threshold must be between 0 and 1")
        return v

    @field_validator("request_timeout")
    @classmethod
    def validate_request_timeout(cls, v: float) -> float:
        """Validate request timeout."""
        if v <= 0:
            raise ValueError("Request timeout must be positive")
        return v

    @field_validator("vix_cache_ttl_seconds", "vix_stale_threshold_seconds")
    @classmethod
    def validate_vix_timeouts(cls, v: int) -> int:
        """Validate VIX timeout settings."""
        if v <= 0:
            raise ValueError("VIX timeout values must be positive")
        if v < 30 or v > 60:
            # Warning only - allow values outside recommended range
            import warnings

            warnings.warn(
                f"VIX cache TTL {v}s outside recommended range (30-60s)",
                stacklevel=2,
            )
        return v

    @field_validator("decision_queue_maxsize")
    @classmethod
    def validate_decision_queue_maxsize(cls, v: int) -> int:
        """Validate decision queue maxsize (bounded queue backpressure)."""
        if v <= 0:
            raise ValueError("decision_queue_maxsize must be positive")
        if v > 10000:
            raise ValueError("decision_queue_maxsize exceeds sane limit (10000)")
        return v

    @field_validator("rss_feeds", mode="before")
    @classmethod
    def parse_rss_feeds(cls, v: Any) -> Any:
        """Parse rss_feeds from env var JSON or comma-separated string."""
        if isinstance(v, str):
            stripped = v.strip()
            if not stripped:
                return []
            if stripped.startswith("["):
                try:
                    import json

                    parsed = json.loads(stripped)
                    if isinstance(parsed, list):
                        return parsed
                except Exception:  # nosec B110
                    pass
            # Fallback: comma-separated
            return [s.strip() for s in stripped.split(",") if s.strip()]
        return v

    @field_validator("openalgo_api_key")
    @classmethod
    def validate_openalgo_api_key(cls, v: SecretStr) -> SecretStr:
        """Ensure OpenAlgo API key is provided (no default allowed for secrets)."""
        value = v.get_secret_value()
        if not value:
            raise ValueError(
                "OpenAlgo API key must be set via OPENALGO_API_KEY environment variable"
            )
        return v

    def initialize(self) -> None:
        """Initialize settings (placeholder method for backward compatibility)."""
        pass


# Global settings instance with lazy initialization
# to avoid import-time validation errors
@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """
    Get global settings instance with lazy initialization.
    Avoids import-time validation errors on fresh checkouts by
    deferring actual Settings creation until first use.
    """
    return Settings()  # type: ignore[call-arg]


# Backward compatibility: get_settings() returns cached instance.
# Use get_settings() function for lazy initialization.
# The lru_cache defers Settings() instantiation until first call.
