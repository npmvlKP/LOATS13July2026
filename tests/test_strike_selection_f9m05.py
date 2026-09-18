#!/usr/bin/env python3
"""F9-M-05 (TODO-15) conformance net: CMP S4 strike selection.

Pins the three remediation surfaces:
1. BUY-side true closed delta band |delta| in [0.50, 0.60] (the old
   heuristic `abs(delta - 0.5) < 0.1` was an open band that even
   rejected delta == 0.60 exactly).
2. SELL-side two-sigma band from unit-consistent history sigma
   (per-bar sigma of simple returns scaled by sqrt(bars-in-horizon);
   fail-closed on insufficient or unit-ambiguous history).
3. OI confirmation filter, fail-closed when OI is zero.

Also pins the duplicated-strike root-cause fix: the ATM call and put
at the SAME strike previously produced [K, K]; selections are now
deduplicated.
"""

import math
import unittest
from datetime import UTC, datetime

from loats import strike_selection as ss
from loats.models import HistoricalData, OptionContract, OptionType


def mk_bar(close: float, interval: str = "1min", idx: int = 0) -> HistoricalData:
    """Build one historical bar with open/high/low pinned to close."""
    return HistoricalData(
        symbol="NIFTY",
        timestamp=datetime(2026, 9, 18, 9, idx, tzinfo=UTC),
        open=close,
        high=close,
        low=close,
        close=close,
        volume=1000,
        interval=interval,
    )


def mk_contract(
    strike: float,
    option_type: OptionType,
    delta: float | None,
    oi: int = 1000,
) -> OptionContract:
    """Build one option contract with the fields F9-M-05 cares about."""
    return OptionContract(
        symbol=f"TEST{strike:g}{'CE' if option_type == OptionType.CALL else 'PE'}",
        strike_price=strike,
        expiry=datetime(2026, 9, 24, tzinfo=UTC),
        option_type=option_type,
        last_price=5.0,
        open_interest=oi,
        volume=500,
        implied_volatility=0.25,
        delta=delta,
        gamma=0.01,
        theta=-0.05,
        vega=0.1,
        rho=0.05,
        quantity=1,
    )


