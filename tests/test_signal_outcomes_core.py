"""Outcome grading core (30Sep evidence wave).

Pure, deterministic, clock-free -- mirrors the F9-H-05 property net's
discipline: fuzz invariants plus hand-computed arithmetic cases, no
network, no sleeps.
"""

from __future__ import annotations

import datetime
import random
import re
from typing import Any

import pytest

from loats.models import HistoricalData, SignalType
from loats.signal_outcomes import (
    MAX_OUTCOME_HORIZON_MINUTES,
    MIN_OUTCOME_HORIZON_MINUTES,
    TERMINAL_OUTCOME_STATES,
    SignalOutcomeState,
    evaluate_signal_outcome,
    parse_signal_type,
    validate_signal_outcome_horizon,
)

UTC = datetime.UTC


def _bar(
    minutes_offset: int,
    *,
    base: float = 100.0,
    timestamp: datetime.datetime | None = None,
) -> HistoricalData:
    """Deterministic synthetic 1d bar at ``minutes_offset`` from base."""
    start = timestamp or datetime.datetime(2026, 9, 23, 10, 0, tzinfo=UTC)
    ts = start + datetime.timedelta(minutes=minutes_offset)
    return HistoricalData(
        symbol="NIFTY",
        timestamp=ts,
        open=base,
        high=base + 2.0,
        low=base - 1.0,
        close=base + 1.0,
        volume=1000,
        interval="1d",
    )


class TestParseSignalType:
    def test_valid_values_round_trip(self) -> None:
        assert parse_signal_type("BUY") is SignalType.BUY
        assert parse_signal_type("SELL") is SignalType.SELL
        assert parse_signal_type("HOLD") is SignalType.HOLD
        assert parse_signal_type("NEUTRAL") is SignalType.NEUTRAL

    def test_invalid_value_fails_closed_to_none(self) -> None:
        assert parse_signal_type("not-a-type") is None
        assert parse_signal_type("") is None
        assert parse_signal_type("buy") is None  # case-sensitive enum

    @pytest.mark.parametrize("value", ["corrupt", "BUY ", "sell", "0", "None"])
    def test_fuzz_garbage_never_raises(self, value: str) -> None:
        assert parse_signal_type(value) is None


class TestEvaluateSignalOutcome:
    def test_buy_up_bars_positive_hand_computed(self) -> None:
        timestamp = datetime.datetime(2026, 9, 23, 10, 0, tzinfo=UTC)
        bars = [
            HistoricalData(
                symbol="NIFTY",
                timestamp=timestamp,
                open=100.0,
                high=106.0,
                low=99.0,
                close=104.0,
                volume=10,
                interval="1d",
            ),
            HistoricalData(
                symbol="NIFTY",
                timestamp=timestamp + datetime.timedelta(minutes=30),
                open=104.0,
                high=108.0,
                low=103.0,
                close=107.0,
                volume=10,
                interval="1d",
            ),
        ]
        state, meta = evaluate_signal_outcome(
            signal_id="s1",
            signal_type="BUY",
            timestamp=timestamp,
            bars=bars,
            horizon_minutes=60,
            strength=0.8,
            confidence=0.7,
        )
        assert state is SignalOutcomeState.POSITIVE
        assert meta is not None
        assert meta["entry_price"] == pytest.approx(100.0)
        assert meta["exit_price"] == pytest.approx(107.0)
        assert meta["favorable_excursion"] == pytest.approx(108.0)
        assert meta["adverse_excursion"] == pytest.approx(99.0)
        assert meta["bars"] == 2

    def test_buy_down_bars_negative(self) -> None:
        timestamp = datetime.datetime(2026, 9, 23, 10, 0, tzinfo=UTC)
        bars = [_bar(0, base=100.0), _bar(30, base=95.0)]
        state, _ = evaluate_signal_outcome(
            signal_id="s2",
            signal_type="BUY",
            timestamp=timestamp,
            bars=bars,
            horizon_minutes=60,
        )
        assert state is SignalOutcomeState.NEGATIVE

    def test_sell_down_bars_positive_direction_inverted(self) -> None:
        timestamp = datetime.datetime(2026, 9, 23, 10, 0, tzinfo=UTC)
        bars = [_bar(0, base=100.0), _bar(30, base=95.0)]
        state, _ = evaluate_signal_outcome(
            signal_id="s3",
            signal_type="SELL",
            timestamp=timestamp,
            bars=bars,
            horizon_minutes=60,
        )
        assert state is SignalOutcomeState.POSITIVE

    def test_sell_up_bars_negative(self) -> None:
        timestamp = datetime.datetime(2026, 9, 23, 10, 0, tzinfo=UTC)
        bars = [_bar(0, base=100.0), _bar(30, base=105.0)]
        state, _ = evaluate_signal_outcome(
            signal_id="s4",
            signal_type="SELL",
            timestamp=timestamp,
            bars=bars,
            horizon_minutes=60,
        )
        assert state is SignalOutcomeState.NEGATIVE

    def test_flat_window_is_negative_not_positive(self) -> None:
        timestamp = datetime.datetime(2026, 9, 23, 10, 0, tzinfo=UTC)
        flat = [
            HistoricalData(
                symbol="NIFTY",
                timestamp=timestamp + datetime.timedelta(minutes=m),
                open=100.0,
                high=100.0,
                low=100.0,
                close=100.0,
                volume=10,
                interval="1d",
            )
            for m in (0, 30)
        ]
        state, _ = evaluate_signal_outcome(
            signal_id="s5",
            signal_type="BUY",
            timestamp=timestamp,
            bars=flat,
            horizon_minutes=60,
        )
        assert state is SignalOutcomeState.NEGATIVE

    @pytest.mark.parametrize("signal_type", ["HOLD", "NEUTRAL"])
    def test_non_directional_carries_no_metadata(self, signal_type: str) -> None:
        timestamp = datetime.datetime(2026, 9, 23, 10, 0, tzinfo=UTC)
        state, meta = evaluate_signal_outcome(
            signal_id="s6",
            signal_type=signal_type,
            timestamp=timestamp,
            bars=[_bar(0)],
            horizon_minutes=60,
        )
        assert state is SignalOutcomeState.NON_DIRECTIONAL
        assert meta is None

    def test_empty_bars_stays_open_honest_hole(self) -> None:
        timestamp = datetime.datetime(2026, 9, 23, 10, 0, tzinfo=UTC)
        state, meta = evaluate_signal_outcome(
            signal_id="s7",
            signal_type="BUY",
            timestamp=timestamp,
            bars=[],
            horizon_minutes=60,
        )
        assert state is SignalOutcomeState.OPEN
        assert meta is None

    def test_invalid_signal_type_unresolvable(self) -> None:
        timestamp = datetime.datetime(2026, 9, 23, 10, 0, tzinfo=UTC)
        state, meta = evaluate_signal_outcome(
            signal_id="s8",
            signal_type="CORRUPT",
            timestamp=timestamp,
            bars=[_bar(0)],
            horizon_minutes=60,
        )
        assert state is SignalOutcomeState.UNRESOLVABLE
        assert meta is not None and "reason" in meta


