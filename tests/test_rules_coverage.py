"""
Comprehensive test coverage for rules.py module.
This test file aims to achieve 80%+ coverage for the CMPRulesEngine class.
"""

import datetime
from unittest.mock import patch

from loats.models import HistoricalData, Signal, SignalType, Trade
from loats.rules import CMPRulesEngine, RuleType, TradingSession, rules_engine


class TestCMPRulesEngineInitialization:
    """Test CMPRulesEngine initialization and basic properties."""

    def test_initialization(self) -> None:
        """Test that CMPRulesEngine initializes correctly."""
        engine = CMPRulesEngine()
        assert engine.modification_counter == 0
        assert engine.session_state == TradingSession.PRE_OPEN
        assert isinstance(engine.last_session_update, datetime.datetime)

    def test_rule_type_enum(self) -> None:
        """Test RuleType enumeration."""
        assert RuleType.GATING == "GATING"
        assert RuleType.RISK == "RISK"
        assert RuleType.POSITION == "POSITION"
        assert RuleType.SESSION == "SESSION"

    def test_trading_session_enum(self) -> None:
        """Test TradingSession enumeration."""
        assert TradingSession.PRE_OPEN == "PRE_OPEN"
        assert TradingSession.REGULAR == "REGULAR"
        assert TradingSession.POST_CLOSE == "POST_CLOSE"
        assert TradingSession.AFTER_HOURS == "AFTER_HOURS"


class TestSessionManagement:
    """Test trading session management functionality."""

    def test_get_current_session_pre_open(self) -> None:
        """Test PRE_OPEN session detection (9:00-9:15 AM IST)."""
        engine = CMPRulesEngine()

        # Test 9:00 AM IST (UTC 3:30 AM)
        test_time = datetime.datetime(2023, 1, 1, 3, 30, 0, tzinfo=datetime.UTC)
        session = engine.get_current_session(test_time)
        assert session == TradingSession.PRE_OPEN

        # Test 9:14 AM IST (UTC 3:44 AM)
        test_time = datetime.datetime(2023, 1, 1, 3, 44, 0, tzinfo=datetime.UTC)
        session = engine.get_current_session(test_time)
        assert session == TradingSession.PRE_OPEN

    def test_get_current_session_regular(self) -> None:
        """Test REGULAR session detection (9:15 AM-3:30 PM IST)."""
        engine = CMPRulesEngine()

        # Test 9:15 AM IST (UTC 3:45 AM)
        test_time = datetime.datetime(2023, 1, 1, 3, 45, 0, tzinfo=datetime.UTC)
        session = engine.get_current_session(test_time)
        assert session == TradingSession.REGULAR

        # Test 12:00 PM IST (UTC 6:30 AM)
        test_time = datetime.datetime(2023, 1, 1, 6, 30, 0, tzinfo=datetime.UTC)
        session = engine.get_current_session(test_time)
        assert session == TradingSession.REGULAR

        # Test 3:29 PM IST (UTC 9:59 AM)
        test_time = datetime.datetime(2023, 1, 1, 9, 59, 0, tzinfo=datetime.UTC)
        session = engine.get_current_session(test_time)
        assert session == TradingSession.REGULAR

    def test_get_current_session_post_close(self) -> None:
        """Test POST_CLOSE session detection (3:30-4:00 PM IST)."""
        engine = CMPRulesEngine()

        # Test 3:30 PM IST (UTC 10:00 AM)
        test_time = datetime.datetime(2023, 1, 1, 10, 0, 0, tzinfo=datetime.UTC)
        session = engine.get_current_session(test_time)
        assert session == TradingSession.POST_CLOSE

        # Test 3:59 PM IST (UTC 10:29 AM)
        test_time = datetime.datetime(2023, 1, 1, 10, 29, 0, tzinfo=datetime.UTC)
        session = engine.get_current_session(test_time)
        assert session == TradingSession.POST_CLOSE

    def test_get_current_session_after_hours(self) -> None:
        """Test AFTER_HOURS session detection (4:00 PM-9:00 AM IST)."""
        engine = CMPRulesEngine()

        # Test 4:00 PM IST (UTC 10:30 AM)
        test_time = datetime.datetime(2023, 1, 1, 10, 30, 0, tzinfo=datetime.UTC)
        session = engine.get_current_session(test_time)
        assert session == TradingSession.AFTER_HOURS

        # Test 8:00 PM IST (UTC 2:30 PM)
        test_time = datetime.datetime(2023, 1, 1, 14, 30, 0, tzinfo=datetime.UTC)
        session = engine.get_current_session(test_time)
        assert session == TradingSession.AFTER_HOURS

        # Test 8:59 AM IST (UTC 3:29 AM)
        test_time = datetime.datetime(2023, 1, 1, 3, 29, 0, tzinfo=datetime.UTC)
        session = engine.get_current_session(test_time)
        assert session == TradingSession.AFTER_HOURS

    def test_update_session_state(self, caplog) -> None:
        """Test session state updates."""
        engine = CMPRulesEngine()

        # Mock current time to be in REGULAR session
        test_time = datetime.datetime(2023, 1, 1, 6, 30, 0, tzinfo=datetime.UTC)

        with patch("loats.rules.datetime.datetime") as mock_datetime:
            mock_datetime.now.return_value = test_time
            mock_datetime.side_effect = lambda *args, **kw: (
                datetime.datetime(*args, **kw) if args else test_time
            )

            engine.update_session_state()
            assert engine.session_state == TradingSession.REGULAR

    def test_is_trading_allowed(self) -> None:
        """Test trading allowed check."""
        engine = CMPRulesEngine()

        # Test during REGULAR session (should be allowed)
        test_time = datetime.datetime(2023, 1, 1, 6, 30, 0, tzinfo=datetime.UTC)

        with patch("loats.rules.datetime.datetime") as mock_datetime:
            mock_datetime.now.return_value = test_time
            mock_datetime.side_effect = lambda *args, **kw: (
                datetime.datetime(*args, **kw) if args else test_time
            )

            assert engine.is_trading_allowed()

        # Test during AFTER_HOURS session (should not be allowed)
        test_time = datetime.datetime(2023, 1, 1, 14, 30, 0, tzinfo=datetime.UTC)

        with patch("loats.rules.datetime.datetime") as mock_datetime:
            mock_datetime.now.return_value = test_time
            mock_datetime.side_effect = lambda *args, **kw: (
                datetime.datetime(*args, **kw) if args else test_time
            )

            assert not engine.is_trading_allowed()


