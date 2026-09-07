"""F8-L-02 (CMP Rule 8): caller-supplied as-of date propagation.

Registered audit item ``as_of_date`` (F8-L-02) -- the carried determinism
gap from the 01Sep2026 forensic register: decision/audit records carried
no explicit as-of date, so backtests could not pin a result to the input
snapshot date it was computed from.

Acceptance (registered):
    Records carry ``as_of_date`` equal to the input snapshot date.

Invariants pinned here:
    - The as-of date is CALLER-SUPPLIED ONLY. No module under src/loats
      may call ``date.today()`` (zero-occurrence invariant, previously
      verifier-pinned, now also test-pinned); omission leaves the field
      None so live-cycle behaviour is unchanged.
    - A stamped decision survives the SQLite round trip (new nullable
      ``as_of_date`` TEXT column, ISO-8601) and pre-existing rows read
      back as None.
    - CREATE trade-decision audit rows (new_state) and ROUTE audit rows
      (metadata) carry the same ISO as-of value.
    - The orchestrator CMP step accepts the snapshot date and stamps
      every produced record (end-to-end acceptance path).
"""

from __future__ import annotations

import datetime
from datetime import UTC, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from loats.database import Database
from loats.models import (
    FundsData,
    HistoricalData,
    Signal,
    SignalType,
    TradeDecision,
)
from loats.orchestrator import TradingOrchestrator
from loats.strength import StrengthSource
from loats.trade_decision import TradeDecisionEngine

AS_OF = datetime.date(2026, 9, 1)
AS_OF_ISO = "2026-09-01"

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_LOATS = REPO_ROOT / "src" / "loats"


def _sigs(n: int = 4, base_str: float = 0.75) -> list[Signal]:
    """Known-source signals mirroring the canonical engine test batch."""
    sources = [
        StrengthSource.TECHNICAL_ANALYSIS,
        StrengthSource.SENTIMENT,
        StrengthSource.PRICE_ACTION,
        StrengthSource.VOLATILITY,
    ]
    now = datetime.datetime.now(UTC)
    return [
        Signal(
            symbol="NIFTY",
            signal_type=SignalType.BUY,
            strength=base_str - i * 0.05,
            timestamp=now - timedelta(seconds=i * 30),
            indicators={"v": 0.5 + i * 0.1},
            confidence=0.8 - i * 0.05,
            metadata={"source": sources[i % len(sources)].value},
        )
        for i in range(min(n, len(sources)))
    ]


def _hist() -> list[HistoricalData]:
    now = datetime.datetime.now(UTC)
    return [
        HistoricalData(
            symbol="NIFTY",
            timestamp=now - timedelta(minutes=5 * (30 - i)),
            open=24500.0 + i * 10,
            high=24550.0 + i * 10,
            low=24470.0 + i * 10,
            close=24510.0 + i * 10,
            volume=1000000 + i * 10000,
            interval="5min",
        )
        for i in range(30)
    ]


def _funds() -> FundsData:
    return FundsData(
        available_cash=100000.0,
        utilized_margin=20000.0,
        available_margin=80000.0,
        total_equity=120000.0,
        timestamp=datetime.datetime.now(UTC),
    )


def _make_td(as_of_date: datetime.date | None = None) -> TradeDecision:
    return TradeDecision(
        symbol="NIFTY",
        decision_type=SignalType.BUY,
        composite_strength=0.8,
        timestamp=datetime.datetime.now(UTC),
        entry_price=24500.0,
        quantity=25,
        stop_loss=24255.0,
        take_profit=24990.0,
        risk_percentage=0.02,
        status="PENDING",
        as_of_date=as_of_date,
    )


def _make_db(tmp_path: Path) -> Database:
    db = Database(
        db_path=tmp_path / "asof.db",
        audit_log_path=tmp_path / "asof_audit.jsonl",
    )
    db._initialize_database()
    return db