class TestOutcomeFuzzInvariants:
    def test_fuzz_arithmetic_invariants(self) -> None:
        """1000 random windows: verdict matches direction*sign; excursion
        envelope brackets entry and exit; deterministic replay agrees."""
        rng = random.Random(20260923)
        timestamp = datetime.datetime(2026, 9, 23, 10, 0, tzinfo=UTC)
        for _ in range(1000):
            base = rng.uniform(100.0, 5000.0)
            drift = rng.uniform(-0.9 * base, 0.9 * base)
            n = rng.randint(1, 10)
            start_o = base + rng.uniform(-1.0, 1.0)
            end_c = base + drift
            bars = []
            for i in range(n):
                frac = i / max(n - 1, 1)
                open_ = start_o + (end_c - start_o) * frac
                close_ = start_o + (end_c - start_o) * min(frac + 1 / n, 1.0)
                bars.append(
                    HistoricalData(
                        symbol="NIFTY",
                        timestamp=timestamp + datetime.timedelta(minutes=30 * i),
                        open=open_,
                        high=max(open_, close_) + 2.0,
                        low=min(open_, close_) - 1.0,
                        close=close_,
                        volume=100,
                        interval="1d",
                    )
                )
            signal_type = rng.choice(["BUY", "SELL"])
            state, meta = evaluate_signal_outcome(
                signal_id="fuzz",
                signal_type=signal_type,
                timestamp=timestamp,
                bars=bars,
                horizon_minutes=60,
            )
            assert state in TERMINAL_OUTCOME_STATES
            assert meta is not None
            entry = float(meta["entry_price"])  # type: ignore[arg-type]
            exit_ = float(meta["exit_price"])  # type: ignore[arg-type]
            fav = float(meta["favorable_excursion"])  # type: ignore[arg-type]
            adv = float(meta["adverse_excursion"])  # type: ignore[arg-type]
            # Envelope invariants: highs >= max(entry, exit) >= lows...
            assert fav >= max(entry, exit_) - 1e-9
            assert adv <= min(entry, exit_) + 1e-9
            # ...and the verdict agrees with direction * sign of move.
            direction = 1.0 if signal_type == "BUY" else -1.0
            expected = (
                SignalOutcomeState.POSITIVE
                if (exit_ - entry) * direction > 0
                else SignalOutcomeState.NEGATIVE
            )
            assert state is expected

    def test_deterministic_replay(self) -> None:
        rng = random.Random(42)
        timestamp = datetime.datetime(2026, 9, 23, 10, 0, tzinfo=UTC)
        bars = [
            _bar(i, base=100.0 + rng.uniform(-5, 5), timestamp=timestamp)
            for i in range(5)
        ]
        first = evaluate_signal_outcome(
            signal_id="replay",
            signal_type="BUY",
            timestamp=timestamp,
            bars=bars,
            horizon_minutes=60,
        )
        second = evaluate_signal_outcome(
            signal_id="replay",
            signal_type="BUY",
            timestamp=timestamp,
            bars=bars,
            horizon_minutes=60,
        )
        assert first == second


class TestHorizonValidation:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            (1, 1),
            (60, 60),
            (1440, 1440),
            (0, MIN_OUTCOME_HORIZON_MINUTES),
            (-5, MIN_OUTCOME_HORIZON_MINUTES),
            (5000, MAX_OUTCOME_HORIZON_MINUTES),
            (True, 60),  # bool is not a valid int horizon
            (2.5, 60),
            ("90", 60),
            (None, 60),
        ],
    )
    def test_clamping_and_degradation(self, raw: Any, expected: int) -> None:
        assert validate_signal_outcome_horizon(raw) == expected


class TestAsciiGate:
    def test_module_source_is_ascii(self) -> None:
        """Same ASCII discipline as the repo's check_src_ascii gate."""
        import sys
        from pathlib import Path

        module = sys.modules["loats.signal_outcomes"]
        module_file = module.__file__
        assert module_file is not None
        source = Path(module_file).read_text(encoding="utf-8")
        assert source.isascii(), "non-ASCII character in signal_outcomes.py"
        assert "TODO" not in source
        assert not re.search(r"print\(", source)
