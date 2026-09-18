"""F9-C-01 / F9-M-04 regression tests: iv_rank correctness + fail-closed history.

Legacy contract (pre-fix, proven RED on HEAD 57b77a0):
  calculate_iv_rank saturated to 100.0 for every sufficient-history input
  (annualized sigma over daily spread, clipped) and returned a silent 0.5
  when len(history) < window -- which PASSED the BUY gate (< 30) on
  insufficient data. All 527 live gating rejects carried iv_rank 100.0 and
  all 1,542 BUY/PENDING decisions were fallback artifacts.

Fixed contract (CMP conformance; TODO-1 resolution):
  - iv_rank = 100 x percentile rank of the CURRENT bar's absolute return
    within the window's absolute-return range, units-consistent (daily vs
    daily), never clipped into degeneracy.
  - Persisted per-symbol option-chain ATM IV (fed by the options-flow
    producer) takes precedence over the HV percentile; falls back to the
    consistent-unit HV percentile when no chain IV history exists.
  - Insufficient history is LOUD: float("-inf") from the calculator and a
    fail-closed `insufficient_history` gating outcome blocking BOTH
    directions (no silent 0.5 -- that value passed the BUY gate).
"""

from __future__ import annotations

import json
import random
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from loats.database import Database
from loats.models import HistoricalData, Signal, SignalType
from loats.rules import CMPRulesEngine


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------
def _bars(closes: list[float], interval: str = "5min") -> list[HistoricalData]:
    t0 = datetime(2026, 9, 1, 4, 15, tzinfo=UTC)  # 09:45 IST, REGULAR
    return [
        HistoricalData(
            symbol="NIFTY",
            timestamp=t0 + timedelta(minutes=5 * i),
            open=c,
            high=c * 1.001,
            low=c * 0.999,
            close=c,
            volume=1000,
            interval=interval,
        )
        for i, c in enumerate(closes)
    ]


def _regime(daily_vol: float, seed: int, n: int = 40) -> list[HistoricalData]:
    """Synthetic daily bars with a given daily-vol regime (FR9 probe shape)."""
    rnd = random.Random(seed)
    price = 100.0
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    out: list[HistoricalData] = []
    for i in range(n):
        price *= 1.0 + rnd.gauss(0.0, daily_vol)
        out.append(
            HistoricalData(
                symbol="NIFTY",
                timestamp=t0 + timedelta(days=i),
                open=price,
                high=price * 1.001,
                low=price * 0.999,
                close=price,
                volume=1000,
                interval="1day",
            )
        )
    return out


def _grind_then_quiet(n_pairs: int = 15) -> list[HistoricalData]:
    """31 bars: sustained +0.4%/-0.1% grind (ADX>25) ending on a +0.05% bar."""
    closes = [100.0]
    for i in range(n_pairs):
        up = closes[-1] * 1.004
        closes.append(up)
        if i < n_pairs - 1:
            closes.append(up * 0.999)
    closes.append(closes[-1] * 1.0005)
    return _bars(closes)


