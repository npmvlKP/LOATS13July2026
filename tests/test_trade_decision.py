"""Tests for TradeDecision engine."""

import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from loats.database import Database
from loats.models import FundsData, HistoricalData, Signal, SignalType, TradeDecision
from loats.strength import StrengthEngine, StrengthSource, resolve_source
from loats.trade_decision import DecisionStatus, TradeDecisionEngine


@pytest.fixture
def temp_db():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        db = Database(db_path=Path(td) / "td.db", audit_log_path=Path(td) / "a.jsonl")
        db._initialize_database()
        yield db
        db.close_all()


@pytest.fixture
def td_engine():
    return TradeDecisionEngine()


@pytest.fixture
def funds():
    return FundsData(
        available_cash=100000.0,
        utilized_margin=20000.0,
        available_margin=80000.0,
        total_equity=120000.0,
        timestamp=datetime.now(UTC),
    )


@pytest.fixture
def hist():
    now = datetime.now(UTC)
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


def _sigs(n, base_str=0.75, st=SignalType.BUY):
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


def _make_td():
    return TradeDecision(
        symbol="NIFTY",
        decision_type=SignalType.BUY,
        composite_strength=0.8,
        timestamp=datetime.now(UTC),
        entry_price=24500.0,
        quantity=25,
        stop_loss=24255.0,
        take_profit=24990.0,
        risk_percentage=0.02,
        status="PENDING",
    )


class TestStrength:
    def test_composite_three_sources(self):
        cs, d = StrengthEngine().calculate_composite_strength(_sigs(3))
        assert 0.0 <= cs <= 1.0
        assert d["sources"] == 3

    def test_composite_opposition(self):
        now = datetime.now(UTC)
        sigs = [
            Signal(
                symbol="NIFTY",
                signal_type=SignalType.BUY,
                strength=0.8,
                timestamp=now,
                indicators={},
                confidence=0.8,
                metadata={"source": StrengthSource.TECHNICAL_ANALYSIS.value},
            ),
            Signal(
                symbol="NIFTY",
                signal_type=SignalType.SELL,
                strength=0.75,
                timestamp=now - timedelta(seconds=30),
                indicators={},
                confidence=0.75,
                metadata={"source": StrengthSource.SENTIMENT.value},
            ),
            Signal(
                symbol="NIFTY",
                signal_type=SignalType.BUY,
                strength=0.7,
                timestamp=now - timedelta(seconds=60),
                indicators={},
                confidence=0.7,
                metadata={"source": StrengthSource.PRICE_ACTION.value},
            ),
        ]
        cs, d = StrengthEngine().calculate_composite_strength(sigs)
        assert "opposition_details" in d or "opposition_check" in d

    def test_insufficient_sources(self):
        ok, d = StrengthEngine().validate_signal_sources(_sigs(2))
        assert ok is False
        assert d["reason"] == "insufficient_unique_sources"

    def test_unknown_source(self):
        now = datetime.now(UTC)
        sigs = _sigs(2) + [
            Signal(
                symbol="NIFTY",
                signal_type=SignalType.BUY,
                strength=0.68,
                timestamp=now - timedelta(seconds=60),
                indicators={},
                confidence=0.72,
                metadata={"source": "bad"},
            )
        ]
        ok, d = StrengthEngine().validate_signal_sources(sigs)
        assert ok is False
        assert d["reason"] == "unknown_source"

    def test_duplicate_sources(self):
        now = datetime.now(UTC)
        sigs = [
            Signal(
                symbol="NIFTY",
                signal_type=SignalType.BUY,
                strength=0.8,
                timestamp=now,
                indicators={},
                confidence=0.8,
                metadata={"source": StrengthSource.TECHNICAL_ANALYSIS.value},
            )
        ] * 3
        ok, d = StrengthEngine().validate_signal_sources(sigs)
        assert ok is False

    def test_resolve_valid(self):
        assert resolve_source("ta") == StrengthSource.TECHNICAL_ANALYSIS
        assert resolve_source("sentiment") == StrengthSource.SENTIMENT

    def test_resolve_invalid(self):
        with pytest.raises(ValueError):
            resolve_source("bad")


