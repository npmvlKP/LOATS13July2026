"""Unit tests for loats.rules CMPRulesEngine (HC-12/13 coverage lift)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from loats.models import HistoricalData, Signal, SignalType, Trade, TransactionType
from loats.rules import CMPRulesEngine, RuleType, TradingSession, rules_engine


def _hist(n: int = 40, base: float = 100.0) -> list[HistoricalData]:
    now = datetime.now(UTC)
    out: list[HistoricalData] = []
    price = base
    for i in range(n):
        price = price + (0.2 if i % 2 == 0 else -0.1)
        out.append(
            HistoricalData(
                symbol="NIFTY",
                timestamp=now - timedelta(minutes=n - i),
                open=price,
                high=price + 0.5,
                low=price - 0.5,
                close=price,
                volume=1000 + i,
                interval="1min",
            )
        )
    return out


def _trade(
    symbol: str = "NIFTY", qty: int = 25, pnl: float | None = -10.0, source: str = "ta"
) -> Trade:
    return Trade(
        symbol=symbol,
        quantity=qty,
        entry_price=100.0,
        entry_time=datetime.now(UTC),
        transaction_type=TransactionType.BUY,
        pnl=pnl,
        stop_loss=95.0,
        metadata={"source": source},
    )


def test_enums_and_singleton() -> None:
    assert RuleType.GATING.value == "GATING"
    assert TradingSession.REGULAR.value == "REGULAR"
    assert isinstance(rules_engine, CMPRulesEngine)


def test_session_detection_all_buckets() -> None:
    eng = CMPRulesEngine()
    # times are UTC; engine adds +5:30 for IST
    # IST 09:00 -> UTC 03:30
    pre = datetime(2026, 8, 31, 3, 30, tzinfo=UTC)
    assert eng.get_current_session(pre) == TradingSession.PRE_OPEN

    # IST 09:20 -> UTC 03:50
    reg1 = datetime(2026, 8, 31, 3, 50, tzinfo=UTC)
    assert eng.get_current_session(reg1) == TradingSession.REGULAR

    # IST 11:00 -> UTC 05:30
    reg2 = datetime(2026, 8, 31, 5, 30, tzinfo=UTC)
    assert eng.get_current_session(reg2) == TradingSession.REGULAR

    # IST 15:00 -> UTC 09:30
    reg3 = datetime(2026, 8, 31, 9, 30, tzinfo=UTC)
    assert eng.get_current_session(reg3) == TradingSession.REGULAR

    # IST 15:45 -> UTC 10:15
    post = datetime(2026, 8, 31, 10, 15, tzinfo=UTC)
    assert eng.get_current_session(post) == TradingSession.POST_CLOSE

    # IST 18:00 -> UTC 12:30
    after = datetime(2026, 8, 31, 12, 30, tzinfo=UTC)
    assert eng.get_current_session(after) == TradingSession.AFTER_HOURS

    # IST 02:00 -> UTC 20:30 previous day
    night = datetime(2026, 8, 30, 20, 30, tzinfo=UTC)
    assert eng.get_current_session(night) == TradingSession.AFTER_HOURS

    # None uses now
    assert eng.get_current_session(None) in set(TradingSession)


def test_update_session_and_trading_allowed(monkeypatch: pytest.MonkeyPatch) -> None:
    eng = CMPRulesEngine()
    eng.session_state = TradingSession.PRE_OPEN
    monkeypatch.setattr(
        eng,
        "get_current_session",
        lambda current_time=None: TradingSession.REGULAR,
    )
    eng.update_session_state()
    assert eng.session_state == TradingSession.REGULAR
    assert eng.is_trading_allowed() is True

    monkeypatch.setattr(
        eng,
        "get_current_session",
        lambda current_time=None: TradingSession.AFTER_HOURS,
    )
    eng.update_session_state()
    assert eng.is_trading_allowed() is False


def test_iv_rank_and_adx() -> None:
    eng = CMPRulesEngine()
    short = _hist(5)
    assert eng.calculate_iv_rank(short) == 0.5
    assert eng.calculate_adx(short) == 25.0

    long_h = _hist(50)
    iv = eng.calculate_iv_rank(long_h, window=30)
    assert 0.0 <= iv <= 100.0
    adx = eng.calculate_adx(long_h, period=14)
    assert isinstance(adx, float)


def test_vix_gate_paths() -> None:
    eng = CMPRulesEngine()
    # unknown -> block_all default
    assert eng.get_vix_level() is None
    assert eng.check_vix_gate("BUY") is False
    assert eng.check_vix_gate("SELL") is False
    assert eng.check_vix_gate("HOLD") is False

    eng.set_vix_level(None)
    assert eng.get_vix_level() is None

    eng.set_vix_level(18.0)
    assert eng.get_vix_level() == pytest.approx(18.0)
    assert eng.check_vix_gate("SELL") is True
    assert eng.check_vix_gate("BUY") is False

    eng.set_vix_level(10.0)
    assert eng.check_vix_gate("BUY") is True
    assert eng.check_vix_gate("SELL") is False

    # stale path
    eng._vix_timestamp = datetime.now(UTC) - timedelta(hours=2)
    assert eng.get_vix_level() is None

    # missing timestamp
    eng._vix_level = 12.0
    eng._vix_timestamp = None
    assert eng.get_vix_level() is None


def test_vix_gate_uses_settings_threshold(monkeypatch: pytest.MonkeyPatch) -> None:
    """F8-M-07: gate thresholds must come from Settings, not inline literals.

    Pins CMP Rule 10 semantics against the settings-derived threshold:
    SELL passes strictly above, BUY strictly below, boundary blocks both.
    """
    from loats import rules as rules_mod

    # Capture the real settings BEFORE monkeypatching; falling through to
    # rules_mod.settings inside __getattr__ would resolve to the proxy
    # itself and recurse infinitely.
    real_settings = rules_mod.settings

    class _ThresholdProxy:
        def __getattr__(self, name: str) -> object:
            if name == "vix_gate_threshold":
                return 10.0
            return getattr(real_settings, name)

    monkeypatch.setattr(rules_mod, "settings", _ThresholdProxy())
    eng = CMPRulesEngine()
    eng.set_vix_level(10.0)
    # Boundary: VIX == threshold blocks BOTH directions (strict compare).
    assert eng.check_vix_gate("BUY") is False
    assert eng.check_vix_gate("SELL") is False
    eng.set_vix_level(11.0)
    assert eng.check_vix_gate("SELL") is True
    assert eng.check_vix_gate("BUY") is False
    eng.set_vix_level(9.0)
    assert eng.check_vix_gate("BUY") is True
    assert eng.check_vix_gate("SELL") is False


def test_vix_fail_mode_block_buy(monkeypatch: pytest.MonkeyPatch) -> None:
    eng = CMPRulesEngine()
    from loats import rules as rules_mod

    # Capture the real settings BEFORE monkeypatching; falling through to
    # rules_mod.settings inside __getattr__ would resolve to the proxy
    # itself and recurse infinitely.
    real_settings = rules_mod.settings

    class _SettingsProxy:
        def __getattr__(self, name: str) -> object:
            if name == "vix_fail_mode":
                return "block_buy"
            return getattr(real_settings, name)

    monkeypatch.setattr(rules_mod, "settings", _SettingsProxy())
    eng._vix_level = None
    assert eng.check_vix_gate("BUY") is False
    assert eng.check_vix_gate("SELL") is True


def test_apply_gating_rules() -> None:
    eng = CMPRulesEngine()
    hist = _hist(40)
    eng.session_state = TradingSession.AFTER_HOURS
    # force not allowed
    eng.session_state = TradingSession.AFTER_HOURS

    def _no_trade() -> bool:
        return False

    eng.is_trading_allowed = _no_trade  # type: ignore[method-assign]
    sig = Signal(
        symbol="NIFTY",
        signal_type=SignalType.SELL,
        strength=0.9,
        timestamp=datetime.now(UTC),
    )
    ok, info = eng.apply_gating_rules(sig, hist, 100.0)
    assert ok is False
    assert info["reason"] == "trading_not_allowed"

    eng.is_trading_allowed = lambda: True  # type: ignore[method-assign]
    eng.set_vix_level(20.0)
    ok_s, info_s = eng.apply_gating_rules(sig, hist, 100.0)
    assert isinstance(ok_s, bool)
    assert "iv_rank" in info_s

    buy = Signal(
        symbol="NIFTY",
        signal_type=SignalType.BUY,
        strength=0.9,
        timestamp=datetime.now(UTC),
    )
    eng.set_vix_level(10.0)
    ok_b, info_b = eng.apply_gating_rules(buy, hist, 100.0)
    assert isinstance(ok_b, bool)

    hold = Signal(
        symbol="NIFTY",
        signal_type=SignalType.HOLD,
        strength=0.5,
        timestamp=datetime.now(UTC),
    )
    ok_h, info_h = eng.apply_gating_rules(hold, hist, 100.0)
    assert ok_h is True
    assert info_h["reason"] == "neutral_signal"


def test_position_limits_and_circuit_breakers() -> None:
    eng = CMPRulesEngine()
    ok, info = eng.check_position_limits("NIFTY", [])
    assert ok is True
    assert info["reason"] == "position_limit_ok"

    many = [_trade(qty=25) for _ in range(5)]
    ok2, info2 = eng.check_position_limits("NIFTY", many)
    assert ok2 is False
    assert info2["reason"] == "position_limit_exceeded"

    ok3, _ = eng.check_position_limits("BANKNIFTY", [])
    assert ok3 is True
    ok4, _ = eng.check_position_limits("RELIANCE", [])
    assert ok4 is True

    # insufficient history
    ok5, info5 = eng.check_circuit_breakers("NIFTY", [_trade(), _trade()])
    assert ok5 is True
    assert info5["reason"] == "insufficient_trade_history"

    # consecutive losses
    losses = [_trade(pnl=-1.0) for _ in range(5)]
    ok6, info6 = eng.check_circuit_breakers("NIFTY", losses)
    assert ok6 is False
    assert "circuit_breaker" in info6["reason"]

    # mixed then ok path with winners interrupting
    mixed = [
        _trade(pnl=-1.0),
        _trade(pnl=1.0),
        _trade(pnl=-1.0),
        _trade(pnl=-1.0),
        _trade(pnl=2.0),
    ]
    ok7, info7 = eng.check_circuit_breakers("NIFTY", mixed)
    assert ok7 is True
    assert info7["reason"] == "circuit_breakers_ok"

    # 5 losses in 10
    ten = [_trade(pnl=-1.0 if i < 5 else 1.0) for i in range(10)]
    # consecutive may fire first; either circuit path is fine
    ok8, info8 = eng.check_circuit_breakers("NIFTY", ten)
    assert ok8 is False


def test_modification_counter() -> None:
    eng = CMPRulesEngine()
    assert eng.get_modification_count() == 0
    assert eng.increment_modification_counter() == 1
    assert eng.increment_modification_counter() == 2
    eng.reset_modification_counter()
    assert eng.get_modification_count() == 0
