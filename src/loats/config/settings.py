"""Pydantic settings for LOATS13July2026 configuration."""

from decimal import Decimal
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings with environment variable support."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="forbid",
        frozen=True,
    )

    # OpenAlgo Configuration
    openalgo_api_key: str = Field(..., min_length=1, description="OpenAlgo API key")
    openalgo_base_url: str = Field(
        "http://127.0.0.1:5000",
        description="Base URL for OpenAlgo REST API",
    )
    openalgo_mode: Literal["ANALYZE", "LIVE"] = Field(
        "ANALYZE",
        description="OpenAlgo mode - ANALYZE only until all gates pass",
    )

    # Trading Configuration
    nifty_lot_size: int = Field(
        25,
        description="NIFTY lot size (NSE Nov 2021)",
    )
    max_order_value: Decimal = Field(
        Decimal("200000.00"),
        description="Maximum order value per order (Rs 2,00,000)",
    )
    max_daily_orders: int = Field(
        500,
        description="Maximum orders per day (self-imposed limit)",
    )
    max_ops: int = Field(
        3,
        description="Maximum orders per second (self-imposed ≤3 OPS)",
    )
    circuit_limit_pct: Decimal = Field(
        Decimal("0.05"),
        description="Circuit limit percentage (±5%)",
    )

    # Risk Management
    max_position_per_symbol: int = Field(
        1000,
        description="Maximum position per symbol",
    )
    max_total_exposure: Decimal = Field(
        Decimal("1000000.00"),
        description="Maximum total exposure",
    )

    # NVIDIA NIM Rate Limiting
    nim_max_requests_per_minute: int = Field(
        20,
        description="Maximum NVIDIA NIM requests per minute (conservative)",
    )
    nim_min_gap_seconds: Decimal = Field(
        Decimal("3.0"),
        description="Minimum gap between NVIDIA NIM requests (seconds)",
    )
    nim_max_context_tokens: int = Field(
        4096,
        description="Maximum context tokens for NVIDIA NIM prompts",
    )

    # Timezone Configuration
    timezone: str = Field(
        "Asia/Kolkata",
        description="Timezone for all datetime operations",
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
