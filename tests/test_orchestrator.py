"""Tests for TradingOrchestrator CMP body."""

import asyncio
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from loats.database import Database
from loats.models import FundsData, HistoricalData, Signal, SignalType
from loats.orchestrator import TradingOrchestrator
from loats.strength import StrengthSource


@pytest.fixture
def temp_db():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        db = Database(
            db_path=Path(td) / "test_orch2.db",
            audit_log_path=Path(td) / "test_audit2.jsonl",
        )
        db._initialize_database()
        yield db
        db.close_all()


@pytest.fixture
def orch():
    return TradingOrchestrator()


def make_signals(count=3, symbol="NIFTY"):
    now = datetime.now(UTC)
    sources = [
        StrengthSource.TECHNICAL_ANALYSIS,
        StrengthSource.SENTIMENT,
        StrengthSource.PRICE_ACTION,
    ]
    return [
        Signal(
            symbol=symbol,
            signal_type=SignalType.BUY,
            strength=0.8 - i * 0.05,
            timestamp=now - timedelta(seconds=i * 10),
            indicators={"val": 0.5 + i * 0.1},
            confidence=0.8 - i * 0.05,
            metadata={"source": sources[i].value},
        )
        for i in range(min(count, 3))
    ]


def make_historical(count=30, symbol="NIFTY"):
    now = datetime.now(UTC)
    items = []
    for i in range(count):
        c = 24500.0 + i * 10
        items.append(
            HistoricalData(
                symbol=symbol,
                timestamp=now - timedelta(minutes=5 * (count - 1 - i)),
                open=c - 5,
                high=c + 10,
                low=c - 10,
                close=c,
                volume=1000000,
                interval="5min",
            )
        )
    return items


def make_funds_data():
    return FundsData(
        available_cash=100000.0,
        utilized_margin=20000.0,
        available_margin=80000.0,
        total_equity=120000.0,
        timestamp=datetime.now(UTC),
    )