class TestIndicatorCalculations:
    """Test indicator calculation methods."""

    def test_calculate_iv_rank(self) -> None:
        """Test IV rank calculation."""
        engine = CMPRulesEngine()

        # Create sample historical data
        historical_data = [
            HistoricalData(
                symbol="NIFTY",
                timestamp=datetime.datetime(
                    2023, 1, min(i + 1, 28), tzinfo=datetime.UTC
                ),  # Fix: January has only 31 days
                open=100.0 + i,
                high=105.0 + i,
                low=95.0 + i,
                close=102.0 + i,
                volume=1000 + i * 10,
                interval="1min",
            )
            for i in range(30)
        ]

        iv_rank = engine.calculate_iv_rank(historical_data)
        assert 0 <= iv_rank <= 100

        # Test with insufficient data
        short_data = historical_data[:5]
        iv_rank_short = engine.calculate_iv_rank(short_data)
        assert iv_rank_short == 50.0  # Default neutral value (0-100 scale)

    def test_calculate_adx(self) -> None:
        """Test ADX calculation."""
        engine = CMPRulesEngine()

        # Create sample historical data
        historical_data = [
            HistoricalData(
                symbol="NIFTY",
                timestamp=datetime.datetime(
                    2023, 1, min(i + 1, 31), tzinfo=datetime.UTC
                ),
                open=100.0 + i,
                high=105.0 + i,
                low=95.0 + i,
                close=102.0 + i,
                volume=1000 + i * 10,
                interval="1min",
            )
            for i in range(20)
        ]

        adx = engine.calculate_adx(historical_data)
        assert isinstance(adx, float)
        assert adx >= 0

        # Test with insufficient data
        short_data = historical_data[:5]
        adx_short = engine.calculate_adx(short_data)
        assert adx_short == 25.0  # Default neutral value

    def test_get_vix_level(self) -> None:
        """Test VIX level retrieval."""
        engine = CMPRulesEngine()
        vix = engine.get_vix_level()
        assert vix == 18.5  # Default value