class TestF9M05DeltaBand(unittest.IsolatedAsyncioTestCase):
    """BUY-side closed band [0.50, 0.60] inclusive (FR9 boundary spec)."""

    def test_band_constants_pin_spec(self):
        """The spec values are pinned: a silent band change trips here."""
        self.assertEqual(ss.DELTA_BAND_LOW, 0.50)
        self.assertEqual(ss.DELTA_BAND_HIGH, 0.60)
        self.assertEqual(ss.STD_DEVIATION_MULTIPLE, 2.0)

    def test_band_boundary_049_050_060_061(self):
        """FR9 spec boundaries: 0.49 out, 0.50 in, 0.60 in, 0.61 out."""
        self.assertFalse(ss.delta_in_buy_band(0.49))
        self.assertTrue(ss.delta_in_buy_band(0.50))
        self.assertTrue(ss.delta_in_buy_band(0.55))
        self.assertTrue(ss.delta_in_buy_band(0.60))
        self.assertFalse(ss.delta_in_buy_band(0.61))

    def test_band_none_delta_fail_closed(self):
        """A contract without a delta is never band-eligible."""
        self.assertFalse(ss.delta_in_buy_band(None))

    def test_band_symmetric_for_put_magnitudes(self):
        """Put deltas are negative; the band applies to |delta|."""
        self.assertTrue(ss.delta_in_buy_band(-0.50))
        self.assertTrue(ss.delta_in_buy_band(-0.60))
        self.assertFalse(ss.delta_in_buy_band(-0.49))
        self.assertFalse(ss.delta_in_buy_band(-0.61))

    async def test_boundary_delta_060_selected(self):
        """delta == 0.60 contracts are eligible (old heuristic rejected them)."""
        chain = [
            mk_contract(100.0, OptionType.CALL, 0.50),
            mk_contract(105.0, OptionType.CALL, 0.60),
        ]
        engine = ss.StrikeSelectionEngine()
        selected = await engine._select_delta_neutral_strikes(100.0, chain, 1, 5)
        self.assertIn(100.0, selected)
        self.assertIn(105.0, selected)

    async def test_out_of_band_strikes_excluded(self):
        """Strikes whose only eligible-side contract is out of band drop out."""
        chain = [
            mk_contract(95.0, OptionType.CALL, 0.49),
            mk_contract(100.0, OptionType.CALL, 0.55),
            mk_contract(105.0, OptionType.CALL, 0.61),
        ]
        engine = ss.StrikeSelectionEngine()
        selected = await engine._select_delta_neutral_strikes(100.0, chain, 1, 5)
        self.assertEqual(selected, [100.0])

    async def test_oi_confirmation_zero_fail_closed(self):
        """In-band contract with zero OI is excluded (fail-closed)."""
        chain = [
            mk_contract(100.0, OptionType.CALL, 0.50, oi=1000),
            mk_contract(105.0, OptionType.CALL, 0.55, oi=0),
        ]
        engine = ss.StrikeSelectionEngine()
        selected = await engine._select_delta_neutral_strikes(100.0, chain, 1, 5)
        self.assertEqual(selected, [100.0])

    async def test_no_eligible_strikes_fail_closed_empty(self):
        """When every contract is out of band the selection is empty."""
        chain = [
            mk_contract(95.0, OptionType.CALL, 0.30),
            mk_contract(100.0, OptionType.CALL, 0.49),
            mk_contract(105.0, OptionType.PUT, -0.61),
        ]
        engine = ss.StrikeSelectionEngine()
        selected = await engine._select_delta_neutral_strikes(100.0, chain, 1, 5)
        self.assertEqual(selected, [])

    async def test_delta_neutral_empty_chain_returns_empty(self):
        """An empty chain yields an empty selection (guard pinned)."""
        engine = ss.StrikeSelectionEngine()
        self.assertEqual(
            await engine._select_delta_neutral_strikes(100.0, [], 1, 5), []
        )

    async def test_max_strikes_cap_respected(self):
        """Selection never exceeds max_strikes even with many eligible strikes."""
        chain = [
            mk_contract(95.0, OptionType.CALL, 0.52),
            mk_contract(100.0, OptionType.CALL, 0.50),
            mk_contract(105.0, OptionType.CALL, 0.58),
            mk_contract(110.0, OptionType.CALL, 0.60),
        ]
        engine = ss.StrikeSelectionEngine()
        selected = await engine._select_delta_neutral_strikes(100.0, chain, 1, 2)
        self.assertEqual(len(selected), 2)


class TestF9M05DedupRootCause(unittest.IsolatedAsyncioTestCase):
    """Root-cause pin: the ATM call+put pair at one strike duplicated K."""

    async def test_atm_pair_yields_single_strike(self):
        """100CE (0.50) + 100PE (-0.50) -> [100.0] once, not [100.0, 100.0]."""
        chain = [
            mk_contract(100.0, OptionType.CALL, 0.50),
            mk_contract(100.0, OptionType.PUT, -0.50),
        ]
        engine = ss.StrikeSelectionEngine()
        selected = await engine._select_delta_neutral_strikes(100.0, chain, 1, 2)
        self.assertEqual(selected, [100.0])
        self.assertEqual(selected.count(100.0), 1)

    async def test_distinct_strike_legs_both_kept(self):
        """Eligible call and put at DIFFERENT strikes both survive dedup."""
        chain = [
            mk_contract(100.0, OptionType.CALL, 0.50),
            mk_contract(105.0, OptionType.PUT, -0.55),
        ]
        engine = ss.StrikeSelectionEngine()
        selected = await engine._select_delta_neutral_strikes(100.0, chain, 1, 5)
        self.assertEqual(selected, [100.0, 105.0])

    async def test_fr9_fixture_chain_conformance(self):
        """The pre-wave FR9 fixture chain now returns the deduped ATM pair."""
        chain = [
            mk_contract(95.0, OptionType.CALL, 0.65),
            mk_contract(100.0, OptionType.CALL, 0.50),
            mk_contract(105.0, OptionType.CALL, 0.35),
            mk_contract(95.0, OptionType.PUT, -0.35),
            mk_contract(100.0, OptionType.PUT, -0.50),
            mk_contract(105.0, OptionType.PUT, -0.65),
        ]
        engine = ss.StrikeSelectionEngine()
        selected = await engine._select_delta_neutral_strikes(100.0, chain, 1, 2)
        self.assertEqual(selected, [100.0])