class TestCMPStrategyExecution:
    @pytest.mark.asyncio
    async def test_insufficient_signals_early_return(self, orch, temp_db):
        with (
            patch("loats.orchestrator.settings") as mock_settings,
            patch("loats.orchestrator.db", temp_db),
            patch("loats.orchestrator.rules_engine") as mock_rules,
            patch("loats.orchestrator.record_cmp_chain_rejection") as mock_reject,
        ):
            mock_settings.default_symbol = "NIFTY"
            mock_settings.enable_trailing_stops = False
            mock_rules.is_trading_allowed.return_value = True
            mock_rules.session_state.value = "REGULAR"
            temp_db.async_get_latest_signals = AsyncMock(return_value=make_signals(2))
            await orch._execute_cmp_strategy()
            mock_reject.assert_called_once_with("insufficient_signals")
            assert orch._insufficient_signals_count == 1

    @pytest.mark.asyncio
    async def test_trading_not_allowed_skips(self, orch):
        with patch("loats.orchestrator.rules_engine") as mock_rules:
            mock_rules.is_trading_allowed.return_value = False
            with patch.object(
                orch, "_execute_cmp_strategy", new_callable=AsyncMock
            ) as mock_cmp:
                await orch._execute_trading_cycle()
                mock_cmp.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_historical_data_returns(self, orch, temp_db):
        with (
            patch("loats.orchestrator.settings") as mock_settings,
            patch("loats.orchestrator.db", temp_db),
            patch("loats.orchestrator.rules_engine") as mock_rules,
            patch.object(
                orch, "_safe_get_history", new_callable=AsyncMock, return_value=None
            ),
        ):
            mock_settings.default_symbol = "NIFTY"
            mock_settings.enable_trailing_stops = False
            mock_rules.is_trading_allowed.return_value = True
            mock_rules.session_state.value = "REGULAR"
            temp_db.async_get_latest_signals = AsyncMock(return_value=make_signals(3))
            await orch._execute_cmp_strategy()

    @pytest.mark.asyncio
    async def test_no_quote_data_returns(self, orch, temp_db):
        history = [
            {
                "timestamp": datetime.now(UTC).isoformat(),
                "open": 24500,
                "high": 24550,
                "low": 24450,
                "close": 24510,
                "volume": 1000000,
            }
        ]
        with (
            patch("loats.orchestrator.settings") as mock_settings,
            patch("loats.orchestrator.db", temp_db),
            patch("loats.orchestrator.rules_engine") as mock_rules,
            patch.object(
                orch,
                "_safe_get_history",
                new_callable=AsyncMock,
                return_value={"data": history},
            ),
            patch.object(
                orch, "_safe_get_quotes", new_callable=AsyncMock, return_value=None
            ),
        ):
            mock_settings.default_symbol = "NIFTY"
            mock_settings.enable_trailing_stops = False
            mock_rules.is_trading_allowed.return_value = True
            mock_rules.session_state.value = "REGULAR"
            temp_db.async_get_latest_signals = AsyncMock(return_value=make_signals(3))
            await orch._execute_cmp_strategy()

    @pytest.mark.asyncio
    async def test_no_funds_data_returns(self, orch, temp_db):
        history = [
            {
                "timestamp": datetime.now(UTC).isoformat(),
                "open": 24500,
                "high": 24550,
                "low": 24450,
                "close": 24510,
                "volume": 1000000,
            }
        ]
        quotes = {"data": {"NIFTY": {"last_price": 24510}}}
        with (
            patch("loats.orchestrator.settings") as mock_settings,
            patch("loats.orchestrator.db", temp_db),
            patch("loats.orchestrator.rules_engine") as mock_rules,
            patch.object(
                orch,
                "_safe_get_history",
                new_callable=AsyncMock,
                return_value={"data": history},
            ),
            patch.object(
                orch, "_safe_get_quotes", new_callable=AsyncMock, return_value=quotes
            ),
            patch.object(
                orch, "_safe_get_funds", new_callable=AsyncMock, return_value=None
            ),
        ):
            mock_settings.default_symbol = "NIFTY"
            mock_settings.enable_trailing_stops = False
            mock_rules.is_trading_allowed.return_value = True
            mock_rules.session_state.value = "REGULAR"
            temp_db.async_get_latest_signals = AsyncMock(return_value=make_signals(3))
            await orch._execute_cmp_strategy()


class TestOrchestratorInitialization:
    def test_initial_state(self, orch):
        assert orch.running is False
        assert orch.cycle_count == 0
        assert orch.last_cycle_time == 0.0
        assert orch.max_cycle_time == 0.0

    @pytest.mark.asyncio
    async def test_initialize_sets_running(self, orch):
        with patch("loats.orchestrator.db") as mock_db:
            mock_db._local_connection = MagicMock()
            mock_db.async_get_latest_signals = AsyncMock(return_value=[])
            await orch.initialize()
            assert orch.running is True
            assert orch.cycle_count == 0

    @pytest.mark.asyncio
    async def test_shutdown_sets_running_false(self, orch):
        with patch("loats.orchestrator.db") as mock_db:
            mock_db._local_connection = MagicMock()
            mock_db.async_get_latest_signals = AsyncMock(return_value=[])
            await orch.initialize()
            await orch.shutdown()
            assert orch.running is False


class TestSessionStateTracking:
    @pytest.mark.asyncio
    async def test_session_change_resets_counter(self, orch, temp_db):
        mock_session = MagicMock()
        mock_session.value = "REGULAR"
        with (
            patch("loats.orchestrator.settings") as mock_settings,
            patch("loats.orchestrator.db", temp_db),
            patch("loats.orchestrator.rules_engine") as mock_rules,
        ):
            mock_settings.default_symbol = "NIFTY"
            mock_settings.enable_trailing_stops = False
            mock_rules.is_trading_allowed.return_value = True
            mock_rules.session_state = mock_session
            temp_db.async_get_latest_signals = AsyncMock(return_value=make_signals(2))
            mock_session.value = "REGULAR"
            await orch._execute_cmp_strategy()
            assert orch._insufficient_signals_count == 1
            mock_session.value = "CLOSING"
            await orch._execute_cmp_strategy()
            assert orch._insufficient_signals_count == 1