class TestGatingRules:
    """Test gating rules functionality."""

    def test_apply_gating_rules_sell_signal_pass(self) -> None:
        """Test gating rules for SELL signal that should pass."""
        engine = CMPRulesEngine()

        # Create a SELL signal
        signal = Signal(
            signal_id="test-001",
            symbol="NIFTY",
            signal_type=SignalType.SELL,
            strength=0.8,
            timestamp=datetime.datetime(2023, 1, 1, tzinfo=datetime.UTC),
            indicators={"rsi": 30.0, "macd": -0.5},
        )

        # Create historical data that should pass SELL rules
        # IV-rank > 40, ADX < 25, VIX > 15
        # Range-bound alternating bars: high realized vol (IV rank ~50)
        # with +DM/-DM perfectly balanced (ADX ~ 0, no trend)
        historical_data = [
            HistoricalData(
                symbol="NIFTY",
                timestamp=datetime.datetime(
                    2023, 1, min(i + 1, 31), tzinfo=datetime.UTC
                ),
                open=100.0,
                high=112.0 if i % 2 == 0 else 108.0,
                low=88.0 if i % 2 == 0 else 92.0,
                close=105.0 if i % 2 == 0 else 95.0,
                volume=1000 + i * 50,
                interval="1min",
            )
            for i in range(30)
        ]

        # Mock trading session to be REGULAR
        with patch.object(engine, "is_trading_allowed", return_value=True):
            result, details = engine.apply_gating_rules(signal, historical_data, 105.0)

            assert result
            assert details["reason"] == "gating_passed"
            assert "iv_rank" in details
            assert "adx" in details
            assert "vix" in details

    def test_apply_gating_rules_sell_signal_fail(self) -> None:
        """Test gating rules for SELL signal that should fail."""
        engine = CMPRulesEngine()

        # Create a SELL signal
        signal = Signal(
            signal_id="test-001",
            symbol="NIFTY",
            signal_type=SignalType.SELL,
            strength=0.8,
            timestamp=datetime.datetime(2023, 1, 1, tzinfo=datetime.UTC),
            indicators={"rsi": 70.0, "macd": 0.5},
        )

        # Create historical data that should fail SELL rules
        historical_data = [
            HistoricalData(
                symbol="NIFTY",
                timestamp=datetime.datetime(
                    2023, 1, min(i + 1, 31), tzinfo=datetime.UTC
                ),
                open=100.0 + i,
                high=101.0 + i,
                low=99.0 + i,
                close=100.0 + i,
                volume=1000 + i * 10,
                interval="1min",
            )
            for i in range(30)
        ]

        # Mock trading session to be REGULAR
        with patch.object(engine, "is_trading_allowed", return_value=True):
            result, details = engine.apply_gating_rules(signal, historical_data, 100.0)

            assert not result
            assert details["reason"] == "gating_failed"
            assert "iv_pass" in details
            assert "adx_pass" in details
            assert "vix_pass" in details

    def test_apply_gating_rules_buy_signal_pass(self) -> None:
        """Test gating rules for BUY signal that should pass."""
        engine = CMPRulesEngine()

        # Create a BUY signal
        signal = Signal(
            signal_id="test-001",
            symbol="NIFTY",
            signal_type=SignalType.BUY,
            strength=0.8,
            timestamp=datetime.datetime(2023, 1, 1, tzinfo=datetime.UTC),
            indicators={"rsi": 70.0, "macd": 0.5},
        )

        # Create historical data that should pass BUY rules
        # IV-rank < 60, ADX > 25, VIX < 15
        historical_data = [
            HistoricalData(
                symbol="NIFTY",
                timestamp=datetime.datetime(
                    2023, 1, min(i + 1, 31), tzinfo=datetime.UTC
                ),
                open=100.0 + i * 3,
                high=115.0 + i * 3,
                low=85.0 + i * 3,
                close=110.0 + i * 3,
                volume=1000 + i * 100,
                interval="1min",
            )
            for i in range(30)
        ]

        # Mock trading session to be REGULAR and VIX < 15 for BUY to pass
        with patch.object(engine, "is_trading_allowed", return_value=True):
            with patch.object(engine, "get_vix_level", return_value=12.0):
                result, details = engine.apply_gating_rules(
                    signal, historical_data, 110.0
                )

                assert result
                assert details["reason"] == "gating_passed"

    def test_apply_gating_rules_buy_signal_fail(self) -> None:
        """Test gating rules for BUY signal that should fail."""
        engine = CMPRulesEngine()

        # Create a BUY signal
        signal = Signal(
            signal_id="test-001",
            symbol="NIFTY",
            signal_type=SignalType.BUY,
            strength=0.8,
            timestamp=datetime.datetime(2023, 1, 1, tzinfo=datetime.UTC),
            indicators={"rsi": 30.0, "macd": -0.5},
        )

        # Create historical data that should fail BUY rules
        historical_data = [
            HistoricalData(
                symbol="NIFTY",
                timestamp=datetime.datetime(
                    2023, 1, min(i + 1, 31), tzinfo=datetime.UTC
                ),
                open=100.0 + i,
                high=101.0 + i,
                low=99.0 + i,
                close=100.0 + i,
                volume=1000 + i * 10,
                interval="1min",
            )
            for i in range(30)
        ]

        # Mock trading session to be REGULAR
        with patch.object(engine, "is_trading_allowed", return_value=True):
            result, details = engine.apply_gating_rules(signal, historical_data, 100.0)

            assert not result
            assert details["reason"] == "gating_failed"

    def test_apply_gating_rules_trading_not_allowed(self) -> None:
        """Test gating rules when trading is not allowed."""
        engine = CMPRulesEngine()

        # Create any signal
        signal = Signal(
            signal_id="test-001",
            symbol="NIFTY",
            signal_type=SignalType.BUY,
            strength=0.8,
            timestamp=datetime.datetime(2023, 1, 1, tzinfo=datetime.UTC),
            indicators={"rsi": 50.0},
        )

        historical_data = [
            HistoricalData(
                symbol="NIFTY",
                timestamp=datetime.datetime(
                    2023, 1, min(i + 1, 31), tzinfo=datetime.UTC
                ),
                open=100.0 + i,
                high=101.0 + i,
                low=99.0 + i,
                close=100.0 + i,
                volume=1000 + i * 10,
                interval="1min",
            )
            for i in range(30)
        ]

        # Mock trading session to be AFTER_HOURS
        with patch.object(engine, "is_trading_allowed", return_value=False):
            result, details = engine.apply_gating_rules(signal, historical_data, 100.0)

            assert not result
            assert details["reason"] == "trading_not_allowed"
            assert "session" in details

    def test_apply_gating_rules_neutral_signal(self) -> None:
        """Test gating rules for NEUTRAL/HOLD signals."""
        engine = CMPRulesEngine()

        # Create a NEUTRAL signal
        signal = Signal(
            signal_id="test-001",
            symbol="NIFTY",
            signal_type=SignalType.NEUTRAL,
            strength=0.5,
            timestamp=datetime.datetime(2023, 1, 1, tzinfo=datetime.UTC),
            indicators={},
        )

        historical_data = [
            HistoricalData(
                symbol="NIFTY",
                timestamp=datetime.datetime(
                    2023, 1, min(i + 1, 31), tzinfo=datetime.UTC
                ),
                open=100.0 + i,
                high=101.0 + i,
                low=99.0 + i,
                close=100.0 + i,
                volume=1000 + i * 10,
                interval="1min",
            )
            for i in range(30)
        ]

        # Mock trading session to be REGULAR
        with patch.object(engine, "is_trading_allowed", return_value=True):
            result, details = engine.apply_gating_rules(signal, historical_data, 100.0)

            assert result
            assert details["reason"] == "neutral_signal"