class TestZeroDateTodayInvariant:
    """The zero-date.today() invariant must survive F8-L-02.

    The as-of date is caller-supplied ONLY; deriving it inside src/loats
    (date.today()) would silently reintroduce the nondeterminism this
    item closes. Previously pinned only by the external carried-set
    verifier; pinned here so the gate runs inside the suite too.
    """

    def test_src_tree_has_zero_date_today(self) -> None:
        hits = [
            str(p.relative_to(REPO_ROOT))
            for p in sorted(SRC_LOATS.rglob("*.py"))
            if "__pycache__" not in p.parts
            and "date.today(" in p.read_text(encoding="utf-8")
        ]
        assert hits == [], f"date.today() must stay absent from src/loats: {hits}"


class TestEnginePropagation:
    """TradeDecisionEngine stamps the caller-supplied snapshot date."""

    @pytest.fixture
    def engine(self) -> TradeDecisionEngine:
        return TradeDecisionEngine()

    @pytest.mark.asyncio
    async def test_engine_propagates_as_of_date_into_decision(
        self, engine: TradeDecisionEngine
    ) -> None:
        with patch("loats.trade_decision.rules_engine") as mock_rules:
            mock_rules.apply_gating_rules.return_value = (
                True,
                {"reason": "passed", "iv_rank": 50.0, "adx": 30.0, "vix": 14.0},
            )
            mock_rules.check_position_limits.return_value = (True, {"reason": "ok"})
            mock_rules.session_state = "REGULAR"
            decision, result = await engine.create_trade_decision(
                signals=_sigs(4),
                historical_data=_hist(),
                current_price=24500.0,
                funds=_funds(),
                current_positions=[],
                as_of_date=AS_OF,
            )
        assert decision is not None
        assert decision.as_of_date == AS_OF
        assert result["as_of_date"] == AS_OF_ISO
        # The model field is the carrier; metadata must not duplicate it.
        assert "as_of_date" not in decision.metadata

    @pytest.mark.asyncio
    async def test_engine_omitted_as_of_date_leaves_none(
        self, engine: TradeDecisionEngine
    ) -> None:
        """Default path is unchanged: no caller date -> None, live cycle
        behaviour identical (acceptance is additive, not mandatory)."""
        with patch("loats.trade_decision.rules_engine") as mock_rules:
            mock_rules.apply_gating_rules.return_value = (
                True,
                {"reason": "passed", "iv_rank": 50.0, "adx": 30.0, "vix": 14.0},
            )
            mock_rules.check_position_limits.return_value = (True, {"reason": "ok"})
            mock_rules.session_state = "REGULAR"
            decision, result = await engine.create_trade_decision(
                signals=_sigs(4),
                historical_data=_hist(),
                current_price=24500.0,
                funds=_funds(),
                current_positions=[],
            )
        assert decision is not None
        assert decision.as_of_date is None
        # Uniform echo contract: the key is always present; an omitted
        # input date reads back as None.
        assert result["as_of_date"] is None

    @pytest.mark.asyncio
    async def test_rejection_diagnostics_carry_as_of_date(
        self, engine: TradeDecisionEngine
    ) -> None:
        """Even a rejected batch is traceable to its snapshot date."""
        _, result = await engine.create_trade_decision(
            signals=_sigs(4, base_str=0.2),
            historical_data=_hist(),
            current_price=24500.0,
            funds=_funds(),
            current_positions=[],
            as_of_date=AS_OF,
        )
        assert result["status"] == "rejected"
        assert result["as_of_date"] == AS_OF_ISO

    def test_analyzer_payload_carries_as_of_date(self) -> None:
        stamped = _make_td(AS_OF).to_analyzer_payload()
        assert stamped["as_of_date"] == AS_OF_ISO
        omitted = _make_td().to_analyzer_payload()
        assert omitted["as_of_date"] is None


