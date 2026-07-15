"""
Data models for LOATS13July2026 using Pydantic.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class OrderType(str, Enum):
    """Order type enumeration."""

    MARKET = "MARKET"
    LIMIT = "LIMIT"
    SL = "SL"  # Stop Loss
    SL_M = "SL-M"  # Stop Loss Market


class TransactionType(str, Enum):
    """Transaction type enumeration."""

    BUY = "BUY"
    SELL = "SELL"


class ProductType(str, Enum):
    """Product type enumeration."""

    MIS = "MIS"  # Intraday
    NRML = "NRML"  # Normal
    CNC = "CNC"  # Cash and Carry


class OrderVariety(str, Enum):
    """Order variety enumeration."""

    REGULAR = "regular"
    AMO = "amo"  # After Market Order


class OrderStatus(str, Enum):
    """Order status enumeration."""

    OPEN = "OPEN"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    PENDING = "PENDING"


class QuoteData(BaseModel):
    """Quote data model."""

    symbol: str
    last_price: float
    open: float
    high: float
    low: float
    close: float
    volume: int
    timestamp: datetime
    change: float = Field(default=0.0)
    change_percent: float = Field(default=0.0)

    def __init__(self, **data: dict[str, Any]) -> None:
        """Initialize QuoteData and calculate change_percent if not provided."""
        # Validate required fields
        if not data.get("symbol"):
            error_msg = "Symbol cannot be empty"
            raise ValueError(error_msg)

        # Calculate change_percent if not provided
        if ("change_percent" not in data or data["change_percent"] == 0.0) and (
            "last_price" in data and "close" in data and data["close"] != 0
        ):
            change = (data["last_price"] - data["close"]) / data["close"]
            data["change_percent"] = change * 100

        super().__init__(**data)


class HistoricalData(BaseModel):
    """Historical data model."""

    symbol: str
    timestamp: datetime
    open: float = Field(gt=0)
    high: float = Field(gt=0)
    low: float = Field(gt=0)
    close: float = Field(gt=0)
    volume: int = Field(ge=0)
    interval: str


class OptionType(str, Enum):
    """Option type enumeration."""

    CALL = "CE"
    PUT = "PE"


class OptionContract(BaseModel):
    """Option contract model."""

    symbol: str
    strike_price: float
    expiry: datetime
    option_type: OptionType
    last_price: float
    open_interest: int
    volume: int
    implied_volatility: float | None = None
    delta: float | None = None
    gamma: float | None = None
    theta: float | None = None
    vega: float | None = None
    rho: float | None = None


class OptionChain(BaseModel):
    """Option chain model."""

    symbol: str
    expiry: datetime
    timestamp: datetime
    underlying_price: float
    calls: list[OptionContract]
    puts: list[OptionContract]


class Position(BaseModel):
    """Position model."""

    symbol: str
    quantity: int
    average_price: float
    last_price: float
    pnl: float
    product_type: ProductType
    buy_quantity: int
    sell_quantity: int


class FundsData(BaseModel):
    """Funds data model."""

    available_cash: float
    utilized_margin: float
    available_margin: float
    total_equity: float
    timestamp: datetime


class Order(BaseModel):
    """Order model."""

    order_id: str
    symbol: str
    quantity: int = Field(gt=0)
    order_type: OrderType
    price: float | None = Field(None, gt=0)
    trigger_price: float | None = Field(None, gt=0)
    variety: OrderVariety
    transaction_type: TransactionType
    product_type: ProductType
    status: OrderStatus
    timestamp: datetime
    filled_quantity: int = Field(ge=0)
    average_price: float | None = Field(None, gt=0)
    stop_loss: float | None = Field(None, gt=0)
    take_profit: float | None = Field(None, gt=0)
    trailing_stop_loss: float | None = Field(None, gt=0)


class Trade(BaseModel):
    """Trade model for database storage."""

    trade_id: str = Field(
        default_factory=lambda: f"trade_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
    )
    symbol: str
    quantity: int = Field(gt=0)
    entry_price: float = Field(gt=0)
    exit_price: float | None = Field(None, gt=0)
    entry_time: datetime
    exit_time: datetime | None = None
    transaction_type: TransactionType
    product_type: ProductType
    pnl: float | None = None
    status: str = "OPEN"
    strategy: str
    stop_loss: float | None = Field(None, gt=0)
    take_profit: float | None = Field(None, gt=0)
    trailing_stop_loss: float | None = Field(None, gt=0)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("pnl", mode="before")
    @classmethod
    def calculate_pnl(cls, v: Any, info: Any) -> float | None:  # type: ignore[valid-type]
        """Calculate PnL if not provided."""
        if v is not None:
            return v

        # Get the data from ValidationInfo
        values = info.data

        if (
            values.get("exit_price") is not None
            and values.get("entry_price") is not None
            and values.get("quantity") is not None
            and values.get("transaction_type") is not None
        ):
            multiplier = 1 if values["transaction_type"] == TransactionType.BUY else -1
            pnl_value = (
                (values["exit_price"] - values["entry_price"])
                * values["quantity"]
                * multiplier
            )
            return float(pnl_value) if pnl_value is not None else None
        return None


class SignalType(str, Enum):
    """Signal type enumeration."""

    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"
    NEUTRAL = "NEUTRAL"


class Signal(BaseModel):
    """Trading signal model."""

    signal_id: str = Field(
        default_factory=lambda: f"signal_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
    )
    symbol: str
    signal_type: SignalType
    strength: float = Field(ge=0, le=1)
    timestamp: datetime
    indicators: dict[str, float]
    metadata: dict[str, Any] = Field(default_factory=dict)
    confidence: float | None = Field(None, ge=0, le=1)


class NewsItem(BaseModel):
    """News item model."""

    title: str
    content: str
    source: str
    url: str
    published_date: datetime
    sentiment_score: float
    sentiment_label: str


class AuditLogEntry(BaseModel):
    """Audit log entry model."""

    entry_id: str = Field(
        default_factory=lambda: f"audit_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
    )
    timestamp: datetime
    action: str
    entity_type: str
    entity_id: str
    user: str = "system"
    metadata: dict[str, Any] = Field(default_factory=dict)
    previous_state: dict[str, Any] | None = None
    new_state: dict[str, Any] | None = None
    sha256_hash: str | None = None


class TAIndicator(BaseModel):
    """Technical analysis indicator model."""

    name: str
    value: float
    timestamp: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)


class Greeks(BaseModel):
    """Greeks model for options."""

    delta: float
    gamma: float
    theta: float
    vega: float
    rho: float
    implied_volatility: float


class VaRResult(BaseModel):
    """Value at Risk result model."""

    confidence_level: float
    time_horizon: int  # in days
    var_value: float
    var_percent: float
    historical_var: float
    method: str
    timestamp: datetime


class SentimentAnalysisResult(BaseModel):
    """Sentiment analysis result model."""

    symbol: str
    timestamp: datetime
    sentiment_score: float
    sentiment_label: str
    news_count: int
    positive_count: int
    negative_count: int
    neutral_count: int
    top_news: list[NewsItem]