class TestDecisionCreation:
    @pytest.mark.asyncio
    async def test_valid_signals(self, td_engine, hist, funds):
        with patch("loats.trade_decision.rules_engine") as mr:
            mr.apply_gating_rules.return_value = (
                True,
                {"reason": "passed", "iv_rank": 50.0, "adx": 30.0, "vix": 14.0},
            )
            mr.check_position_limits.return_value = (True, {"reason": "ok"})
            mr.session_state = "REGULAR"
            d, _ = await td_engine.create_trade_decision(
                signals=_sigs(4),
                historical_data=hist,
                current_price=24500.0,
                funds=funds,
                current_positions=[],
            )
        assert d is not None
        assert d.symbol == "NIFTY"

    @pytest.mark.asyncio
    async def test_weak_signals_rejected(self, td_engine, hist, funds):
        with patch("loats.trade_decision.rules_engine") as mr:
            mr.apply_gating_rules.return_value = (
                True,
                {"reason": "passed", "iv_rank": 50.0, "adx": 30.0, "vix": 14.0},
            )
            mr.check_position_limits.return_value = (True, {"reason": "ok"})
            mr.session_state = "REGULAR"
            d, r = await td_engine.create_trade_decision(
                signals=_sigs(4, 0.2),
                historical_data=hist,
                current_price=24500.0,
                funds=funds,
                current_positions=[],
            )
        assert d is None
        assert r["reason"] == "insufficient_strength"

    @pytest.mark.asyncio
    async def test_invalid_sources_rejected(self, td_engine, hist, funds):
        now = datetime.now(UTC)
        sigs = _sigs(2) + [
            Signal(
                symbol="NIFTY",
                signal_type=SignalType.BUY,
                strength=0.68,
                timestamp=now - timedelta(seconds=60),
                indicators={},
                confidence=0.72,
                metadata={"source": "bad"},
            )
        ]
        d, r = await td_engine.create_trade_decision(
            signals=sigs,
            historical_data=hist,
            current_price=24500.0,
            funds=funds,
            current_positions=[],
        )
        assert d is None
        assert r["reason"] == "signal_validation_failed"

    @pytest.mark.asyncio
    async def test_gating_rejected(self, td_engine, hist, funds):
        with patch("loats.trade_decision.rules_engine") as mr:
            mr.apply_gating_rules.return_value = (
                False,
                {"reason": "iv_rank_low", "iv_rank": 30.0},
            )
            mr.session_state = "REGULAR"
            d, r = await td_engine.create_trade_decision(
                signals=_sigs(4),
                historical_data=hist,
                current_price=24500.0,
                funds=funds,
                current_positions=[],
            )
        assert d is None
        assert r["reason"] == "gating_rules_failed"

    @pytest.mark.asyncio
    async def test_position_limit_rejected(self, td_engine, hist, funds):
        with patch("loats.trade_decision.rules_engine") as mr:
            mr.apply_gating_rules.return_value = (
                True,
                {"reason": "passed", "iv_rank": 50.0, "adx": 30.0, "vix": 14.0},
            )
            mr.check_position_limits.return_value = (
                False,
                {
                    "reason": "limit_exceeded",
                    "current_quantity": 150,
                    "max_allowed": 125,
                },
            )
            mr.session_state = "REGULAR"
            d, r = await td_engine.create_trade_decision(
                signals=_sigs(4),
                historical_data=hist,
                current_price=24500.0,
                funds=funds,
                current_positions=[],
            )
        assert d is None
        assert r["reason"] == "position_limit_exceeded"

    @pytest.mark.asyncio
    async def test_invalid_size_rejected(self, td_engine, hist, funds):
        with patch("loats.trade_decision.rules_engine") as mr:
            mr.apply_gating_rules.return_value = (
                True,
                {"reason": "passed", "iv_rank": 50.0, "adx": 30.0, "vix": 14.0},
            )
            mr.check_position_limits.return_value = (True, {"reason": "ok"})
            mr.session_state = "REGULAR"
            with patch("loats.trade_decision.sizing_engine") as ms:
                ms.calculate_fixed_fraction_size.return_value = (
                    0,
                    {"reason": "invalid_prices"},
                )
                d, r = await td_engine.create_trade_decision(
                    signals=_sigs(4),
                    historical_data=hist,
                    current_price=24500.0,
                    funds=funds,
                    current_positions=[],
                )
        assert d is None
        assert r["reason"] == "invalid_position_size"


class TestRouting:
    @pytest.mark.asyncio
    async def test_route_disabled(self, td_engine):
        td_engine.analyzer_routing_enabled = False
        with (
            patch("loats.database.db") as mdb,
            patch("loats.trade_decision.datetime") as mdt,
        ):
            mdt.datetime.now.return_value = __import__("datetime").datetime.now(
                __import__("datetime").timezone.utc
            )
            mdt.UTC = __import__("datetime").timezone.utc
            mdb.async_record_trade_decision = AsyncMock()
            r = await td_engine.route_to_analyzer(_make_td())
        assert r["status"] == "disabled"

    @pytest.mark.asyncio
    async def test_route_success(self, td_engine):
        td_engine.analyzer_routing_enabled = True
        with (
            patch("loats.database.db") as mdb,
            patch("loats.trade_decision.datetime") as mdt,
        ):
            mdt.datetime.now.return_value = __import__("datetime").datetime.now(
                __import__("datetime").timezone.utc
            )
            mdt.UTC = __import__("datetime").timezone.utc
            mdb.async_record_trade_decision = AsyncMock()
            with patch("loats.trade_decision.AsyncOpenAlgoClient") as mcc:
                mc = AsyncMock()
                mc.__aenter__ = AsyncMock(return_value=mc)
                mc.__aexit__ = AsyncMock()
                mc.place_analyzer_request = AsyncMock(
                    return_value={"status": "accepted"}
                )
                mcc.return_value = mc
                r = await td_engine.route_to_analyzer(_make_td())
        assert r["status"] == "success"

    @pytest.mark.asyncio
    async def test_route_error(self, td_engine):
        td_engine.analyzer_routing_enabled = True
        with (
            patch("loats.database.db") as mdb,
            patch("loats.trade_decision.datetime") as mdt,
        ):
            mdt.datetime.now.return_value = __import__("datetime").datetime.now(
                __import__("datetime").timezone.utc
            )
            mdt.UTC = __import__("datetime").timezone.utc
            mdb.async_record_trade_decision = AsyncMock()
            with patch("loats.trade_decision.AsyncOpenAlgoClient") as mcc:
                mc = AsyncMock()
                mc.__aenter__ = AsyncMock(return_value=mc)
                mc.__aexit__ = AsyncMock(return_value=False)
                mc.place_analyzer_request = AsyncMock(side_effect=Exception("fail"))
                mcc.return_value = mc
                try:
                    r = await td_engine.route_to_analyzer(_make_td())
                    assert r.get("status") == "error"
                except Exception as e:
                    assert "fail" in str(e)