class TestDatabaseRoundTrip:
    """The trade_decisions row carries the as-of date both directions."""

    def test_round_trip_stamps_and_preserves_absence(self, tmp_path: Path) -> None:
        db = _make_db(tmp_path)
        try:
            stamped = _make_td(AS_OF)
            assert db.create_trade_decision(stamped) is True
            got = db.get_trade_decision(stamped.decision_id)
            assert got is not None
            assert got.as_of_date == AS_OF

            plain = _make_td()
            assert db.create_trade_decision(plain) is True
            got_plain = db.get_trade_decision(plain.decision_id)
            assert got_plain is not None
            assert got_plain.as_of_date is None
        finally:
            db.close_all()

    def test_as_of_date_column_exists_for_migrations(self, tmp_path: Path) -> None:
        db = _make_db(tmp_path)
        try:
            conn = db._get_connection()
            cols = {
                row[1] for row in conn.execute("PRAGMA table_info(trade_decisions)")
            }
            assert "as_of_date" in cols
        finally:
            db.close_all()


class TestAuditPropagation:
    """CREATE and ROUTE audit rows carry the as-of date."""

    def test_create_audit_row_new_state_carries_as_of_date(
        self, tmp_path: Path
    ) -> None:
        db = _make_db(tmp_path)
        try:
            td = _make_td(AS_OF)
            db.create_trade_decision(td)
            entries = [
                e
                for e in db.get_audit_log(entity_type="trade_decision", limit=50)
                if e.action == "CREATE" and e.entity_id == td.decision_id
            ]
            assert entries, "CREATE audit row for trade_decision missing"
            assert entries[0].new_state.get("as_of_date") == AS_OF_ISO
        finally:
            db.close_all()

    @pytest.mark.asyncio
    async def test_route_audit_row_metadata_carries_as_of_date(self) -> None:
        engine = TradeDecisionEngine()
        engine.analyzer_routing_enabled = False
        td = _make_td(AS_OF)
        with patch("loats.trade_decision.db") as mdb:
            mdb.async_get_trade_decision = AsyncMock(return_value=None)
            mdb.async_create_trade_decision = AsyncMock()
            mdb.async_log_audit = AsyncMock()
            response = await engine.route_to_analyzer(td)
        assert response["status"] == "disabled"
        route_calls = [
            c
            for c in mdb.async_log_audit.await_args_list
            if c.kwargs.get("action") == "ROUTE"
        ]
        assert route_calls, "ROUTE audit row missing"
        meta = route_calls[0].kwargs["metadata"]
        assert meta["as_of_date"] == AS_OF_ISO


