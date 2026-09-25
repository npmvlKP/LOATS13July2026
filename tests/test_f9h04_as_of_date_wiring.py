"""
Signal-store provenance policy (F9-L-03 store hygiene): every
production-signal fixture in this module either carries a valid
``metadata["source"]`` tag (a StrengthSource value or a documented
exemption) or uses the explicit ``{"test": ...}`` provenance key.
The insert-time guard rejects untagged/unknown-source rows by design;
pinned by tests/test_signal_source_guard.py.
F9-H-04 (TODO-5): the live CMP cycle must supply the snapshot date.

FR9 forensic finding: the F8-L-02 half-close built the entire
``as_of_date`` plumbing (model field, engine parameter, SQLite column,
CREATE/ROUTE audit rows) but the production caller -- the trading
cycle's CMP step -- passed ``as_of_date=None`` unconditionally, so
0/1,542 decisions and 100% of ROUTE rows carried NULL.

Acceptance pinned here (FR9 "Recommended Tests" + register items):
    - The cycle derives the snapshot date from the input batch itself
      (max bar timestamp) -- decision ``as_of_date`` == the data
      snapshot it was computed from.
    - T-1 data records T-1: a batch of yesterday's bars stamps
      yesterday, proving data-derivation, not wall-clock derivation.
    - An explicit caller-supplied date still wins (backtest path
      unchanged; pinned in tests/test_as_of_date_propagation.py).
    - CREATE audit rows (new_state) and ROUTE audit rows (metadata)
      carry the same derived ISO value.
    - An empty input batch leaves records unpinned (None) -- honest
      degradation, never a fabricated date.
    - The cycle calls the CMP step with ``as_of_date=None``: derivation
      lives INSIDE the CMP step where the input batch exists, keeping
      the external verifier's pinned orchestrator signature intact.

Supersedes the cycle-level half of the F8-L-02 live-default contract
("omission leaves records unpinned"): that contract stays true at the
engine API level (see tests/test_as_of_date_propagation.py) but no
longer describes the production cycle.
"""

from __future__ import annotations

import datetime
from contextlib import ExitStack
from datetime import UTC, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from loats.database import Database
from loats.models import Signal, SignalType
from loats.orchestrator import TradingOrchestrator
from loats.strength import StrengthSource

SOURCES = [
    StrengthSource.TECHNICAL_ANALYSIS,
    StrengthSource.SENTIMENT,
    StrengthSource.PRICE_ACTION,
    StrengthSource.VOLATILITY,
]


async def _store_signals(db: Database, ages_seconds: list[float]) -> None:
    """Persist one BUY signal per canonical source, staggered backwards."""
    now = datetime.datetime.now(UTC)
    for i, source in enumerate(SOURCES):
        await db.async_create_signal(
            Signal(
                symbol="NIFTY",
                signal_type=SignalType.BUY,
                strength=0.8 - i * 0.02,
                timestamp=now - timedelta(seconds=ages_seconds[i]),
                indicators={"v": 0.5},
                confidence=0.8,
                metadata={"source": source.value},
            )
        )


def _history_payload(bar_dates: list[datetime.datetime]) -> dict:
    """Build a /history payload whose bar timestamps are exactly given."""
    return {
        "data": [
            {
                "timestamp": ts.isoformat(),
                "open": 24500.0 + i,
                "high": 24550.0 + i,
                "low": 24470.0 + i,
                "close": 24510.0 + i,
                "volume": 1000000 + i,
            }
            for i, ts in enumerate(bar_dates)
        ]
    }


def _mocked_cycle_ctx(
    orch: TradingOrchestrator, history: dict, db: Database
) -> ExitStack:
    """Run the CMP step against real stored signals and a fixed batch."""
    mock_rules = MagicMock()
    mock_rules.apply_gating_rules.return_value = (
        True,
        {"reason": "passed", "iv_rank": 50.0, "adx": 30.0, "vix": 14.0},
    )
    mock_rules.check_position_limits.return_value = (True, {"reason": "ok"})
    mock_rules.session_state = "REGULAR"

    mock_settings = MagicMock()
    mock_settings.default_symbol = "NIFTY"
    mock_settings.enable_trailing_stops = False

    stack = ExitStack()
    stack.enter_context(patch("loats.orchestrator.db", db))
    stack.enter_context(patch("loats.trade_decision.db", db))
    stack.enter_context(patch("loats.orchestrator.rules_engine", new=mock_rules))
    stack.enter_context(patch("loats.trade_decision.rules_engine", new=mock_rules))
    stack.enter_context(patch("loats.orchestrator.settings", mock_settings))
    stack.enter_context(
        patch.object(
            orch, "_safe_get_history", new_callable=AsyncMock, return_value=history
        )
    )
    stack.enter_context(
        patch.object(
            orch,
            "_safe_get_quotes",
            new_callable=AsyncMock,
            return_value={"data": {"NIFTY": {"last_price": 24500.0}}},
        )
    )
    stack.enter_context(
        patch.object(
            orch,
            "_safe_get_funds",
            new_callable=AsyncMock,
            return_value={
                "data": {
                    "available_cash": 100000.0,
                    "utilized_margin": 20000.0,
                    "available_margin": 80000.0,
                    "total_equity": 120000.0,
                }
            },
        )
    )
    return stack


