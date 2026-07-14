"""
Tests for data models.
"""

from datetime import datetime

import pytest
from pydantic import ValidationError

from src.loats.models import (
    AuditLogEntry,
    FundsData,
    Greeks,
    HistoricalData,
    NewsItem,
    OptionContract,
    OptionType,
    Order,
    OrderStatus,
    OrderType,
    OrderVariety,
    Position,
    ProductType,
    QuoteData,
    SentimentAnalysisResult,
    Signal,
    SignalType,
    TAIndicator,
    Trade,
    TransactionType,
    VaRResult,
)


class TestModels:
    """Test suite for data models."""

    def test_order_type_enum(self) -> None:
        """Test OrderType enum."""
        assert OrderType.MARKET.value == "MARKET"
        assert OrderType.LIMIT.value == "LIMIT"
        assert OrderType.SL.value == "SL"
        assert OrderType.SL_M.value == "SL-M"

        # Test enum iteration
        order_types = list(OrderType)
        assert len(order_types) == 4
        assert OrderType.MARKET in order_types

    def test_transaction_type_enum(self) -> None:
        """Test TransactionType enum."""
        assert TransactionType.BUY.value == "BUY"
        assert TransactionType.SELL.value == "SELL"

        # Test enum iteration
        transaction_types = list(TransactionType)
        assert len(transaction_types) == 2
        assert TransactionType.BUY in transaction_types

    def test_product_type_enum(self) -> None:
        """Test ProductType enum."""
        assert ProductType.MIS.value == "MIS"
        assert ProductType.NRML.value == "NRML"
        assert ProductType.CNC.value == "CNC"

        # Test enum iteration
        product_types = list(ProductType)
        assert len(product_types) == 3
        assert ProductType.MIS in product_types

    def test_order_variety_enum(self) -> None:
        """Test OrderVariety enum."""
        assert OrderVariety.REGULAR.value == "regular"
        assert OrderVariety.AMO.value == "amo"

        # Test enum iteration
        varieties = list(OrderVariety)
        assert len(varieties) == 2
        assert OrderVariety.REGULAR in varieties

    def test_order_status_enum(self) -> None:
        """Test OrderStatus enum."""
        assert OrderStatus.OPEN.value == "OPEN"
        assert OrderStatus.COMPLETED.value == "COMPLETED"
        assert OrderStatus.CANCELLED.value == "CANCELLED"
        assert OrderStatus.REJECTED.value == "REJECTED"
        assert OrderStatus.PENDING.value == "PENDING"

        # Test enum iteration
        statuses = list(OrderStatus)
        assert len(statuses) == 5
        assert OrderStatus.OPEN in statuses

    def test_signal_type_enum(self) -> None:
        """Test SignalType enum."""
        assert SignalType.BUY.value == "BUY"
        assert SignalType.SELL.value == "SELL"
        assert SignalType.HOLD.value == "HOLD"
        assert SignalType.NEUTRAL.value == "NEUTRAL"

        # Test enum iteration
        signal_types = list(SignalType)
        assert len(signal_types) == 4
        assert SignalType.BUY in signal_types

    def test_option_type_enum(self) -> None:
        """Test OptionType enum."""
        assert OptionType.CALL.value == "CE"
        assert OptionType.PUT.value == "PE"

        # Test enum iteration
        option_types = list(OptionType)
        assert len(option_types) == 2
        assert OptionType.CALL in option_types

    def test_quote_data_model(self) -> None:
        """Test QuoteData model."""
        quote = QuoteData(
            symbol="NIFTY",
            last_price=18000.50,
            open=17950.25,
            high=18050.75,
            low=17900.00,
            close=17980.50,
            volume=1000000,
            timestamp=datetime(2023, 1, 1, 15, 30),
            change=20.00,
            change_percent=0.11,
        )

        assert quote.symbol == "NIFTY"
        assert quote.last_price == 18000.50
        assert quote.change == 20.00
        assert quote.change_percent == 0.11
        assert quote.timestamp == datetime(2023, 1, 1, 15, 30)

        # Test change_percent calculation
        quote2 = QuoteData(
            symbol="NIFTY",
            last_price=18000.50,
            open=17950.25,
            high=18050.75,
            low=17900.00,
            close=17980.50,
            volume=1000000,
            timestamp=datetime(2023, 1, 1, 15, 30),
        )

        assert quote2.change_percent == pytest.approx(0.11, 0.01)

    def test_historical_data_model(self) -> None:
        """Test HistoricalData model."""
        data = HistoricalData(
            symbol="NIFTY",
            timestamp=datetime(2023, 1, 1, 9, 15),
            open=17950.25,
            high=18000.50,
            low=17900.00,
            close=17980.50,
            volume=500000,
            interval="1min",
        )

        assert data.symbol == "NIFTY"
        assert data.interval == "1min"
        assert data.timestamp == datetime(2023, 1, 1, 9, 15)
        assert data.open == 17950.25
        assert data.close == 17980.50

    def test_option_contract_model(self) -> None:
        """Test OptionContract model."""
        contract = OptionContract(
            symbol="NIFTY23JAN18000CE",
            strike_price=18000.0,
            expiry=datetime(2023, 1, 26, 15, 30),
            option_type=OptionType.CALL,
            last_price=150.50,
            open_interest=10000,
            volume=5000,
            implied_volatility=0.25,
            delta=0.5,
            gamma=0.02,
            theta=-0.05,
            vega=0.1,
            rho=0.03,
        )

        assert contract.symbol == "NIFTY23JAN18000CE"
        assert contract.strike_price == 18000.0
        assert contract.option_type == OptionType.CALL
        assert contract.last_price == 150.50
        assert contract.implied_volatility == 0.25
        assert contract.delta == 0.5

    def test_position_model(self) -> None:
        """Test Position model."""
        position = Position(
            symbol="NIFTY",
            quantity=100,
            average_price=17950.0,
            last_price=18000.50,
            pnl=5050.0,
            product_type=ProductType.MIS,
            buy_quantity=100,
            sell_quantity=0,
        )

        assert position.symbol == "NIFTY"
        assert position.quantity == 100
        assert position.average_price == 17950.0
        assert position.pnl == 5050.0
        assert position.product_type == ProductType.MIS

    def test_funds_data_model(self) -> None:
        """Test FundsData model."""
        funds = FundsData(
            available_cash=50000.0,
            utilized_margin=10000.0,
            available_margin=40000.0,
            total_equity=50000.0,
            timestamp=datetime(2023, 1, 1, 15, 30),
        )

        assert funds.available_cash == 50000.0
        assert funds.utilized_margin == 10000.0
        assert funds.available_margin == 40000.0
        assert funds.total_equity == 50000.0

    def test_order_model(self) -> None:
        """Test Order model."""
        order = Order(
            order_id="order_12345",
            symbol="NIFTY",
            quantity=100,
            order_type=OrderType.LIMIT,
            price=18000.0,
            variety=OrderVariety.REGULAR,
            transaction_type=TransactionType.BUY,
            product_type=ProductType.MIS,
            status=OrderStatus.OPEN,
            timestamp=datetime(2023, 1, 1, 10, 0),
            filled_quantity=0,
            average_price=None,
            stop_loss=17950.0,
            take_profit=18100.0,
            trailing_stop_loss=50.0,
        )

        assert order.order_id == "order_12345"
        assert order.symbol == "NIFTY"
        assert order.quantity == 100
        assert order.order_type == OrderType.LIMIT
        assert order.price == 18000.0
        assert order.status == OrderStatus.OPEN
        assert order.stop_loss == 17950.0
        assert order.take_profit == 18100.0

    def test_trade_model(self) -> None:
        """Test Trade model."""
        trade = Trade(
            symbol="NIFTY",
            quantity=100,
            entry_price=17950.0,
            entry_time=datetime(2023, 1, 1, 10, 0),
            transaction_type=TransactionType.BUY,
            product_type=ProductType.MIS,
            strategy="supertrend",
            stop_loss=17900.0,
            take_profit=18100.0,
            trailing_stop_loss=50.0,
        )

        assert trade.symbol == "NIFTY"
        assert trade.quantity == 100
        assert trade.entry_price == 17950.0
        assert trade.strategy == "supertrend"
        assert trade.status == "OPEN"
        assert trade.trade_id.startswith("trade_")

        # Test PnL calculation
        trade_with_exit = Trade(
            **trade.model_dump(),
            exit_price=18050.0,
            exit_time=datetime(2023, 1, 1, 15, 30),
            transaction_type=TransactionType.BUY,
        )

        assert trade_with_exit.pnl == 10000.0  # (18050 - 17950) * 100

        # Test PnL calculation for sell transaction
        trade_sell = Trade(
            **trade.model_dump(),
            exit_price=17850.0,
            exit_time=datetime(2023, 1, 1, 15, 30),
            transaction_type=TransactionType.SELL,
        )

        assert trade_sell.pnl == 10000.0  # (17950 - 17850) * 100

    def test_signal_model(self) -> None:
        """Test Signal model."""
        signal = Signal(
            symbol="NIFTY",
            signal_type=SignalType.BUY,
            strength=0.85,
            timestamp=datetime(2023, 1, 1, 10, 0),
            indicators={
                "rsi": 25.0,
                "macd": 1.5,
                "supertrend": 17950.0,
            },
            confidence=0.85,
            metadata={
                "scan_type": "ta",
                "timeframe": "1min",
            },
        )

        assert signal.symbol == "NIFTY"
        assert signal.signal_type == SignalType.BUY
        assert signal.strength == 0.85
        assert signal.indicators["rsi"] == 25.0
        assert signal.signal_id.startswith("signal_")

        # Test validation
        with pytest.raises(ValidationError):
            Signal(
                symbol="NIFTY",
                signal_type=SignalType.BUY,
                strength=1.5,  # Invalid strength (> 1)
                timestamp=datetime.now(),
                indicators={},
            )

        with pytest.raises(ValidationError):
            Signal(
                symbol="NIFTY",
                signal_type=SignalType.BUY,
                strength=-0.5,  # Invalid strength (< 0)
                timestamp=datetime.now(),
                indicators={},
            )

    def test_news_item_model(self) -> None:
        """Test NewsItem model."""
        news = NewsItem(
            title="Market Update",
            content="The market is showing bullish signs today.",
            source="Economic Times",
            url="https://economictimes.com/market-update",
            published_date=datetime(2023, 1, 1, 10, 0),
            sentiment_score=0.75,
            sentiment_label="positive",
        )

        assert news.title == "Market Update"
        assert news.source == "Economic Times"
        assert news.sentiment_score == 0.75
        assert news.sentiment_label == "positive"

    def test_audit_log_entry_model(self) -> None:
        """Test AuditLogEntry model."""
        entry = AuditLogEntry(
            timestamp=datetime(2023, 1, 1, 10, 0),
            action="CREATE",
            entity_type="trade",
            entity_id="trade_12345",
            user="system",
            metadata={"key": "value"},
            previous_state={"status": "OPEN"},
            new_state={"status": "CLOSED"},
        )

        assert entry.action == "CREATE"
        assert entry.entity_type == "trade"
        assert entry.entity_id == "trade_12345"
        assert entry.user == "system"
        assert entry.metadata["key"] == "value"
        assert entry.entry_id.startswith("audit_")

    def test_ta_indicator_model(self) -> None:
        """Test TAIndicator model."""
        indicator = TAIndicator(
            name="rsi",
            value=25.0,
            timestamp=datetime(2023, 1, 1, 10, 0),
            metadata={"timeframe": "1min"},
        )

        assert indicator.name == "rsi"
        assert indicator.value == 25.0
        assert indicator.metadata["timeframe"] == "1min"

    def test_greeks_model(self) -> None:
        """Test Greeks model."""
        greeks = Greeks(
            delta=0.5,
            gamma=0.02,
            theta=-0.05,
            vega=0.1,
            rho=0.03,
            implied_volatility=0.25,
        )

        assert greeks.delta == 0.5
        assert greeks.gamma == 0.02
        assert greeks.theta == -0.05
        assert greeks.implied_volatility == 0.25

    def test_var_result_model(self) -> None:
        """Test VaRResult model."""
        var = VaRResult(
            confidence_level=0.95,
            time_horizon=1,
            var_value=1000.0,
            var_percent=1.0,
            historical_var=950.0,
            method="historical",
            timestamp=datetime(2023, 1, 1, 10, 0),
        )

        assert var.confidence_level == 0.95
        assert var.time_horizon == 1
        assert var.var_value == 1000.0
        assert var.var_percent == 1.0
        assert var.method == "historical"

    def test_sentiment_analysis_result_model(self) -> None:
        """Test SentimentAnalysisResult model."""
        news1 = NewsItem(
            title="Positive News",
            content="Good market outlook",
            source="Source1",
            url="https://source1.com/news1",
            published_date=datetime(2023, 1, 1, 9, 0),
            sentiment_score=0.8,
            sentiment_label="positive",
        )

        news2 = NewsItem(
            title="Negative News",
            content="Market downturn expected",
            source="Source2",
            url="https://source2.com/news2",
            published_date=datetime(2023, 1, 1, 9, 30),
            sentiment_score=-0.6,
            sentiment_label="negative",
        )

        result = SentimentAnalysisResult(
            symbol="NIFTY",
            timestamp=datetime(2023, 1, 1, 10, 0),
            sentiment_score=0.1,
            sentiment_label="neutral",
            news_count=2,
            positive_count=1,
            negative_count=1,
            neutral_count=0,
            top_news=[news1, news2],
        )

        assert result.symbol == "NIFTY"
        assert result.sentiment_score == 0.1
        assert result.sentiment_label == "neutral"
        assert result.news_count == 2
        assert result.positive_count == 1
        assert result.negative_count == 1
        assert len(result.top_news) == 2
        assert result.top_news[0].sentiment_score == 0.8

    def test_model_validation(self) -> None:
        """Test model validation."""
        # Test invalid QuoteData
        with pytest.raises(ValidationError):
            QuoteData(
                symbol="",  # Empty symbol
                last_price=18000.50,
                open=17950.25,
                high=18050.75,
                low=17900.00,
                close=17980.50,
                volume=1000000,
                timestamp=datetime.now(),
            )

        # Test invalid HistoricalData
        with pytest.raises(ValidationError):
            HistoricalData(
                symbol="NIFTY",
                timestamp=datetime.now(),
                open=-100.0,  # Negative price
                high=18000.50,
                low=17900.00,
                close=17980.50,
                volume=500000,
                interval="1min",
            )

        # Test invalid Order
        with pytest.raises(ValidationError):
            Order(
                order_id="order_12345",
                symbol="NIFTY",
                quantity=-100,  # Negative quantity
                order_type=OrderType.LIMIT,
                price=18000.0,
                variety=OrderVariety.REGULAR,
                transaction_type=TransactionType.BUY,
                product_type=ProductType.MIS,
                status=OrderStatus.OPEN,
                timestamp=datetime.now(),
                filled_quantity=0,
            )

        # Test invalid Trade
        with pytest.raises(ValidationError):
            Trade(
                symbol="NIFTY",
                quantity=100,
                entry_price=-17950.0,  # Negative price
                entry_time=datetime.now(),
                transaction_type=TransactionType.BUY,
                product_type=ProductType.MIS,
                strategy="supertrend",
            )

        # Test invalid Signal
        with pytest.raises(ValidationError):
            Signal(
                symbol="NIFTY",
                signal_type=SignalType.BUY,
                strength=1.5,  # Strength > 1
                timestamp=datetime.now(),
                indicators={},
            )