class TestInsufficientSignalsTracking:
    @pytest.mark.asyncio
    async def test_counter_increments(self, orch, temp_db):
        mock_session = MagicMock()
        mock_session.value = "REGULAR"
        with (
            patch("loats.orchestrator.settings") as mock_settings,
            patch("loats.orchestrator.db", temp_db),
            patch("loats.orchestrator.rules_engine") as mock_rules,
        ):
            mock_settings.default_symbol = "NIFTY"
            mock_settings.enable_trailing_stops = False
            mock_rules.is_trading_allowed.return_value = True
            mock_rules.session_state = mock_session
            temp_db.async_get_latest_signals = AsyncMock(return_value=make_signals(1))
            await orch._execute_cmp_strategy()
            await orch._execute_cmp_strategy()
            assert orch._insufficient_signals_count == 2


# -- Additional coverage tests ----------------------------------------------------
import numpy as np  # noqa: E402


class TestHurstExponent:
    def test_short_prices_returns_none(self):
        o = TradingOrchestrator()
        assert o._calculate_hurst_exponent(np.array([1.0] * 10)) is None

    def test_valid_prices_returns_float(self):
        o = TradingOrchestrator()
        np.random.seed(42)
        prices = np.cumsum(np.random.randn(100) * 0.01) + 100
        result = o._calculate_hurst_exponent(prices)
        assert result is not None
        assert isinstance(result, float)

    def test_exception_returns_none(self):
        o = TradingOrchestrator()
        with patch("loats.orchestrator.np.diff", side_effect=ValueError("bad")):
            assert o._calculate_hurst_exponent(np.array([1.0] * 100)) is None


class TestRecordCycleTime:
    def test_basic_record(self):
        o = TradingOrchestrator()
        o._record_cycle_time(0.05)
        assert o.cycle_count == 1
        assert o.last_cycle_time == 0.05

    def test_multiple_records(self):
        o = TradingOrchestrator()
        o._record_cycle_time(0.05)
        o._record_cycle_time(0.15)
        assert o.cycle_count == 2
        assert o.max_cycle_time == 0.15


class TestModelCreation:
    def test_create_position_model(self):
        o = TradingOrchestrator()
        pos = o._create_position_model(
            {
                "symbol": "NIFTY",
                "quantity": 100,
                "average_price": 24000.0,
                "last_price": 24100.0,
                "pnl": 10000.0,
                "product_type": "MIS",
            }
        )
        assert pos.symbol == "NIFTY"

    def test_create_funds_model(self):
        o = TradingOrchestrator()
        with patch("loats.orchestrator.datetime") as mdt:
            import datetime as dt

            mdt.datetime.now.return_value = dt.datetime(2025, 1, 1, tzinfo=dt.UTC)
            mdt.UTC = dt.UTC
            funds = o._create_funds_model(
                {
                    "available_cash": 50000.0,
                    "utilized_margin": 10000.0,
                    "available_margin": 40000.0,
                    "total_equity": 100000.0,
                }
            )
        assert funds.available_cash == 50000.0


class TestGetCycleStats:
    def test_initial_stats(self):
        o = TradingOrchestrator()
        stats = o.get_cycle_stats()
        assert stats["cycle_count"] == 0


class TestHandleCycleTaskCompletion:
    @pytest.mark.asyncio
    async def test_failed_task(self):
        o = TradingOrchestrator()
        o.running = True

        async def fail():
            raise RuntimeError("boom")

        task = asyncio.create_task(fail())
        await asyncio.sleep(0)
        try:
            o._handle_cycle_task_completion(task)
        except RuntimeError:
            pass
        assert o.running is False