class TestPositionLimits:
    """Test position limit functionality."""

    def test_check_position_limits_nifty(self) -> None:
        """Test position limits for NIFTY."""
        engine = CMPRulesEngine()

        # Test under limit
        current_positions = [
            Trade(
                trade_id="trade-001",
                symbol="NIFTY",
                quantity=50,
                entry_price=100.0,
                stop_loss=95.0,
                target=105.0,
                trade_type="BUY",
                status="OPEN",
                entry_time=datetime.datetime(2023, 1, 1, tzinfo=datetime.UTC),
            )
        ]

        result, details = engine.check_position_limits("NIFTY", current_positions)
        assert result
        assert details["reason"] == "position_limit_ok"
        assert details["current_quantity"] == 50
        assert details["max_allowed"] == 125  # 5 lots * 25

        # Test at limit
        current_positions = [
            Trade(
                trade_id="trade-001",
                symbol="NIFTY",
                quantity=125,  # 5 lots exactly
                entry_price=100.0,
                stop_loss=95.0,
                target=105.0,
                trade_type="BUY",
                status="OPEN",
                entry_time=datetime.datetime(2023, 1, 1, tzinfo=datetime.UTC),
            )
        ]

        result, details = engine.check_position_limits("NIFTY", current_positions)
        assert not result
        assert details["reason"] == "position_limit_exceeded"

        # Test over limit
        current_positions = [
            Trade(
                trade_id="trade-001",
                symbol="NIFTY",
                quantity=150,  # 6 lots
                entry_price=100.0,
                stop_loss=95.0,
                target=105.0,
                trade_type="BUY",
                status="OPEN",
                entry_time=datetime.datetime(2023, 1, 1, tzinfo=datetime.UTC),
            )
        ]

        result, details = engine.check_position_limits("NIFTY", current_positions)
        assert not result
        assert details["reason"] == "position_limit_exceeded"

    def test_check_position_limits_banknifty(self) -> None:
        """Test position limits for BANKNIFTY."""
        engine = CMPRulesEngine()

        # Test under limit
        current_positions = [
            Trade(
                trade_id="trade-001",
                symbol="BANKNIFTY",
                quantity=30,
                entry_price=100.0,
                stop_loss=95.0,
                target=105.0,
                trade_type="BUY",
                status="OPEN",
                entry_time=datetime.datetime(2023, 1, 1, tzinfo=datetime.UTC),
            )
        ]

        result, details = engine.check_position_limits("BANKNIFTY", current_positions)
        assert result
        assert details["reason"] == "position_limit_ok"
        assert details["max_allowed"] == 75  # 3 lots * 25

    def test_check_position_limits_other_symbol(self) -> None:
        """Test position limits for other symbols."""
        engine = CMPRulesEngine()

        # Test under limit
        current_positions = [
            Trade(
                trade_id="trade-001",
                symbol="RELIANCE",
                quantity=500,
                entry_price=100.0,
                stop_loss=95.0,
                target=105.0,
                trade_type="BUY",
                status="OPEN",
                entry_time=datetime.datetime(2023, 1, 1, tzinfo=datetime.UTC),
            )
        ]

        result, details = engine.check_position_limits("RELIANCE", current_positions)
        assert result
        assert details["reason"] == "position_limit_ok"