def _chop_then_spike(n: int = 29) -> list[HistoricalData]:
    """30 bars: chop (+-1.5%) ending on a +2% spike (largest |return|)."""
    closes = [
        100.0 + (1.5 if i % 2 == 0 else -1.5) * (1 if (i // 4) % 2 else -1)
        for i in range(n)
    ]
    closes.append(closes[-1] * 1.02)
    return _bars(closes)


def _buy_signal() -> Signal:
    return Signal(
        symbol="NIFTY",
        signal_type=SignalType.BUY,
        strength=0.9,
        timestamp=datetime.now(UTC),
    )


def _sell_signal() -> Signal:
    return Signal(
        symbol="NIFTY",
        signal_type=SignalType.SELL,
        strength=0.9,
        timestamp=datetime.now(UTC),
    )


def _gating_engine(vix: float) -> CMPRulesEngine:
    eng = CMPRulesEngine()
    eng.set_vix_level(vix)
    eng.is_trading_allowed = lambda: True  # type: ignore[method-assign]
    return eng


def _sigs(
    n: int, base_str: float = 0.75, st: SignalType = SignalType.BUY
) -> list[Signal]:
    """Decision-batch signals across 4 enum sources (test_trade_decision shape)."""
    from loats.strength import StrengthSource

    srcs = [
        StrengthSource.TECHNICAL_ANALYSIS,
        StrengthSource.SENTIMENT,
        StrengthSource.PRICE_ACTION,
        StrengthSource.VOLATILITY,
    ]
    now = datetime.now(UTC)
    return [
        Signal(
            symbol="NIFTY",
            signal_type=st,
            strength=base_str - i * 0.05,
            timestamp=now - timedelta(seconds=i * 30),
            indicators={"v": 0.5 + i * 0.1},
            confidence=0.8 - i * 0.05,
            metadata={"source": srcs[i % len(srcs)].value},
        )
        for i in range(min(n, len(srcs)))
    ]


def _funds() -> Any:
    from loats.models import FundsData

    return FundsData(
        available_cash=100000.0,
        utilized_margin=20000.0,
        available_margin=80000.0,
        total_equity=120000.0,
        timestamp=datetime.now(UTC),
    )


# --------------------------------------------------------------------------
# (1) Property/distribution: randomized vol regimes must NOT saturate
# --------------------------------------------------------------------------
def test_iv_rank_not_saturated_across_vol_regimes() -> None:
    """FR9 probe: 0.2%-4% daily-vol regimes x 3 seeds must not saturate.

    Legacy code returned 100.0 for every cell (RED on 57b77a0, 15/15).
    Percentile rank is scale-invariant, so the degeneracy property is the
    right assertion here: values must be distinct, bounded, and free of
    the legacy saturation (identically 100.0) and of an identically-flat
    fallback.
    """
    eng = CMPRulesEngine()
    values = [
        eng.calculate_iv_rank(_regime(dv, seed))
        for dv in (0.002, 0.005, 0.01, 0.02, 0.04)
        for seed in (11, 23, 47)
    ]
    assert len(values) == 15
    assert len(set(values)) >= 3, f"iv_rank is degenerate: {values}"
    assert all(0.0 <= v <= 100.0 for v in values)
    assert not all(v == 100.0 for v in values), "saturation regression"
    assert not all(v == 0.0 for v in values), "flat-fallback regression"


# --------------------------------------------------------------------------
# (2) Hand-computed rank (recommended test 4): units-consistent percentile
# --------------------------------------------------------------------------
def test_iv_rank_current_between_min_and_max() -> None:
    """Mid-window rank with EXACT arithmetic: |ret| = [4%, 0.5%, 1%, 2%].

    Closes are built by a multiplicative chain so each bar's return is
    exact: current 2% -> (2.0 - 0.5) / (4.0 - 0.5) x 100 = 42.857...
    """
    eng = CMPRulesEngine()
    closes = [100.0]
    closes.append(closes[-1] * 1.04)  # +4%
    closes.append(closes[-1] * 0.995)  # -0.5%
    closes.append(closes[-1] * 0.99)  # -1%
    closes.append(closes[-1] * 1.02)  # +2% (current)
    expected = (2.0 - 0.5) / (4.0 - 0.5) * 100.0
    assert eng.calculate_iv_rank(_bars(closes), window=5) == pytest.approx(
        expected, rel=1e-9
    )


def test_iv_rank_current_at_window_max_is_100() -> None:
    """Current |return| == window max -> rank 100 (SELL leg reachable)."""
    eng = CMPRulesEngine()
    closes = [100.0, 101.0, 102.0, 101.5, 104.0]  # last |ret|=2.485 is max
    assert eng.calculate_iv_rank(_bars(closes), window=5) == pytest.approx(100.0)


def test_iv_rank_mid_window_value() -> None:
    """Hand-computed mid value: |ret| [1, 2, 4, 0.5]; current 0.5 -> rank 0."""
    eng = CMPRulesEngine()
    closes = [100.0, 101.0, 103.02, 107.1408, 107.6764]  # |ret| 1,2,4,0.5
    assert eng.calculate_iv_rank(_bars(closes), window=5) == pytest.approx(
        0.0, abs=1e-3
    )


# --------------------------------------------------------------------------
# (3) Degenerate input: zero |return| spread -> 0.0 (min), never silent 0.5
# --------------------------------------------------------------------------
def test_iv_rank_zero_spread_returns_zero_not_neutral() -> None:
    eng = CMPRulesEngine()
    closes = [100.0, 100.5, 100.0, 100.5, 100.0]  # |ret| all 0.5 -> spread 0
    assert eng.calculate_iv_rank(_bars(closes), window=5) == 0.0


def test_iv_rank_flat_closes_return_zero() -> None:
    eng = CMPRulesEngine()
    closes = [100.0] * 6  # returns all exactly 0 -> max==min==0 -> 0.0
    assert eng.calculate_iv_rank(_bars(closes), window=6) == 0.0


# --------------------------------------------------------------------------
# (4) F9-M-04: insufficient history is LOUD and fails BOTH directions closed
# --------------------------------------------------------------------------
def test_insufficient_history_returns_negative_infinity() -> None:
    eng = CMPRulesEngine()
    short = _bars([100.0 + (0.2 if i % 2 == 0 else -0.1) for i in range(29)])
    assert eng.calculate_iv_rank(short) == float("-inf")


def test_boundary_len_equal_window_computes_for_real() -> None:
    """len == window is the documented boundary: computes, not fallback."""
    eng = CMPRulesEngine()
    hist30 = _bars([100.0 + (0.2 if i % 2 == 0 else -0.1) for i in range(30)])
    assert eng.calculate_iv_rank(hist30) != float("-inf")


def test_insufficient_history_blocks_buy_and_sell_in_gating() -> None:
    eng = _gating_engine(vix=10.0)
    short = _bars([100.0 + (0.2 if i % 2 == 0 else -0.1) for i in range(29)])

    ok_b, info_b = eng.apply_gating_rules(_buy_signal(), short, 100.0)
    assert ok_b is False
    assert info_b["reason"] == "insufficient_history"
    assert info_b["iv_pass"] is False
    assert info_b["adx_pass"] is False
    assert info_b["vix_pass"] is False

    eng.set_vix_level(20.0)  # even a SELL-friendly VIX must not pass
    ok_s, info_s = eng.apply_gating_rules(_sell_signal(), short, 100.0)
    assert ok_s is False
    assert info_s["reason"] == "insufficient_history"
    assert info_s["iv_pass"] is False


# --------------------------------------------------------------------------
# (5) Both CMP directions reachable on real (non-saturated) ranks
# --------------------------------------------------------------------------
def test_buy_gate_reachable_at_low_iv_rank() -> None:
    """Grinding trend + quiet final bar -> rank<30 -> BUY leg passes (VIX<15).

    RED on legacy HEAD: rank saturated to 100.0 -> BUY unreachable (F9-C-01).
    """
    eng = _gating_engine(vix=10.0)
    hist = _grind_then_quiet()
    assert len(hist) == 31
    adx = eng.calculate_adx(hist)
    assert adx > 25.0, f"fixture must produce trending ADX, got {adx}"
    ok, info = eng.apply_gating_rules(_buy_signal(), hist, 100.0)
    assert info["iv_rank"] < 30.0, f"fixture rank must be <30, got {info['iv_rank']}"
    assert ok is True
    assert info["reason"] == "gating_passed"


def test_sell_gate_reachable_at_high_iv_rank() -> None:
    """Chop + +2% spike -> rank=100 -> SELL leg passes (VIX>15, ADX<25)."""
    eng = _gating_engine(vix=20.0)
    hist = _chop_then_spike()
    adx = eng.calculate_adx(hist)
    assert adx < 25.0, f"fixture must produce choppy ADX, got {adx}"
    ok, info = eng.apply_gating_rules(_sell_signal(), hist, 100.0)
    assert info["iv_rank"] > 40.0
    assert ok is True
    assert info["reason"] == "gating_passed"


def test_gate_boundaries_at_30_and_40() -> None:
    """Hand-computed boundary ranks drive iv_pass at exactly the 30/40 lines.

    SELL case: 28 flat closes (|ret| = 0 exactly), then +2%, -1% ->
    |ret| = [0 x28, 2.0, 1.0]; current 1.0, min 0, max 2.0 -> rank 50.0
    (> 40 -> SELL iv_pass True at the pinned `iv_rank > 40` line).
    BUY case: flat closes, +2%, flat -> current |ret| = 0 = min ->
    rank 0.0 (< 30 -> BUY iv_pass True at the pinned `iv_rank < 30` line).
    """
    eng = _gating_engine(vix=20.0)

    sell_closes = [100.0] * 28 + [102.0, 100.98]  # +2% then exactly -1%
    _ok, info = eng.apply_gating_rules(_sell_signal(), _bars(sell_closes), 100.0)
    assert info["iv_rank"] == pytest.approx(50.0)
    assert info["iv_pass"] is True

    eng.set_vix_level(10.0)
    buy_closes = [100.0] * 28 + [102.0, 102.0]  # +2% then exactly flat
    _ok_b, info_b = eng.apply_gating_rules(_buy_signal(), _bars(buy_closes), 100.0)
    assert info_b["iv_rank"] == 0.0
    assert info_b["iv_pass"] is True


# --------------------------------------------------------------------------
# (6) Rank source provenance: chain IV wins, HV fallback is labelled
# --------------------------------------------------------------------------
def test_iv_source_flag_reports_hv_fallback() -> None:
    eng = _gating_engine(vix=10.0)
    hist = _grind_then_quiet()
    _ok, info = eng.apply_gating_rules(_buy_signal(), hist, 100.0)
    assert info["iv_source"] == "hv_percentile"


def test_chain_iv_history_takes_precedence_over_hv() -> None:
    """Persisted chain ATM IV at window min -> rank 0 regardless of HV."""
    eng = CMPRulesEngine()
    eng.set_chain_iv_history(12.0, as_of_date="2026-01-01")
    eng.set_chain_iv_history(18.0, as_of_date="2026-01-02")
    eng.set_chain_iv_history(15.0, as_of_date="2026-01-03")
    hist = _grind_then_quiet()
    eng.set_chain_iv_history(12.0, as_of_date="2026-01-04")  # current == min
    assert eng.calculate_iv_rank(hist) == 0.0
    eng.set_chain_iv_history(18.0, as_of_date="2026-01-05")  # current == max
    assert eng.calculate_iv_rank(hist) == 100.0


def test_chain_iv_series_mid_range_hand_computed() -> None:
    """Chain-IV rank vs hand computation mid-range: [12,18] current 15 -> 50."""
    eng = CMPRulesEngine()
    eng.set_chain_iv_history(12.0, as_of_date="2026-01-01")
    eng.set_chain_iv_history(18.0, as_of_date="2026-01-02")
    hist = _grind_then_quiet()
    eng.set_chain_iv_history(15.0, as_of_date="2026-01-03")  # current == mid
    assert eng.calculate_iv_rank(hist) == pytest.approx(50.0)


def test_chain_iv_history_window_is_bounded() -> None:
    eng = CMPRulesEngine()
    for i in range(400):
        eng.set_chain_iv_history(
            float(i), as_of_date=f"2026-{(i // 28) + 1:02d}-{(i % 28) + 1:02d}"
        )
    assert len(eng._chain_iv_history) == 252
    values = list(eng._chain_iv_history.values())
    assert values[-1] == pytest.approx(399.0)  # newest kept, oldest evicted


def test_non_finite_iv_rejected_at_every_boundary() -> None:
    """inf/NaN IVs are rejected live, persisted-side, AND on warm-start.

    Adversarial-probe regression: an inf persisted then warm-started
    unvalidated pins rank to a permanent degenerate 0.0 that PASSES the
    BUY gate -- exactly the degenerate-gate class F9-C-01 targets.
    """
    eng = CMPRulesEngine()
    eng.set_chain_iv_history(float("inf"))
    eng.set_chain_iv_history(float("nan"))
    eng.set_chain_iv_history(-5.0)
    assert eng._chain_iv_history == {}

    # Poisoned persistence: only the finite row survives the warm-start.
    eng.load_chain_iv_history([("2026-01-01", float("inf")), ("2026-01-02", 13.0)])
    assert list(eng._chain_iv_history.values()) == [13.0]


def test_dated_feed_upserts_by_day_not_observation() -> None:
    """One entry per as_of_date; undated feeds refresh the newest entry.

    In-memory series must mirror the (symbol, as_of_date) persistence:
    a 5-minute cycle must not evict a year of history in ~3.4 days.
    """
    eng = CMPRulesEngine()
    for i in range(75):  # one trading day of 5-min cycles
        eng.set_chain_iv_history(12.0 + i / 100.0, as_of_date="2026-09-15")
    assert list(eng._chain_iv_history.values()) == [pytest.approx(12.74)]

    eng.set_chain_iv_history(13.0, as_of_date="2026-09-16")
    eng.set_chain_iv_history(14.0, as_of_date="2026-09-17")
    assert list(eng._chain_iv_history.values()) == [
        pytest.approx(12.74),
        13.0,
        14.0,
    ]

    eng.set_chain_iv_history(14.5)  # undated -> refreshes newest, no append
    assert list(eng._chain_iv_history.values()) == [
        pytest.approx(12.74),
        13.0,
        14.5,
    ]


def test_replay_no_single_value_dominates() -> None:
    """FR9 recommended test (2): replay sliding windows over stored bars.

    Fewer than 90% of replayed cycles may land on any single value --
    the legacy saturated code pinned 100% at 100.0.
    """
    from collections import Counter

    eng = CMPRulesEngine()
    data = _regime(0.01, 5, n=40)
    ranks = [eng.calculate_iv_rank(data[:start], window=30) for start in range(30, 41)]
    assert len(ranks) == 11
    most_common_count = Counter(ranks).most_common(1)[0][1]
    assert most_common_count < 0.9 * len(ranks), f"degenerate replay: {ranks}"


def test_exact_gate_boundary_30_and_40_consistent() -> None:
    """Gate outcome at the 30/40 boundaries follows the computed float rank.

    Ranks are constructed to land exactly on the boundaries; the pass/
    fail outcome must equal (rank < 30) / (rank > 40) for the computed
    value -- no hidden epsilon in the pinned comparison lines.
    """
    eng = CMPRulesEngine()
    eng.set_vix_level(10.0)
    eng.is_trading_allowed = lambda: True  # type: ignore[method-assign]
    # Chain-IV series [10, 20] current 13 -> rank (13-10)/(20-10)*100 = 30.
    eng.set_chain_iv_history(10.0, as_of_date="2026-01-01")
    eng.set_chain_iv_history(20.0, as_of_date="2026-01-02")
    eng.set_chain_iv_history(13.0, as_of_date="2026-01-03")
    hist = _grind_then_quiet()
    ok_b, info_b = eng.apply_gating_rules(_buy_signal(), hist, 100.0)
    assert info_b["iv_rank"] == pytest.approx(30.0)
    assert ok_b is (info_b["iv_rank"] < 30)

    # [10, 20] current 14 -> rank 40 -> SELL gate (rank > 40) is False.
    eng.set_vix_level(20.0)
    eng.set_chain_iv_history(14.0, as_of_date="2026-01-04")
    ok_s, info_s = eng.apply_gating_rules(_sell_signal(), hist, 100.0)
    assert info_s["iv_rank"] == pytest.approx(40.0)
    assert ok_s is (info_s["iv_rank"] > 40)


# --------------------------------------------------------------------------
# (7) Decision pipeline: insufficient history is audited (F9-M-04 merge)
# --------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_insufficient_history_audited_in_decision_pipeline() -> None:
    """29-bar history -> gating fails loud + an audit row is persisted."""
    from loats.trade_decision import TradeDecisionEngine

    now = datetime.now(UTC)
    hist29 = [
        HistoricalData(
            symbol="NIFTY",
            timestamp=now - timedelta(minutes=5 * (29 - i)),
            open=24500.0 + i * 10,
            high=24550.0 + i * 10,
            low=24470.0 + i * 10,
            close=24510.0 + i * 10,
            volume=1000000 + i * 10000,
            interval="5min",
        )
        for i in range(29)
    ]

    engine = TradeDecisionEngine()
    audited: list[dict[str, Any]] = []

    async def _spy_log_audit(**kwargs: Any) -> bool:
        audited.append(kwargs)
        return True

    with patch("loats.trade_decision.db") as mdb:
        mdb.async_log_audit = AsyncMock(side_effect=_spy_log_audit)
        # _audit_rejection skips writes when settings.environment == "test"
        # (hermeticity guard); pin production behavior for this audit test.
        with (
            patch("loats.trade_decision.settings") as msettings,
            patch("loats.trade_decision.rules_engine") as mr,
        ):
            msettings.environment = "production"
            msettings.composite_strength_threshold = 0.5
            msettings.default_symbol = "NIFTY"
            # REAL rules engine computes the gate; only identity mocked
            # away. Pin the session gate ON so the test never depends on
            # the wall-clock IST bucket (POST_CLOSE would otherwise
            # short-circuit with trading_not_allowed before history).
            real_engine = CMPRulesEngine()
            real_engine.is_trading_allowed = lambda: True  # type: ignore[method-assign]
            mr.apply_gating_rules = real_engine.apply_gating_rules
            decision, result = await engine.create_trade_decision(
                signals=_sigs(4),
                historical_data=hist29,
                current_price=24500.0,
                funds=_funds(),
                current_positions=[],
            )
    assert decision is None
    assert result["reason"] == "gating_rules_failed"
    assert result["gating_result"]["reason"] == "insufficient_history"
    assert any(
        (meta := r.get("metadata") or {}).get("step") == "gating_rules"
        and meta.get("reason") == "gating_rules_failed"
        and (meta.get("details") or {}).get("reason") == "insufficient_history"
        for r in audited
    ), f"no gating audit row persisted: {audited}"


# --------------------------------------------------------------------------
# (8) Producer integration: real chain -> ATM IV persist + engine feed
# --------------------------------------------------------------------------
class TestOptionsFlowIVIntegration:
    """Drives the REAL _execute_options_flow_analysis against a fixture
    chain, mocking only the _safe_get_option_chain boundary (same
    isolation contract as TestOptionsFlowSignalProducer).
    """

    @staticmethod
    def _row(
        opt_type: str,
        volume: float,
        iv: float | None,
        strike: int = 24500,
        expiry: str = "2026-09-30T00:00:00",
        spot: float | None = 24502.0,
    ) -> dict[str, Any]:
        row: dict[str, Any] = {
            "symbol": f"NIFTY{strike}{opt_type}",
            "strike_price": strike,
            "expiry": expiry,
            "option_type": opt_type,
            "volume": volume,
        }
        if iv is not None:
            row["implied_volatility"] = iv
        if spot is not None:
            row["underlying_price"] = spot
        return row

    @staticmethod
    def _chain(*rows: dict[str, Any]) -> dict[str, Any]:
        return {"status": "success", "data": {"options": list(rows)}}

    async def _run(self, chain_payload: dict[str, Any] | None) -> tuple[Database, Any]:
        import tempfile
        from pathlib import Path

        from loats.orchestrator import TradingOrchestrator

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
            db = Database(
                db_path=Path(td) / "o.db", audit_log_path=Path(td) / "a.jsonl"
            )
            db._initialize_database()
            orch = TradingOrchestrator()
            with (
                patch("loats.orchestrator.db", db),
                patch.object(
                    orch,
                    "_safe_get_option_chain",
                    new_callable=AsyncMock,
                    return_value=chain_payload,
                ),
            ):
                await orch._execute_options_flow_analysis()
            return db, orch

    @pytest.mark.asyncio
    async def test_atm_iv_persisted_and_engine_fed(self):
        """Atm IV lands in iv_history keyed by the payload's expiry date."""
        payload = self._chain(
            self._row("CE", 1000.0, 0.12, strike=24500),
            self._row("PE", 1200.0, 0.13, strike=24500),
            self._row("CE", 800.0, 0.14, strike=24600),
            self._row("PE", 900.0, 0.15, strike=24600),
        )
        db, _orch = await self._run(payload)
        try:
            series = await db.async_get_chain_iv_series("NIFTY")
            assert len(series) == 1, f"expected one upserted row, got {series}"
            date_str, iv = series[0]
            assert date_str == "2026-09-30"
            # ATM pair (distance 0.0000816 vs 0.004) -> min-distance IV mean-ish
            assert 11.0 < iv < 14.0, f"ATM IV should be ~12-13, got {iv}"
        finally:
            db.close_all()

    @pytest.mark.asyncio
    async def test_no_spot_or_expiry_persists_nothing_but_feeds_engine(self):
        """Missing spot AND expiries: honest degradation, no fabricated date."""
        rows = [
            {
                "symbol": "NIFTY24500CE",
                "strike_price": 24500,
                "option_type": "CE",
                "volume": 1000,
                "implied_volatility": 0.12,
            },
            {
                "symbol": "NIFTY24500PE",
                "strike_price": 24500,
                "option_type": "PE",
                "volume": 1200,
                "implied_volatility": 0.13,
            },
        ]
        db, _orch = await self._run(self._chain(*rows))
        try:
            assert await db.async_get_chain_iv_series("NIFTY") == []
        finally:
            db.close_all()

    @pytest.mark.asyncio
    async def test_fraction_iv_normalized_to_percent_scale(self):
        """0.13 stored as 13.0 so mixed-unit series cannot fold rank."""
        eng = CMPRulesEngine()
        eng.set_chain_iv_history(0.13)
        assert list(eng._chain_iv_history.values())[-1] == pytest.approx(13.0)


class TestIVWarmStart:
    """initialize() warm-starts the rank series from persisted iv_history."""

    @pytest.mark.asyncio
    async def test_initialize_loads_persisted_series(self):
        from loats.orchestrator import TradingOrchestrator
        from loats.rules import rules_engine

        saved = dict(rules_engine._chain_iv_history)
        rules_engine._chain_iv_history.clear()
        try:
            orch = TradingOrchestrator()
            mdb = MagicMock()
            # Real db.async_get_chain_iv_series returns (as_of_date, iv)
            # tuples; the mock must honor that contract (a bare float
            # list crashed load_chain_iv_history's pair unpacking).
            mdb.async_get_chain_iv_series = AsyncMock(
                return_value=[("2026-09-01", 12.0), ("2026-09-02", 18.0)]
            )
            with (
                patch("loats.orchestrator.db", mdb),
                patch("loats.orchestrator.settings") as msettings,
            ):
                msettings.default_symbol = "NIFTY"
                await orch.initialize()
            assert list(rules_engine._chain_iv_history.values()) == [12.0, 18.0]
            # Rank computed from the loaded series: current==max -> 100.
            short = _bars([100.0 + (0.2 if i % 2 == 0 else -0.1) for i in range(40)])
            assert rules_engine.calculate_iv_rank(short) == pytest.approx(100.0)
        finally:
            rules_engine.load_chain_iv_history(list(saved.items()))

    @pytest.mark.asyncio
    async def test_initialize_survives_store_failure(self):
        """A failed warm-start degrades to the HV fallback, never crashes."""
        from loats.orchestrator import TradingOrchestrator
        from loats.rules import rules_engine

        saved = dict(rules_engine._chain_iv_history)
        rules_engine._chain_iv_history.clear()
        try:
            orch = TradingOrchestrator()
            mdb = MagicMock()
            mdb.async_get_chain_iv_series = AsyncMock(
                side_effect=RuntimeError("store down")
            )
            with (
                patch("loats.orchestrator.db", mdb),
                patch("loats.orchestrator.settings") as msettings,
            ):
                msettings.default_symbol = "NIFTY"
                await orch.initialize()
            assert list(rules_engine._chain_iv_history.values()) == []
        finally:
            rules_engine.load_chain_iv_history(list(saved.items()))


# --------------------------------------------------------------------------
# (9) Adversarial round hardening (18Sep2026 F9-C-01 re-verification wave)
# --------------------------------------------------------------------------
class TestInsufficientHistoryPayloadIsRFCJson:
    """The loud insufficiency sentinel must never leak -Infinity into JSON.

    The gating payload flows into db.async_log_audit (dual-write JSONL +
    SHA-256 chain), TradeDecision.gating_rules_result (SQLite TEXT via
    json.dumps) and TradeDecision.to_dict(). A raw float("-inf") there
    serializes to the non-RFC-8259 token ``-Infinity`` (proven live), so
    downstream JSON parsers may reject rows that carry a mandatory CMP
    audit event. The calculator keeps its loud float("-inf") sentinel
    (pinned above); the decision-facing payload is sanitized at the
    boundary to None (JSON null).
    """

    def test_calculator_sentinel_unchanged(self) -> None:
        eng = CMPRulesEngine()
        short = _bars([100.0 + (0.2 if i % 2 == 0 else -0.1) for i in range(29)])
        assert eng.calculate_iv_rank(short) == float("-inf")

    def test_insufficient_history_payload_carries_null_not_infinity(self) -> None:
        eng = _gating_engine(vix=10.0)
        short = _bars([100.0 + (0.2 if i % 2 == 0 else -0.1) for i in range(29)])
        _, info_b = eng.apply_gating_rules(_buy_signal(), short, 100.0)
        assert info_b["reason"] == "insufficient_history"
        assert info_b["iv_rank"] is None
        assert "Infinity" not in json.dumps(info_b)

        eng.set_vix_level(20.0)
        _, info_s = eng.apply_gating_rules(_sell_signal(), short, 100.0)
        assert info_s["iv_rank"] is None
        assert "Infinity" not in json.dumps(info_s)


class TestIVRankUsesNewestDayNotFeedOrder:
    """Rank reads the NEWEST as_of_date key, not insertion order.

    set_chain_iv_history is an upsert-by-day; the day-keyed dict only
    preserves insertion order when feeds arrive chronologically (which
    the live producer and the warm-start both guarantee today, but the
    day-key contract must not silently depend on feed order).
    """

    def test_out_of_order_feed_ranks_newest_day(self) -> None:
        eng = CMPRulesEngine()
        # Fed so the NEWEST day lands in the middle of the dict.
        eng.set_chain_iv_history(10.0, as_of_date="2026-01-01")
        eng.set_chain_iv_history(14.0, as_of_date="2026-01-03")  # newest day
        eng.set_chain_iv_history(12.0, as_of_date="2026-01-02")
        # Honest newest-day rank: (14 - 10) / (14 - 10) * 100 = 100.0
        assert eng.calculate_iv_rank([]) == pytest.approx(100.0)

    def test_oldest_day_last_ranks_newest_day(self) -> None:
        eng = CMPRulesEngine()
        eng.set_chain_iv_history(14.0, as_of_date="2026-01-03")  # newest day
        eng.set_chain_iv_history(10.0, as_of_date="2026-01-01")
        eng.set_chain_iv_history(12.0, as_of_date="2026-01-02")
        assert eng.calculate_iv_rank([]) == pytest.approx(100.0)

    def test_newest_day_is_min_ranks_zero(self) -> None:
        eng = CMPRulesEngine()
        eng.set_chain_iv_history(10.0, as_of_date="2026-01-01")
        eng.set_chain_iv_history(18.0, as_of_date="2026-01-02")
        eng.set_chain_iv_history(10.0, as_of_date="2026-01-03")  # newest == min
        assert eng.calculate_iv_rank([]) == pytest.approx(0.0)

    def test_undated_refresh_keeps_newest_day_semantics(self) -> None:
        """Undated refresh targets the NEWEST DAY, rank reads that day.

        The newest day (01-03) is inserted FIRST so both the refresh
        target and the rank's current-selection are order-sensitive:
        day-key semantics give (16-10)/(20-10)*100 = 60.0, while
        insertion-order code would refresh/rank the last-inserted
        01-02 entry and report 100.0/60.0 (RED proven).
        """
        eng = CMPRulesEngine()
        eng.set_chain_iv_history(14.0, as_of_date="2026-01-03")  # newest day
        eng.set_chain_iv_history(10.0, as_of_date="2026-01-01")
        eng.set_chain_iv_history(20.0, as_of_date="2026-01-02")  # last inserted
        eng.set_chain_iv_history(16.0)  # undated -> refreshes newest DAY (01-03)
        assert eng.calculate_iv_rank([]) == pytest.approx(60.0)