class TestCheckKillSwitch:
    @pytest.mark.asyncio
    async def test_kill_switch_active(self):
        o = TradingOrchestrator()
        with patch(
            "loats.orchestrator.alerts.is_kill_switch_active", return_value=True
        ):
            with pytest.raises(Exception):
                await o._check_kill_switch()

    @pytest.mark.asyncio
    async def test_kill_switch_inactive(self):
        o = TradingOrchestrator()
        with patch(
            "loats.orchestrator.alerts.is_kill_switch_active", return_value=False
        ):
            await o._check_kill_switch()


class TestShutdown:
    @pytest.mark.asyncio
    async def test_shutdown_not_running(self):
        o = TradingOrchestrator()
        await o.shutdown()

    @pytest.mark.asyncio
    async def test_shutdown_running_no_task(self):
        o = TradingOrchestrator()
        o.running = True
        await o.shutdown()


class TestSafeGetters:
    @pytest.mark.asyncio
    async def test_safe_get_history_success(self):
        o = TradingOrchestrator()
        with patch("loats.orchestrator.async_client") as mc:
            mc.get_history = AsyncMock(return_value={"data": []})
            result = await o._safe_get_history("NIFTY", "5minute")
        assert result == {"data": []}

    @pytest.mark.asyncio
    async def test_safe_get_history_failure(self):
        o = TradingOrchestrator()
        with patch("loats.orchestrator.async_client") as mc:
            mc.get_history = AsyncMock(side_effect=Exception("fail"))
            result = await o._safe_get_history("NIFTY", "5minute")
        assert result is None

    @pytest.mark.asyncio
    async def test_safe_get_quotes_success(self):
        o = TradingOrchestrator()
        with patch("loats.orchestrator.async_client") as mc:
            mc.get_quotes = AsyncMock(return_value={"data": {"NIFTY": {}}})
            result = await o._safe_get_quotes(["NIFTY"])
        assert result is not None

    @pytest.mark.asyncio
    async def test_safe_get_position_book(self):
        o = TradingOrchestrator()
        with patch("loats.orchestrator.async_client") as mc:
            mc.get_position_book = AsyncMock(return_value={"data": []})
            result = await o._safe_get_position_book()
        assert result is not None

    @pytest.mark.asyncio
    async def test_safe_get_funds(self):
        o = TradingOrchestrator()
        with patch("loats.orchestrator.async_client") as mc:
            mc.get_funds = AsyncMock(return_value={"data": {}})
            result = await o._safe_get_funds()
        assert result is not None


class TestRunCycleLoop:
    @pytest.mark.asyncio
    async def test_kill_switch_pauses(self):
        from loats.openalgo import KillSwitchError

        o = TradingOrchestrator()
        call_count = 0

        async def fake_cycle():
            o._shutdown_event.set()

        async def kill_once():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise KillSwitchError()

        with patch.object(o, "_execute_trading_cycle", side_effect=fake_cycle):
            with patch.object(o, "_check_kill_switch", side_effect=kill_once):
                await o._run_cycle_loop()


class TestExecuteTradingCycle:
    @pytest.mark.asyncio
    async def test_full_cycle(self):
        import datetime as dt

        o = TradingOrchestrator()
        ms = MagicMock()
        ms.default_symbol = "NIFTY"
        ms.trading_enabled = True
        with patch("loats.orchestrator.settings", ms):
            with patch.object(o, "_execute_market_data_update", new_callable=AsyncMock):
                with patch.object(o, "_execute_ta_analysis", new_callable=AsyncMock):
                    with patch.object(
                        o, "_execute_sentiment_analysis", new_callable=AsyncMock
                    ):
                        with patch.object(
                            o, "_execute_volatility_analysis", new_callable=AsyncMock
                        ):
                            with patch.object(
                                o, "_execute_risk_management", new_callable=AsyncMock
                            ):
                                with patch.object(
                                    o, "_execute_cmp_strategy", new_callable=AsyncMock
                                ):
                                    with patch.object(
                                        o,
                                        "_execute_strike_selection",
                                        new_callable=AsyncMock,
                                    ):
                                        with patch(
                                            "loats.orchestrator.datetime"
                                        ) as mdt:
                                            mdt.datetime.now.return_value = (
                                                dt.datetime.now(dt.UTC)
                                            )
                                            mdt.UTC = dt.UTC
                                            await o._execute_trading_cycle()