class TestQueue:
    @pytest.mark.asyncio
    async def test_start_stop(self, td_engine):
        await td_engine.start_decision_processor()
        assert td_engine._processor_task is not None
        await td_engine.stop_decision_processor()

    @pytest.mark.asyncio
    async def test_enqueue(self, td_engine):
        td_engine.analyzer_routing_enabled = False
        with (
            patch("loats.database.db") as mdb,
            patch("loats.trade_decision.datetime") as mdt,
        ):
            mdt.datetime.now.return_value = __import__("datetime").datetime.now(
                __import__("datetime").timezone.utc
            )
            mdt.UTC = __import__("datetime").timezone.utc
            mdb.async_record_trade_decision = AsyncMock()
            r = await td_engine.enqueue_decision(_make_td())
        assert r["status"] == "queued"

    @pytest.mark.asyncio
    async def test_enqueue_error(self, td_engine):
        with patch.object(
            td_engine.decision_queue, "put_nowait", side_effect=RuntimeError("broken")
        ):
            r = await td_engine.enqueue_decision(_make_td())
        assert r["status"] == "error"

    @pytest.mark.asyncio
    async def test_enqueue_backpressure_full(self, td_engine):
        # Fill the bounded queue to maxsize, next enqueue should be rejected with queue_full
        small_engine = TradeDecisionEngine(maxsize=2)
        # Fill
        for _ in range(2):
            res = await small_engine.enqueue_decision(_make_td())
            assert res["status"] == "queued"
        assert small_engine.decision_queue.full() is True
        # Next should be rejected, not blocked
        res_full = await small_engine.enqueue_decision(_make_td())
        assert res_full["status"] == "rejected"
        assert res_full["reason"] == "queue_full"
        assert res_full["queue_maxsize"] == 2
        # Stats reflect bounded state
        stats = small_engine.get_queue_stats()
        assert stats["queue_size"] == 2
        assert stats["queue_maxsize"] == 2
        assert stats["queue_full"] is True

    @pytest.mark.asyncio
    async def test_queue_stats_and_maxsize(self, td_engine):
        stats = td_engine.get_queue_stats()
        assert "queue_size" in stats
        assert "queue_maxsize" in stats
        assert stats["queue_maxsize"] == td_engine.decision_queue.maxsize
        # Default from settings should be 100 (bounded)
        assert stats["queue_maxsize"] == 100
        # Verify queue is bounded (not unbounded maxsize=0)
        assert td_engine.decision_queue.maxsize > 0

    @pytest.mark.asyncio
    async def test_create_and_route_not_created(self, td_engine, hist, funds):
        r = await td_engine.create_and_route_decision(
            signals=_sigs(2),
            historical_data=hist,
            current_price=24500.0,
            funds=funds,
            current_positions=[],
        )
        assert r["routing_status"] == "skipped"
        assert r["reason"] == "decision_not_created"


class TestMisc:
    def test_enable_routing(self, td_engine):
        td_engine.analyzer_routing_enabled = False
        td_engine.enable_analyzer_routing()
        assert td_engine.analyzer_routing_enabled is True

    def test_disable_routing(self, td_engine):
        td_engine.disable_analyzer_routing()
        assert td_engine.analyzer_routing_enabled is False

    @pytest.mark.asyncio
    async def test_get_status(self, td_engine):
        r = await td_engine.get_decision_status("id1")
        assert r["decision_id"] == "id1"

    def test_modification_counter(self, td_engine):
        td_engine.reset_modification_counter()
        assert td_engine.get_modification_count() == 0
        td_engine.increment_modification_counter()
        assert td_engine.get_modification_count() == 1

    def test_enum_values(self):
        assert DecisionStatus.PENDING == "PENDING"
        assert DecisionStatus.APPROVED == "APPROVED"
        assert DecisionStatus.REJECTED == "REJECTED"
        assert DecisionStatus.EXECUTED == "EXECUTED"