class TestOrchestratorPropagation:
    """End-to-end acceptance: the CMP cycle stamps every record."""

    @staticmethod
    def _hist_payload() -> dict:
        base = datetime.datetime.now(UTC)
        return {
            "data": [
                {
                    "timestamp": (base - timedelta(minutes=5 * (30 - i))).isoformat(),
                    "open": 24500.0 + i * 10,
                    "high": 24550.0 + i * 10,
                    "low": 24470.0 + i * 10,
                    "close": 24510.0 + i * 10,
                    "volume": 1000000 + i * 10000,
                }
                for i in range(30)
            ]
        }

    @pytest.mark.asyncio
    async def test_cycle_stamps_caller_as_of_date_into_records(
        self, tmp_path: Path
    ) -> None:
        db = Database(
            db_path=tmp_path / "cycle.db",
            audit_log_path=tmp_path / "cycle_audit.jsonl",
        )
        db._initialize_database()
        orch = TradingOrchestrator()

        now = datetime.datetime.now(UTC)
        sources = [
            StrengthSource.TECHNICAL_ANALYSIS,
            StrengthSource.SENTIMENT,
            StrengthSource.PRICE_ACTION,
            StrengthSource.VOLATILITY,
        ]
        for i, source in enumerate(sources):
            await db.async_create_signal(
                Signal(
                    symbol="NIFTY",
                    signal_type=SignalType.BUY,
                    strength=0.8 - i * 0.02,
                    timestamp=now - timedelta(seconds=10 * i),
                    indicators={"v": 0.5},
                    confidence=0.8,
                    metadata={"source": source.value},
                )
            )

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

        with (
            patch("loats.orchestrator.db", db),
            patch("loats.trade_decision.db", db),
            patch("loats.orchestrator.rules_engine", new=mock_rules),
            patch("loats.trade_decision.rules_engine", new=mock_rules),
            patch("loats.orchestrator.settings", mock_settings),
            patch.object(
                orch,
                "_safe_get_history",
                new_callable=AsyncMock,
                return_value=self._hist_payload(),
            ),
            patch.object(
                orch,
                "_safe_get_quotes",
                new_callable=AsyncMock,
                return_value={"data": {"NIFTY": {"last_price": 24500.0}}},
            ),
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
            ),
        ):
            await orch._execute_cmp_strategy(as_of_date=AS_OF)

        try:
            decisions = await asyncio_to_thread(db.get_trade_decisions, "NIFTY")
            assert len(decisions) == 1, (
                f"expected exactly one TradeDecision, got {len(decisions)}"
            )
            assert decisions[0].as_of_date == AS_OF

            entries = await asyncio_to_thread(
                db.get_audit_log, entity_type="trade_decision"
            )
            create_rows = [
                e
                for e in entries
                if e.action == "CREATE" and e.entity_id == decisions[0].decision_id
            ]
            assert create_rows, "CREATE audit row missing for cycle decision"
            assert create_rows[0].new_state.get("as_of_date") == AS_OF_ISO
            route_rows = [
                e
                for e in entries
                if e.action == "ROUTE" and e.entity_id == decisions[0].decision_id
            ]
            assert route_rows, "ROUTE audit row missing for cycle decision"
            assert route_rows[0].metadata.get("as_of_date") == AS_OF_ISO
        finally:
            db.close_all()

    @pytest.mark.asyncio
    async def test_cycle_without_as_of_date_keeps_records_null(
        self, tmp_path: Path
    ) -> None:
        """Live default is unchanged: omitted date -> records carry None."""
        db = Database(
            db_path=tmp_path / "cycle_default.db",
            audit_log_path=tmp_path / "cycle_default_audit.jsonl",
        )
        db._initialize_database()
        orch = TradingOrchestrator()

        now = datetime.datetime.now(UTC)
        sources = [
            StrengthSource.TECHNICAL_ANALYSIS,
            StrengthSource.SENTIMENT,
            StrengthSource.PRICE_ACTION,
            StrengthSource.VOLATILITY,
        ]
        for i, source in enumerate(sources):
            await db.async_create_signal(
                Signal(
                    symbol="NIFTY",
                    signal_type=SignalType.BUY,
                    strength=0.8 - i * 0.02,
                    timestamp=now - timedelta(seconds=10 * i),
                    indicators={"v": 0.5},
                    confidence=0.8,
                    metadata={"source": source.value},
                )
            )

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

        with (
            patch("loats.orchestrator.db", db),
            patch("loats.trade_decision.db", db),
            patch("loats.orchestrator.rules_engine", new=mock_rules),
            patch("loats.trade_decision.rules_engine", new=mock_rules),
            patch("loats.orchestrator.settings", mock_settings),
            patch.object(
                orch,
                "_safe_get_history",
                new_callable=AsyncMock,
                return_value=self._hist_payload(),
            ),
            patch.object(
                orch,
                "_safe_get_quotes",
                new_callable=AsyncMock,
                return_value={"data": {"NIFTY": {"last_price": 24500.0}}},
            ),
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
            ),
        ):
            await orch._execute_cmp_strategy()

        try:
            decisions = await asyncio_to_thread(db.get_trade_decisions, "NIFTY")
            assert len(decisions) == 1
            assert decisions[0].as_of_date is None
        finally:
            db.close_all()


# Local alias keeps the async DB reads above honest without shadowing the
# datetime module import used throughout this file.
asyncio_to_thread = __import__("asyncio").to_thread