def _make_db(tmp_path: Path, name: str) -> Database:
    db = Database(
        db_path=tmp_path / f"{name}.db",
        audit_log_path=tmp_path / f"{name}_audit.jsonl",
    )
    db._initialize_database()
    return db


def _bar(ts: datetime.datetime) -> SimpleNamespace:
    """Duck-typed bar: the helper reads ``.timestamp`` only (the
    orchestrator has already parsed real HistoricalData objects)."""
    return SimpleNamespace(timestamp=ts)


class TestDeriveHistorySnapshotDate:
    """Unit contract for the derivation helper (chain-sibling invariant)."""

    def test_out_of_order_bars_yield_latest_timestamp(self) -> None:
        bars = [
            _bar(datetime.datetime(2026, 9, 14, 5, 0, tzinfo=UTC)),
            _bar(datetime.datetime(2026, 9, 16, 9, 45, tzinfo=UTC)),
            _bar(datetime.datetime(2026, 9, 15, 10, 0, tzinfo=UTC)),
        ]
        derived = TradingOrchestrator._derive_history_snapshot_date(bars)
        assert derived == datetime.date(2026, 9, 16)

    def test_empty_batch_degrades_to_none(self) -> None:
        assert TradingOrchestrator._derive_history_snapshot_date([]) is None

    def test_t1_batch_records_t1_not_wall_clock(self) -> None:
        """Every bar dated yesterday must stamp yesterday -- the wall
        clock ('today' at test runtime) is a different date."""
        yesterday = datetime.datetime.now(UTC).date() - timedelta(days=1)
        bars = [
            _bar(
                datetime.datetime.combine(yesterday, datetime.time(hour, 0), tzinfo=UTC)
            )
            for hour in (4, 5, 6)
        ]
        derived = TradingOrchestrator._derive_history_snapshot_date(bars)
        assert derived == yesterday

    def test_single_bar_yields_that_bar_date(self) -> None:
        bar = _bar(datetime.datetime(2026, 9, 1, 4, 30, tzinfo=UTC))
        derived = TradingOrchestrator._derive_history_snapshot_date([bar])
        assert derived == datetime.date(2026, 9, 1)


class TestCycleSuppliesDerivedDate:
    """End-to-end acceptance: the LIVE cycle (no caller date) stamps."""

    @pytest.mark.asyncio
    async def test_cycle_stamps_derived_date_into_decision(
        self, tmp_path: Path
    ) -> None:
        db = _make_db(tmp_path, "derive")
        await _store_signals(db, [10.0, 20.0, 30.0, 40.0])
        orch = TradingOrchestrator()

        expected = datetime.date(2026, 9, 16)
        history = _history_payload(
            [
                datetime.datetime(2026, 9, 15, 5, 0, tzinfo=UTC),
                datetime.datetime(2026, 9, 16, 9, 45, tzinfo=UTC),
                datetime.datetime(2026, 9, 16, 9, 50, tzinfo=UTC),
            ]
        )

        with _mocked_cycle_ctx(orch, history, db):
            await orch._execute_cmp_strategy()

        try:
            decisions = await _to_thread(db.get_trade_decisions, "NIFTY")
            assert len(decisions) == 1
            assert decisions[0].as_of_date == expected
        finally:
            db.close_all()

    @pytest.mark.asyncio
    async def test_cycle_audit_rows_carry_derived_iso(self, tmp_path: Path) -> None:
        db = _make_db(tmp_path, "audit")
        await _store_signals(db, [10.0, 20.0, 30.0, 40.0])
        orch = TradingOrchestrator()

        history = _history_payload([datetime.datetime(2026, 9, 16, 9, 50, tzinfo=UTC)])

        with _mocked_cycle_ctx(orch, history, db):
            await orch._execute_cmp_strategy()

        try:
            decisions = await _to_thread(db.get_trade_decisions, "NIFTY")
            assert len(decisions) == 1
            decision_id = decisions[0].decision_id

            entries = await _to_thread(db.get_audit_log, entity_type="trade_decision")
            create_rows = [
                e
                for e in entries
                if e.action == "CREATE" and e.entity_id == decision_id
            ]
            assert create_rows, "CREATE audit row missing for cycle decision"
            assert create_rows[0].new_state.get("as_of_date") == "2026-09-16"
            route_rows = [
                e for e in entries if e.action == "ROUTE" and e.entity_id == decision_id
            ]
            assert route_rows, "ROUTE audit row missing for cycle decision"
            assert route_rows[0].metadata.get("as_of_date") == "2026-09-16"
        finally:
            db.close_all()

    @pytest.mark.asyncio
    async def test_cycle_empty_batch_leaves_records_unpinned(
        self, tmp_path: Path
    ) -> None:
        """Honest degradation: no input bars -> None, never fabricated."""
        db = _make_db(tmp_path, "empty")
        await _store_signals(db, [10.0, 20.0, 30.0, 40.0])
        orch = TradingOrchestrator()

        with _mocked_cycle_ctx(orch, {"data": []}, db):
            await orch._execute_cmp_strategy()

        try:
            decisions = await _to_thread(db.get_trade_decisions, "NIFTY")
            for decision in decisions:
                assert decision.as_of_date is None
        finally:
            db.close_all()


_to_thread = __import__("asyncio").to_thread