class TestCircuitBreakers:
    """Test circuit breaker functionality."""

    def test_check_circuit_breakers_insufficient_history(self) -> None:
        """Test circuit breakers with insufficient trade history."""
        engine = CMPRulesEngine()

        recent_trades = [
            Trade(
                trade_id="trade-001",
                symbol="NIFTY",
                quantity=25,
                entry_price=100.0,
                stop_loss=95.0,
                target=105.0,
                trade_type="BUY",
                status="CLOSED",
                pnl=-100.0,
                metadata={"source": "ta"},
                entry_time=datetime.datetime(2023, 1, 1, tzinfo=datetime.UTC),
            ),
            Trade(
                trade_id="trade-002",
                symbol="NIFTY",
                quantity=25,
                entry_price=100.0,
                stop_loss=95.0,
                target=105.0,
                trade_type="BUY",
                status="CLOSED",
                pnl=-150.0,
                metadata={"source": "ta"},
                entry_time=datetime.datetime(2023, 1, 1, tzinfo=datetime.UTC),
            ),
        ]

        result, details = engine.check_circuit_breakers("NIFTY", recent_trades)
        assert result
        assert details["reason"] == "insufficient_trade_history"

    def test_check_circuit_breakers_consecutive_losses(self) -> None:
        """Test circuit breakers for consecutive losses."""
        engine = CMPRulesEngine()

        recent_trades = [
            Trade(
                trade_id=f"trade-{i:03d}",
                symbol="NIFTY",
                quantity=25,
                entry_price=100.0,
                stop_loss=95.0,
                target=105.0,
                trade_type="BUY",
                status="CLOSED",
                pnl=-100.0 if i >= 7 else 100.0,  # Last 3 are losses (i=7,8,9)
                metadata={"source": "ta"},
                entry_time=datetime.datetime(2023, 1, 1, tzinfo=datetime.UTC),
            )
            for i in range(10)
        ]

        result, details = engine.check_circuit_breakers("NIFTY", recent_trades)
        assert not result
        assert details["reason"] == "consecutive_losses_circuit_breaker"
        assert details["consecutive_losses"] == 3

    def test_check_circuit_breakers_loss_ratio(self) -> None:
        """Test circuit breakers for loss ratio."""
        engine = CMPRulesEngine()

        recent_trades = [
            Trade(
                trade_id=f"trade-{i:03d}",
                symbol="NIFTY",
                quantity=25,
                entry_price=100.0,
                stop_loss=95.0,
                target=105.0,
                trade_type="BUY",
                status="CLOSED",
                pnl=-100.0 if i % 2 == 0 else 100.0,  # 5 losses, 5 wins in last 10
                metadata={"source": "ta"},
                entry_time=datetime.datetime(2023, 1, 1, tzinfo=datetime.UTC),
            )
            for i in range(10)
        ]

        result, details = engine.check_circuit_breakers("NIFTY", recent_trades)
        assert not result
        assert details["reason"] == "loss_ratio_circuit_breaker"
        assert details["losing_trades"] == 5

    def test_check_circuit_breakers_pass(self) -> None:
        """Test circuit breakers that should pass."""
        engine = CMPRulesEngine()

        recent_trades = [
            Trade(
                trade_id=f"trade-{i:03d}",
                symbol="NIFTY",
                quantity=25,
                entry_price=100.0,
                stop_loss=95.0,
                target=105.0,
                trade_type="BUY",
                status="CLOSED",
                pnl=100.0 if i % 3 != 0 else -100.0,  # Mostly wins
                metadata={"source": "ta"},
                entry_time=datetime.datetime(2023, 1, 1, tzinfo=datetime.UTC),
            )
            for i in range(10)
        ]

        result, details = engine.check_circuit_breakers("NIFTY", recent_trades)
        assert result
        assert details["reason"] == "circuit_breakers_ok"


class TestModificationCounter:
    """Test modification counter functionality."""

    def test_modification_counter_operations(self) -> None:
        """Test modification counter increment and reset."""
        engine = CMPRulesEngine()

        # Initial state
        assert engine.get_modification_count() == 0

        # Increment
        count = engine.increment_modification_counter()
        assert count == 1
        assert engine.get_modification_count() == 1

        # Multiple increments
        count = engine.increment_modification_counter()
        assert count == 2
        assert engine.get_modification_count() == 2

        # Reset
        engine.reset_modification_counter()
        assert engine.get_modification_count() == 0


class TestModuleLevelSingleton:
    """Test module-level singleton instance."""

    def test_rules_engine_singleton(self) -> None:
        """Test that rules_engine is a proper singleton."""

        assert isinstance(rules_engine, CMPRulesEngine)
        assert rules_engine.modification_counter == 0
        # session_state is clock-dependent (IST market hours); assert it is a
        # valid session rather than a specific time-of-day value.
        assert rules_engine.session_state in TradingSession

        # Test that it's the same instance
        from loats.rules import rules_engine as rules_engine_2

        assert rules_engine is rules_engine_2