class TestF9M05IntervalParsing(unittest.TestCase):
    """Unit-consistency plumbing: bar labels -> seconds, fail-closed."""

    def test_valid_minute_labels(self):
        self.assertEqual(ss._interval_seconds("1min"), 60.0)
        self.assertEqual(ss._interval_seconds("5min"), 300.0)
        self.assertEqual(ss._interval_seconds("60min"), 3600.0)

    def test_unparseable_labels_fail_closed(self):
        self.assertIsNone(ss._interval_seconds("daily"))
        self.assertIsNone(ss._interval_seconds(""))
        self.assertIsNone(ss._interval_seconds("min"))
        self.assertIsNone(ss._interval_seconds("1h"))

    def test_nonpositive_interval_fail_closed(self):
        self.assertIsNone(ss._interval_seconds("0min"))
        self.assertIsNone(ss._interval_seconds("-5min"))


class TestF9M05BarSigma(unittest.TestCase):
    """Per-bar sigma of simple returns with unit validation."""

    def test_hand_computed_sigma(self):
        """closes 100 -> 101 -> 99.99: returns +0.01, -0.01, sigma = 0.01*sqrt(2)."""
        bars = [
            mk_bar(100.0, "2min", 0),
            mk_bar(101.0, "2min", 2),
            mk_bar(99.99, "2min", 4),
        ]
        result = ss.estimate_bar_sigma(bars)
        self.assertIsNotNone(result)
        sigma, bar_seconds = result
        self.assertAlmostEqual(bar_seconds, 120.0)
        self.assertTrue(math.isclose(sigma, 0.01 * math.sqrt(2), rel_tol=1e-12))

    def test_insufficient_history_fail_closed(self):
        """Fewer than 2 returns cannot produce a sample stdev."""
        self.assertIsNone(ss.estimate_bar_sigma([]))
        self.assertIsNone(ss.estimate_bar_sigma([mk_bar(100.0)]))
        self.assertIsNone(
            ss.estimate_bar_sigma([mk_bar(100.0, idx=0), mk_bar(101.0, idx=1)])
        )

    def test_mixed_intervals_fail_closed(self):
        """Bars from two different intervals must never mix into one sigma."""
        bars = [
            mk_bar(100.0, "1min", 0),
            mk_bar(101.0, "1min", 1),
            mk_bar(99.99, "5min", 2),
        ]
        self.assertIsNone(ss.estimate_bar_sigma(bars))

    def test_unparseable_interval_fail_closed(self):
        bars = [
            mk_bar(100.0, "daily", 0),
            mk_bar(101.0, "daily", 1),
            mk_bar(99.99, "daily", 2),
        ]
        self.assertIsNone(ss.estimate_bar_sigma(bars))

    def test_zero_close_guard_fail_closed(self):
        """A zero previous close cannot divide; the guard returns None.

        The model pins close > 0, so this defense is only reachable for a
        validation-bypassed row (model_construct) -- pinned anyway so the
        guard can never be silently deleted.
        """
        good = mk_bar(100.0, "1min", 0)
        zero = mk_bar(101.0, "1min", 1)
        zero_close = HistoricalData.model_construct(
            symbol="NIFTY",
            timestamp=zero.timestamp,
            open=0.0,
            high=0.0,
            low=0.0,
            close=0.0,
            volume=0,
            interval="1min",
        )
        self.assertIsNone(
            ss.estimate_bar_sigma([good, zero_close, mk_bar(99.0, "1min", 2)])
        )


