"""
Configuration module for LOATS13July2026 using Pydantic Settings.
"""

from pathlib import Path

from pydantic import Field, HttpUrl, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings with validation and type conversion."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
    )

    # OpenAlgo API Configuration
    openalgo_api_key: SecretStr = Field(..., description="OpenAlgo API key")
    openalgo_base_url: HttpUrl = Field(
        "https://api.openalgo.in/v1",
        description="OpenAlgo API base URL",
    )

    # Telegram Configuration
    telegram_bot_token: SecretStr = Field(..., description="Telegram bot token")
    telegram_chat_id: str = Field(..., description="Telegram chat ID for alerts")

    # GitHub Configuration
    github_token: SecretStr | None = Field(
        None,
        description="GitHub token for repository operations",
    )

    # Trading Configuration
    default_symbol: str = Field("NIFTY50", description="Default trading symbol")
    default_timeframe: str = Field("1min", description="Default timeframe for analysis")
    sentiment_threshold: float = Field(
        0.05,
        description="Sentiment threshold for filtering news",
    )
    max_position_size: float = Field(
        100000.0,
        description="Maximum position size in currency units",
    )
    risk_per_trade: float = Field(0.01, description="Risk per trade as percentage")

    # Database Configuration
    sqlite_db_path: Path = Field(
        Path("data/lwts4oa.db"),
        description="Path to SQLite database file",
    )
    audit_log_path: Path = Field(
        Path("data/audit_log.jsonl"),
        description="Path to audit log file",
    )
    retention_days: int = Field(
        2555,
        description="Data retention period in days (7 years)",
    )

    # Scheduler Configuration
    ta_scan_interval: int = Field(
        60,
        description="Technical analysis scan interval in seconds",
    )
    sentiment_scan_interval: int = Field(
        300,
        description="Sentiment scan interval in seconds",
    )
    signal_scan_interval: int = Field(30, description="Signal scan interval in seconds")

    # Performance Configuration
    max_workers: int = Field(4, description="Maximum number of worker threads")
    request_timeout: int = Field(30, description="HTTP request timeout in seconds")

    @field_validator("sqlite_db_path", "audit_log_path", mode="before")
    @classmethod
    def ensure_data_directory_exists(cls, v: str | Path) -> Path:
        """Ensure the data directory exists."""
        path = Path(v)
        if not path.parent.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def initialize(self) -> None:
        """Initialize settings and ensure required directories exist."""
        # Ensure data directory exists
        self.sqlite_db_path.parent.mkdir(parents=True, exist_ok=True)
        self.audit_log_path.parent.mkdir(parents=True, exist_ok=True)

        # Validate critical settings
        if self.sentiment_threshold <= 0:
            raise ValueError("Sentiment threshold must be positive")

        if not (0 < self.risk_per_trade <= 1):
            raise ValueError("Risk per trade must be between 0 and 1")


# Initialize settings instance
settings = Settings()
