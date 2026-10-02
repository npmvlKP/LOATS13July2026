"""Tests for the 02Oct2026 operator-mandate market-status wave.

Covers: deterministic regime classification (mandate [2]), instrument
selection (mandate [3]), session activation semantics (mandate [1]),
per-segment quote routing, and the backward-compatibility surface of the
extended OpenAlgo client (get_quotes ``exchanges``).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from loats.market_status import (
    REGIME_VOLUME_VETO_RATIO,
    SEGMENT_EXCHANGES,
    SEGMENT_SYMBOLS,
    MarketRegime,
    MarketStatusReport,
    MarketStatusService,
    SegmentStatus,
)

MODULE = "loats.market_status"


def _status(
    segment: str = "NSE",
    regime: MarketRegime = MarketRegime.BULL,
    change_pct: float | None = 0.5,
    sentiment: float | None = 0.3,
    volume_ratio: float | None = 1.2,
    instruments: dict[str, object] | None = None,
) -> SegmentStatus:
    from loats.market_status import InstrumentMetrics

    if instruments is None:
        instruments = {"NIFTY": InstrumentMetrics(change_pct=change_pct)}
    return SegmentStatus(
        segment=segment,
        session_open=True,
        session_window="09:15-15:30",
        availability="available",
        change_pct=change_pct,
        sentiment_score=sentiment,
        volume_ratio=volume_ratio,
        regime=regime,
        instruments=instruments,  # type: ignore[arg-type]
    )


class TestClassifyRegime:
    """Deterministic BULL/BEAR/NEUTRAL classification (mandate [2])."""

    def test_no_price_data_is_neutral(self):
        regime, reason = MarketStatusService._classify_regime(None, 0.5, 1.5)
        assert regime is MarketRegime.NEUTRAL
        assert "no price data" in reason

    def test_volume_veto_forces_neutral(self):
        regime, reason = MarketStatusService._classify_regime(1.0, 0.4, 0.5)
        assert regime is MarketRegime.NEUTRAL
        assert "volume participation" in reason

    def test_volume_none_skips_veto(self):
        regime, _ = MarketStatusService._classify_regime(1.0, 0.4, None)
        assert regime is MarketRegime.BULL

    def test_flat_band_neutral(self):
        regime, reason = MarketStatusService._classify_regime(0.05, 0.1, 1.2)
        assert regime is MarketRegime.NEUTRAL
        assert "flat band" in reason

    def test_flat_price_strong_sentiment_stays_neutral(self):
        # Price-confirmation rule: sentiment alone never flips the regime;
        # a sub-threshold move with strong sentiment stays NEUTRAL.
        regime, _ = MarketStatusService._classify_regime(0.05, 0.4, 1.2)
        assert regime is MarketRegime.NEUTRAL

    def test_bull_requires_sentiment_agreement(self):
        # +1% move but sentiment negative: disagreement -> NEUTRAL.
        regime, reason = MarketStatusService._classify_regime(1.0, -0.3, 1.2)
        assert regime is MarketRegime.NEUTRAL
        assert "disagree" in reason

    def test_bull_without_sentiment_is_neutral(self):
        regime, reason = MarketStatusService._classify_regime(1.0, None, 1.2)
        assert regime is MarketRegime.NEUTRAL
        assert "without sentiment data" in reason

    def test_bull_agreement(self):
        regime, reason = MarketStatusService._classify_regime(0.5, 0.3, 1.2)
        assert regime is MarketRegime.BULL
        assert "up-move" in reason

    def test_strong_bull(self):
        regime, _ = MarketStatusService._classify_regime(0.7, 0.4, 1.2)
        assert regime is MarketRegime.BULL
        assert "strong" in _

    def test_bear_agreement(self):
        regime, _ = MarketStatusService._classify_regime(-0.5, -0.3, 1.2)
        assert regime is MarketRegime.BEAR

    def test_strong_bear(self):
        regime, reason = MarketStatusService._classify_regime(-0.7, -0.4, 1.2)
        assert regime is MarketRegime.BEAR
        assert "strong" in reason

    def test_directional_price_negative_sentiment_mirrors(self):
        # -1% move with positive sentiment -> disagreement NEUTRAL.
        regime, _ = MarketStatusService._classify_regime(-1.0, 0.3, 1.2)
        assert regime is MarketRegime.NEUTRAL


class TestScoreAndSelect:
    """Mandate [3]: candidate ranking."""

    def test_score_weights(self):
        score = MarketStatusService.score_instrument(2.0, 1.0, 2.0)
        assert score == pytest.approx(0.5 * 1.0 + 0.3 * 1.0 + 0.2 * 1.0)

    def test_score_missing_legs_contribute_zero(self):
        assert MarketStatusService.score_instrument(None, None, None) == 0.0

    def test_score_volume_cap(self):
        # Above the 2x cap the volume leg saturates.
        assert MarketStatusService.score_instrument(0.0, 0.0, 5.0) == pytest.approx(0.2)

    def test_select_excludes_neutral(self):
        statuses = [_status(regime=MarketRegime.NEUTRAL)]
        assert MarketStatusService.select_instruments(statuses) == []

    def test_select_excludes_volume_veto(self):
        statuses = [
            _status(
                regime=MarketRegime.BULL,
                volume_ratio=REGIME_VOLUME_VETO_RATIO - 0.1,
            )
        ]
        assert MarketStatusService.select_instruments(statuses) == []

    def test_select_skips_priceless_instruments(self):
        from loats.market_status import InstrumentMetrics

        statuses = [_status(instruments={"GOLD": InstrumentMetrics(change_pct=None)})]
        assert MarketStatusService.select_instruments(statuses) == []

    def test_select_ranks_within_segment(self):
        from loats.market_status import InstrumentMetrics

        statuses = [
            _status(
                segment="MCX",
                regime=MarketRegime.BULL,
                sentiment=0.4,
                instruments={
                    "GOLD": InstrumentMetrics(change_pct=0.2, volume_ratio=1.5),
                    "CRUDEOIL": InstrumentMetrics(change_pct=1.5, volume_ratio=1.5),
                },
            )
        ]
        opps = MarketStatusService.select_instruments(statuses)
        assert [o.symbol for o in opps] == ["CRUDEOIL", "GOLD"]
        assert opps[0].score > opps[1].score

    def test_select_per_market_cap(self):
        from loats.market_status import InstrumentMetrics

        instruments = {f"S{i}": InstrumentMetrics(change_pct=0.5) for i in range(5)}
        statuses = [_status(segment="MCX", instruments=instruments)]
        opps = MarketStatusService.select_instruments(statuses, per_market=2)
        assert len(opps) == 2


class TestActivationSemantics:
    """Mandate [1]: announce-once, delivery-confirmed announce state."""

    def _service(self) -> MarketStatusService:
        return MarketStatusService()

    @pytest.mark.asyncio
    async def test_announces_on_open_transition(self):
        svc = self._service()
        report = MarketStatusReport(
            timestamp="t", any_session_open=True, segments=[_status()]
        )
        with (
            patch.object(svc, "snapshot", new=AsyncMock(return_value=report)),
            patch(
                f"{MODULE}.alerts.send_system_alert",
                new=AsyncMock(return_value=True),
            ) as send,
        ):
            out = await svc.run_activation_check()
        assert out is not None
        send.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_no_announce_when_all_shut(self):
        svc = self._service()
        shut = _status()
        shut.session_open = False
        report = MarketStatusReport(
            timestamp="t", any_session_open=False, segments=[shut]
        )
        with (
            patch.object(svc, "snapshot", new=AsyncMock(return_value=report)),
            patch(
                f"{MODULE}.alerts.send_system_alert",
                new=AsyncMock(return_value=True),
            ) as send,
        ):
            out = await svc.run_activation_check()
        assert out is report
        send.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_announces_once_per_segment(self):
        svc = self._service()
        report = MarketStatusReport(
            timestamp="t", any_session_open=True, segments=[_status()]
        )
        send = AsyncMock(return_value=True)
        with (
            patch.object(svc, "snapshot", new=AsyncMock(return_value=report)),
            patch(f"{MODULE}.alerts.send_system_alert", new=send),
        ):
            first = await svc.run_activation_check()
            second = await svc.run_activation_check()
        assert first is not None
        # Second tick: nothing new to announce, no message sent again.
        assert second is report
        send.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_failed_delivery_retries_next_tick(self):
        svc = self._service()
        report = MarketStatusReport(
            timestamp="t", any_session_open=True, segments=[_status()]
        )
        send = AsyncMock(return_value=False)
        with (
            patch.object(svc, "snapshot", new=AsyncMock(return_value=report)),
            patch(f"{MODULE}.alerts.send_system_alert", new=send),
        ):
            first = await svc.run_activation_check()
            # Delivered=False -> NOT marked announced -> retry announces.
            second = await svc.run_activation_check()
        # v2 contract: the service returns the report; delivery success is
        # signalled by the announced-set state, not the return value.
        assert first is report
        assert "NSE" not in svc._announced_open
        assert second is report
        assert send.await_count == 2

    def test_telegram_text_escapes_external_data(self):
        status = _status()
        status.availability = "unavailable: <b>evil</b>"
        status.regime_reason = "x <script>alert(1)</script>"
        report = MarketStatusReport(
            timestamp="t", any_session_open=True, segments=[status]
        )
        text = report.telegram_text()
        assert "&lt;b&gt;evil&lt;/b&gt;" in text
        assert "&lt;script&gt;" in text
        assert "<b>evil</b>" not in text


class TestSegmentAssembly:
    """Snapshot assembly: phases, routing, degradation."""

    @pytest.mark.asyncio
    async def test_segment_status_outside_session_short_circuits(self):
        svc = MarketStatusService()
        with patch(
            f"{MODULE}.MarketStatusService._session_phase",
            return_value="halted",
        ):
            status = await svc._segment_status("NSE", svc._now())
        assert status.availability == "halted"
        assert status.regime is MarketRegime.NEUTRAL
        assert status.instruments == {}

    @pytest.mark.asyncio
    async def test_quote_failure_degrades_leg(self):
        svc = MarketStatusService()
        with (
            patch(
                f"{MODULE}.MarketStatusService._session_phase",
                return_value="open",
            ),
            patch.object(
                svc,
                "_safe_get_quotes",
                new=AsyncMock(side_effect=RuntimeError("broker down")),
            ),
        ):
            status = await svc._segment_status("NSE", svc._now())
        assert status.availability == "unavailable: no quote data"
        assert status.regime_reason == "unavailable: no quote data"

    @pytest.mark.asyncio
    async def test_sentiment_failure_degrades_to_none(self):
        svc = MarketStatusService()
        quotes = {
            "data": {
                "NIFTY": {"last_price": 22421.95, "close": 22620.45},
            }
        }
        with (
            patch(
                f"{MODULE}.MarketStatusService._session_phase",
                return_value="open",
            ),
            patch.object(
                svc,
                "_safe_get_quotes",
                new=AsyncMock(return_value=quotes),
            ),
            patch.object(
                svc,
                "_safe_sentiment",
                new=AsyncMock(return_value=None),
            ),
        ):
            status = await svc._segment_status("NSE", svc._now())
        assert status.availability == "available"
        assert status.sentiment_score is None
        assert status.regime is MarketRegime.NEUTRAL
        assert "NIFTY" in status.instruments

    @pytest.mark.asyncio
    async def test_per_segment_exchange_routing(self):
        """MCX symbols must be quoted on MCX, not the NSE default."""
        svc = MarketStatusService()
        quotes = {
            "data": {
                "GOLD": {
                    "ltp": 50000.0,
                    "prev_close": 49500.0,
                    "volume": 100,
                    "average_volume": 200,
                },
            }
        }
        with (
            patch(
                f"{MODULE}.MarketStatusService._session_phase",
                return_value="open",
            ),
            patch.object(
                svc,
                "_safe_get_quotes",
                new=AsyncMock(return_value=quotes),
            ) as gq,
            patch.object(svc, "_safe_sentiment", new=AsyncMock(return_value=0.0)),
        ):
            status = await svc._segment_status("MCX", svc._now())
        symbols_arg, exchanges_arg = gq.await_args.args
        assert symbols_arg == ["GOLD", "SILVER", "CRUDEOIL"]
        assert exchanges_arg == ["MCX", "MCX", "MCX"]
        # volume_ratio wired: 100/200 = 0.5 -> participation veto holds.
        assert status.volume_ratio == pytest.approx(0.5)

    @pytest.mark.asyncio
    async def test_primary_symbol_drives_segment_regime(self):
        svc = MarketStatusService()
        quotes = {
            "data": {
                "NIFTY": {"last_price": 22421.95, "close": 22620.45},
            }
        }
        with (
            patch(
                f"{MODULE}.MarketStatusService._session_phase",
                return_value="open",
            ),
            patch.object(
                svc,
                "_safe_get_quotes",
                new=AsyncMock(return_value=quotes),
            ),
            patch.object(svc, "_safe_sentiment", new=AsyncMock(return_value=0.2)),
        ):
            status = await svc._segment_status("NSE", svc._now())
        assert status.ltp == pytest.approx(22421.95)
        # (22421.95 - 22620.45)/22620.45 = -0.878% -> flat band NEUTRAL.
        assert status.change_pct == pytest.approx(-0.8777, abs=1e-3)
        assert status.regime is MarketRegime.NEUTRAL

    def test_session_phase_holiday_weekend(self):
        import datetime

        svc = MarketStatusService()
        # 2026-10-03 is a Saturday.
        sat = datetime.datetime(2026, 10, 3, 10, 0)
        assert svc._session_phase("NSE", sat) == "halted"
        # 2026-10-02 is an NSE + MCX + CDS holiday.
        hol = datetime.datetime(2026, 10, 2, 10, 0)
        assert svc._session_phase("NSE", hol) == "halted"
        assert svc._session_phase("MCX", hol) == "halted"

    def test_segment_exchanges_routing_table(self):
        assert SEGMENT_EXCHANGES["NSE"] == "NSE_INDEX"
        assert SEGMENT_EXCHANGES["MCX"] == "MCX"
        assert SEGMENT_EXCHANGES["CDS"] == "CDS"

    def test_segment_symbols_pool(self):
        assert SEGMENT_SYMBOLS["NSE"] == ("NIFTY",)
        assert len(SEGMENT_SYMBOLS["MCX"]) == 3
        assert SEGMENT_SYMBOLS["CDS"] == ("USDINR",)


class TestOpenAlgoQuotesCompat:
    """Extended client surface: explicit exchanges, default unchanged."""

    def test_sync_default_shape_unchanged(self):
        from loats.openalgo import OpenAlgoClient, _quote_request_shape

        assert _quote_request_shape("NIFTY") == {
            "exchange": "NSE_INDEX",
            "symbol": "NIFTY",
        }
        assert _quote_request_shape("RELIANCE") == {
            "exchange": "NSE",
            "symbol": "RELIANCE",
        }
        client = OpenAlgoClient(api_key="k")
        with patch.object(client, "_request", return_value={"data": {}}) as req:
            client.get_quotes(["NIFTY"])
        body = req.call_args.kwargs["json"]
        assert body["exchange"] == "NSE_INDEX"

    def test_sync_explicit_exchange_wins(self):
        from loats.openalgo import OpenAlgoClient, _quote_request_shape

        assert _quote_request_shape("GOLD", "MCX") == {
            "exchange": "MCX",
            "symbol": "GOLD",
        }
        client = OpenAlgoClient(api_key="k")
        with patch.object(client, "_request", return_value={"data": {}}) as req:
            client.get_quotes(["GOLD"], exchanges=["MCX"])
        body = req.call_args.kwargs["json"]
        assert body["exchange"] == "MCX"

    def test_sync_exchanges_must_align(self):
        from loats.openalgo import OpenAlgoClient

        client = OpenAlgoClient(api_key="k")
        with pytest.raises(ValueError):
            client.get_quotes(["A", "B"], exchanges=["MCX"])

    @pytest.mark.asyncio
    async def test_async_explicit_exchange_reaches_request(self):
        from loats.openalgo import AsyncOpenAlgoClient

        client = AsyncOpenAlgoClient(api_key="k")
        with (
            patch.object(
                client, "_request", new=AsyncMock(return_value={"data": {}})
            ) as req,
            patch("loats.openalgo.cache_manager") as cache,
        ):
            cache.get = AsyncMock(return_value=None)
            cache.set = AsyncMock(return_value=True)
            await client.get_quotes(["USDINR"], exchanges=["CDS"])
        body = req.await_args.kwargs["json"]
        assert body["exchange"] == "CDS"

    @pytest.mark.asyncio
    async def test_async_default_cache_key_backward_compatible(self):
        """A no-exchange call must hit the same digest family as before
        (sorted-symbols prefix) so a deployed cache is not forked."""
        import hashlib

        from loats.openalgo import AsyncOpenAlgoClient

        client = AsyncOpenAlgoClient(api_key="k")
        symbols = ["B", "A"]
        expected = hashlib.sha256(b"A,B").hexdigest()
        with (
            patch.object(
                client, "_request", new=AsyncMock(return_value={"data": {}})
            ) as req,
            patch("loats.openalgo.cache_manager") as cache,
        ):
            cache.get = AsyncMock(return_value=None)
            cache.set = AsyncMock(return_value=True)
            await client.get_quotes(symbols)
        assert req.await_count == 2
        # The cache key must be quotes:<sha256("A,B|")> -- same symbols
        # prefix the legacy key used, plus the (empty) exchange suffix.
        cache.set.assert_awaited_once()
        key = cache.set.await_args.args[0]
        assert key == f"quotes:{expected}"


class TestReportModels:
    def test_summary_line(self):
        report = MarketStatusReport(
            timestamp="t",
            any_session_open=True,
            segments=[_status()],
        )
        line = report.summary_line()
        assert "NSE=BULL(open,available)" in line

    def test_instrument_metrics_model(self):
        from loats.market_status import InstrumentMetrics

        m = InstrumentMetrics(ltp=1.0, prev_close=2.0)
        assert m.change_pct is None
        assert m.volume_ratio is None