class TestF9M05TwoSigmaBand(unittest.TestCase):
    """SELL-side 2-sigma band: hand-computed and realistic-path pins."""

    def test_hand_computed_perfect_square_horizon(self):
        """sigma=0.02/bar, 16 bars/day, 4 days -> 64 bars -> 2*0.02*8*100 = 32."""
        band = ss.two_sigma_sell_band(100.0, 0.02, ss.TRADING_DAY_SECONDS / 16.0, 4.0)
        self.assertIsNotNone(band)
        lower, upper = band
        self.assertTrue(math.isclose(lower, 68.0, rel_tol=1e-12))
        self.assertTrue(math.isclose(upper, 132.0, rel_tol=1e-12))

    def test_realistic_60min_bars_one_day(self):
        """60-minute bars, 1 day: bars = TRADING_DAY_SECONDS/3600 = 1575."""
        band = ss.two_sigma_sell_band(100.0, 0.01, 3600.0, 1.0)
        self.assertIsNotNone(band)
        lower, upper = band
        expected_half_width = (
            100.0 * 2.0 * 0.01 * math.sqrt(ss.TRADING_DAY_SECONDS / 3600.0)
        )
        self.assertTrue(math.isclose(100.0 - lower, expected_half_width, rel_tol=1e-12))
        self.assertTrue(math.isclose(upper - 100.0, expected_half_width, rel_tol=1e-12))

    def test_guards_fail_closed(self):
        """None sigma/seconds, non-positive price or horizon -> None."""
        self.assertIsNone(ss.two_sigma_sell_band(100.0, None, 3600.0, 1.0))
        self.assertIsNone(ss.two_sigma_sell_band(100.0, 0.01, None, 1.0))
        self.assertIsNone(ss.two_sigma_sell_band(0.0, 0.01, 3600.0, 1.0))
        self.assertIsNone(ss.two_sigma_sell_band(-100.0, 0.01, 3600.0, 1.0))
        self.assertIsNone(ss.two_sigma_sell_band(100.0, 0.01, 3600.0, 0.0))
        self.assertIsNone(ss.two_sigma_sell_band(100.0, 0.01, 0.0, 1.0))

    def test_band_is_symmetric_around_underlying(self):
        band = ss.two_sigma_sell_band(25000.0, 0.015, 300.0, 2.0)
        self.assertIsNotNone(band)
        lower, upper = band
        self.assertTrue(math.isclose(lower + upper, 2.0 * 25000.0, rel_tol=1e-12))


class TestF9M05EngineBand(unittest.IsolatedAsyncioTestCase):
    """Engine-level band construction end to end."""

    async def test_engine_band_end_to_end(self):
        """2-min bars hand series -> engine band matches the pure function."""
        bars = [
            mk_bar(100.0, "2min", 0),
            mk_bar(101.0, "2min", 2),
            mk_bar(99.99, "2min", 4),
        ]
        engine = ss.StrikeSelectionEngine()
        band = await engine.build_sell_two_sigma_band(100.0, bars, holding_days=1.0)
        self.assertIsNotNone(band)
        sigma = 0.01 * math.sqrt(2)
        bars_in_horizon = ss.TRADING_DAY_SECONDS / 120.0
        expected = 100.0 * 2.0 * sigma * math.sqrt(bars_in_horizon)
        self.assertTrue(math.isclose(band[0], 100.0 - expected, rel_tol=1e-12))
        self.assertTrue(math.isclose(band[1], 100.0 + expected, rel_tol=1e-12))

    async def test_engine_band_fail_closed_short_history(self):
        """Two bars = one return = no sample stdev -> None, not a made-up band."""
        engine = ss.StrikeSelectionEngine()
        bars = [mk_bar(100.0, "1min", 0), mk_bar(101.0, "1min", 1)]
        self.assertIsNone(await engine.build_sell_two_sigma_band(100.0, bars))

    async def test_engine_band_fail_closed_ambiguous_units(self):
        """Mixed-interval history must never produce a band."""
        engine = ss.StrikeSelectionEngine()
        bars = [
            mk_bar(100.0, "1min", 0),
            mk_bar(101.0, "1min", 1),
            mk_bar(99.99, "5min", 2),
        ]
        self.assertIsNone(await engine.build_sell_two_sigma_band(100.0, bars))


if __name__ == "__main__":
    unittest.main(verbosity=2)