class TestExecuteMarketDataUpdate:
    @pytest.mark.asyncio
    async def test_basic_update(self):
        import datetime as dt

        o = TradingOrchestrator()
        ms = MagicMock()
        ms.default_symbol = "NIFTY"
        mdb = MagicMock()
        mdb.async_store_quote = AsyncMock()
        mdb.async_store_position = AsyncMock()
        mdb.async_store_funds = AsyncMock()
        qd = {
            "last_price": 24000,
            "open": 23900,
            "high": 24100,
            "low": 23800,
            "close": 24000,
            "volume": 1000,
            "change": 100,
            "change_percent": 0.42,
        }
        with patch("loats.orchestrator.settings", ms):
            with patch("loats.orchestrator.db", mdb):
                with patch.object(
                    o,
                    "_safe_get_quotes",
                    new_callable=AsyncMock,
                    return_value={"data": {"NIFTY": qd}},
                ):
                    with patch.object(
                        o,
                        "_safe_get_position_book",
                        new_callable=AsyncMock,
                        return_value=None,
                    ):
                        with patch.object(
                            o,
                            "_safe_get_funds",
                            new_callable=AsyncMock,
                            return_value=None,
                        ):
                            with patch(
                                "loats.orchestrator._fetch_cached_vix",
                                new_callable=AsyncMock,
                                return_value=14.0,
                            ):
                                with patch("loats.orchestrator.rules_engine"):
                                    with patch("loats.orchestrator.datetime") as mdt:
                                        mdt.datetime.now.return_value = dt.datetime.now(
                                            dt.UTC
                                        )
                                        mdt.UTC = dt.UTC
                                        await o._execute_market_data_update()
        mdb.async_store_quote.assert_called_once()


class TestExecuteRiskManagement:
    @pytest.mark.asyncio
    async def test_circuit_breaker_open(self):
        import datetime as dt

        o = TradingOrchestrator()
        ms = MagicMock()
        ms.default_symbol = "NIFTY"
        with patch("loats.orchestrator.settings", ms):
            with patch("loats.orchestrator.OPENALGO_CIRCUIT_BREAKER") as mcb:
                mcb.get_status.return_value = {"state": "open"}
                with patch("loats.orchestrator.datetime") as mdt:
                    mdt.datetime.now.return_value = dt.datetime.now(dt.UTC)
                    mdt.UTC = dt.UTC
                    await o._execute_risk_management()


class TestValidateRSSFeed:
    @pytest.mark.asyncio
    async def test_invalid_url(self):
        from loats.orchestrator import validate_rss_feed

        assert await validate_rss_feed("not-a-url") is False

    @pytest.mark.asyncio
    async def test_unsupported_scheme(self):
        from loats.orchestrator import validate_rss_feed

        assert await validate_rss_feed("ftp://example.com/feed") is False


class TestModuleFunctions:
    @pytest.mark.asyncio
    async def test_start_orchestrator(self):
        from loats.orchestrator import orchestrator, start_orchestrator

        with patch.object(orchestrator, "start", new_callable=AsyncMock):
            await start_orchestrator()

    @pytest.mark.asyncio
    async def test_stop_orchestrator(self):
        from loats.orchestrator import orchestrator, stop_orchestrator

        with patch.object(orchestrator, "shutdown", new_callable=AsyncMock):
            await stop_orchestrator()

    @pytest.mark.asyncio
    async def test_get_cycle_stats_module(self):
        from loats.orchestrator import get_cycle_stats as gcs
        from loats.orchestrator import orchestrator

        with patch.object(
            orchestrator, "get_cycle_stats", return_value={"cycle_count": 0}
        ):
            r = await gcs()
            assert r == {"cycle_count": 0}
