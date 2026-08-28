import asyncio
import datetime as dt
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from loats.orchestrator import (
    TradingOrchestrator,
    _fetch_cached_vix,
    update_trailing_stops,
    validate_rss_feed,
)


class TestFetchCachedVix:
    @pytest.mark.asyncio
    async def test_cache_hit(self):
        ms = MagicMock(); ms.vix_symbol = 'INDIAVIX'; ms.vix_cache_ttl_seconds = 60
        with patch('loats.orchestrator.settings', ms):
            with patch('loats.orchestrator.cache_manager') as cm:
                cm.get = AsyncMock(return_value='18.5')
                result = await _fetch_cached_vix()
        assert result == 18.5
    @pytest.mark.asyncio
    async def test_cache_miss_fetch(self):
        ms = MagicMock(); ms.vix_symbol = 'INDIAVIX'; ms.vix_cache_ttl_seconds = 60
        with patch('loats.orchestrator.settings', ms):
            with patch('loats.orchestrator.cache_manager') as cm:
                cm.get = AsyncMock(return_value=None); cm.set = AsyncMock()
                with patch('loats.orchestrator.async_client') as ac:
                    ac.get_quotes = AsyncMock(return_value={'data': {'INDIAVIX': {'last_price': '19.2'}}})
                    result = await _fetch_cached_vix()
        assert result == 19.2
    @pytest.mark.asyncio
    async def test_no_data_returns_none(self):
        ms = MagicMock(); ms.vix_symbol = 'INDIAVIX'; ms.vix_cache_ttl_seconds = 60
        with patch('loats.orchestrator.settings', ms):
            with patch('loats.orchestrator.cache_manager') as cm:
                cm.get = AsyncMock(return_value=None)
                with patch('loats.orchestrator.async_client') as ac:
                    ac.get_quotes = AsyncMock(return_value={})
                    result = await _fetch_cached_vix()
        assert result is None
    @pytest.mark.asyncio
    async def test_invalid_cache_falls_through(self):
        ms = MagicMock(); ms.vix_symbol = 'INDIAVIX'; ms.vix_cache_ttl_seconds = 60
        with patch('loats.orchestrator.settings', ms):
            with patch('loats.orchestrator.cache_manager') as cm:
                cm.get = AsyncMock(return_value='bad'); cm.set = AsyncMock()
                with patch('loats.orchestrator.async_client') as ac:
                    ac.get_quotes = AsyncMock(return_value={'data': {'INDIAVIX': {'last_price': 17.0}}})
                    result = await _fetch_cached_vix()
        assert result == 17.0
    @pytest.mark.asyncio
    async def test_exception_returns_none(self):
        ms = MagicMock(); ms.vix_symbol = 'INDIAVIX'
        with patch('loats.orchestrator.settings', ms):
            with patch('loats.orchestrator.cache_manager') as cm:
                cm.get = AsyncMock(side_effect=Exception('down'))
                result = await _fetch_cached_vix()
        assert result is None
    @pytest.mark.asyncio
    async def test_vix_none_last_price(self):
        ms = MagicMock(); ms.vix_symbol = 'INDIAVIX'; ms.vix_cache_ttl_seconds = 60
        with patch('loats.orchestrator.settings', ms):
            with patch('loats.orchestrator.cache_manager') as cm:
                cm.get = AsyncMock(return_value=None); cm.set = AsyncMock()
                with patch('loats.orchestrator.async_client') as ac:
                    ac.get_quotes = AsyncMock(return_value={'data': {'INDIAVIX': {'last_price': None}}})
                    result = await _fetch_cached_vix()
        assert result is None


class TestValidateRSSFeedAdditional:
    @pytest.mark.asyncio
    async def test_non_rss_content(self):
        assert await validate_rss_feed('https://example.com/plain') is False
    @pytest.mark.asyncio
    async def test_connection_error(self):
        with patch('loats.orchestrator.httpx.AsyncClient') as mcc:
            mc = AsyncMock()
            mc.__aenter__ = AsyncMock(return_value=mc)
            mc.__aexit__ = AsyncMock(return_value=False)
            mc.get = AsyncMock(side_effect=Exception('timeout'))
            mcc.return_value = mc
            assert await validate_rss_feed('https://example.com/feed.xml') is False

class TestExecuteSentimentAnalysis:
    @pytest.mark.asyncio
    async def test_no_valid_feeds(self):
        o = TradingOrchestrator()
        ms = MagicMock(); ms.default_symbol = 'NIFTY'; ms.sentiment_threshold = 0.3
        with patch('loats.orchestrator.settings', ms):
            with patch('loats.orchestrator.validate_rss_feed', new_callable=AsyncMock, return_value=False):
                await o._execute_sentiment_analysis()
    @pytest.mark.asyncio
    async def test_with_sentiment_signal(self):
        o = TradingOrchestrator()
        ms = MagicMock(); ms.default_symbol = 'NIFTY'; ms.sentiment_threshold = 0.3
        mock_result = MagicMock()
        mock_result.sentiment_score = 0.7
        mock_result.news_count = 5
        with patch('loats.orchestrator.settings', ms):
            with patch('loats.orchestrator.validate_rss_feed', new_callable=AsyncMock, return_value=True):
                with patch('loats.orchestrator.sentiment') as msent:
                    msent.analyze_symbol_sentiment = AsyncMock(return_value=mock_result)
                    with patch('loats.orchestrator.db') as mdb:
                        mdb.async_create_signal = AsyncMock()
                        await o._execute_sentiment_analysis()
                        mdb.async_create_signal.assert_called_once()
    @pytest.mark.asyncio
    async def test_low_sentiment_no_signal(self):
        o = TradingOrchestrator()
        ms = MagicMock(); ms.default_symbol = 'NIFTY'; ms.sentiment_threshold = 0.9
        mock_result = MagicMock()
        mock_result.sentiment_score = 0.5
        mock_result.news_count = 3
        with patch('loats.orchestrator.settings', ms):
            with patch('loats.orchestrator.validate_rss_feed', new_callable=AsyncMock, return_value=True):
                with patch('loats.orchestrator.sentiment') as msent:
                    msent.analyze_symbol_sentiment = AsyncMock(return_value=mock_result)
                    with patch('loats.orchestrator.db') as mdb:
                        mdb.async_create_signal = AsyncMock()
                        await o._execute_sentiment_analysis()
                        mdb.async_create_signal.assert_not_called()


class TestExecuteTAAnalysis:
    @pytest.mark.asyncio
    async def test_no_history(self):
        o = TradingOrchestrator()
        ms = MagicMock(); ms.default_symbol = 'NIFTY'; ms.default_timeframe = '5minute'
        with patch('loats.orchestrator.settings', ms):
            with patch.object(o, '_safe_get_history', new_callable=AsyncMock, return_value=None):
                await o._execute_ta_analysis()
    @pytest.mark.asyncio
    async def test_with_history_no_signal(self):
        o = TradingOrchestrator()
        ms = MagicMock(); ms.default_symbol = 'NIFTY'; ms.default_timeframe = '5minute'
        ts = dt.datetime(2025,1,1,10,0,tzinfo=dt.UTC)
        raw = {'data': [{'timestamp': ts.isoformat(), 'open': 100, 'high': 101, 'low': 99, 'close': 100, 'volume': 1000}]}
        with patch('loats.orchestrator.settings', ms):
            with patch.object(o, '_safe_get_history', new_callable=AsyncMock, return_value=raw):
                with patch('loats.orchestrator.db') as mdb:
                    mdb.async_store_historical_data = AsyncMock()
                    with patch('loats.orchestrator.technical_analysis') as mta:
                        mta.calculate_indicators.return_value = []
                        with patch.object(o, '_safe_get_quotes', new_callable=AsyncMock, return_value=None):
                            await o._execute_ta_analysis()
    @pytest.mark.asyncio
    async def test_with_signal(self):
        o = TradingOrchestrator()
        ms = MagicMock(); ms.default_symbol = 'NIFTY'; ms.default_timeframe = '5minute'
        ts = dt.datetime(2025,1,1,10,0,tzinfo=dt.UTC)
        raw = {'data': [{'timestamp': ts.isoformat(), 'open': 100, 'high': 101, 'low': 99, 'close': 100, 'volume': 1000}]}
        mi = MagicMock(); mi.name = 'rsi'; mi.value = 70.0
        with patch('loats.orchestrator.settings', ms):
            with patch.object(o, '_safe_get_history', new_callable=AsyncMock, return_value=raw):
                with patch('loats.orchestrator.db') as mdb:
                    mdb.async_store_historical_data = AsyncMock()
                    mdb.async_create_signal = AsyncMock()
                    with patch('loats.orchestrator.technical_analysis') as mta:
                        mta.calculate_indicators.return_value = [mi]
                        mta.generate_signal.return_value = ('BUY', 0.8)
                        with patch.object(o, '_safe_get_quotes', new_callable=AsyncMock, return_value={'data': {'NIFTY': {'last_price': 24100}}}):
                            await o._execute_ta_analysis()
                            mdb.async_create_signal.assert_called_once()

class TestRiskManagementAdditional:
    @pytest.mark.asyncio
    async def test_position_limit_exceeded(self):
        o = TradingOrchestrator()
        ms = MagicMock(); ms.default_symbol = 'NIFTY'; ms.max_position_size = 50
        mock_pos = MagicMock(); mock_pos.quantity = 100
        with patch('loats.orchestrator.settings', ms):
            with patch('loats.orchestrator.OPENALGO_CIRCUIT_BREAKER') as mcb:
                mcb.get_status.return_value = {'state': 'closed'}
                with patch('loats.orchestrator.db') as mdb:
                    mdb.get_position = MagicMock(return_value=mock_pos)
                    mdb.get_latest_funds = MagicMock(return_value=None)
                    with patch('loats.orchestrator.alerts') as ma:
                        ma.send_alert = AsyncMock()
                        with patch('loats.orchestrator.datetime') as mdt:
                            mdt.datetime.now.return_value = dt.datetime.now(dt.UTC)
                            mdt.UTC = dt.UTC
                            await o._execute_risk_management()
                            ma.send_alert.assert_called_once()
    @pytest.mark.asyncio
    async def test_high_margin_utilization(self):
        o = TradingOrchestrator()
        ms = MagicMock(); ms.default_symbol = 'NIFTY'; ms.max_margin_utilization = 0.8
        mock_funds = MagicMock(); mock_funds.available_margin = 100000.0; mock_funds.utilized_margin = 90000.0
        with patch('loats.orchestrator.settings', ms):
            with patch('loats.orchestrator.OPENALGO_CIRCUIT_BREAKER') as mcb:
                mcb.get_status.return_value = {'state': 'closed'}
                with patch('loats.orchestrator.db') as mdb:
                    mdb.get_position = MagicMock(return_value=None)
                    mdb.get_latest_funds = MagicMock(return_value=mock_funds)
                    with patch('loats.orchestrator.alerts') as ma:
                        ma.send_alert = AsyncMock()
                        with patch('loats.orchestrator.datetime') as mdt:
                            mdt.datetime.now.return_value = dt.datetime.now(dt.UTC)
                            mdt.UTC = dt.UTC
                            await o._execute_risk_management()
                            ma.send_alert.assert_called_once()
    @pytest.mark.asyncio
    async def test_zero_available_margin(self):
        o = TradingOrchestrator()
        ms = MagicMock(); ms.default_symbol = 'NIFTY'; ms.max_margin_utilization = 0.8
        mock_funds = MagicMock(); mock_funds.available_margin = 0.0; mock_funds.utilized_margin = 50000.0
        with patch('loats.orchestrator.settings', ms):
            with patch('loats.orchestrator.OPENALGO_CIRCUIT_BREAKER') as mcb:
                mcb.get_status.return_value = {'state': 'closed'}
                with patch('loats.orchestrator.db') as mdb:
                    mdb.get_position = MagicMock(return_value=None)
                    mdb.get_latest_funds = MagicMock(return_value=mock_funds)
                    with patch('loats.orchestrator.datetime') as mdt:
                        mdt.datetime.now.return_value = dt.datetime.now(dt.UTC)
                        mdt.UTC = dt.UTC
                        await o._execute_risk_management()


class TestTradingCycleException:
    @pytest.mark.asyncio
    async def test_exception_in_cycle(self):
        o = TradingOrchestrator()
        ms = MagicMock(); ms.default_symbol = 'NIFTY'; ms.trading_enabled = True
        with patch('loats.orchestrator.settings', ms):
            with patch.object(o, '_execute_market_data_update', new_callable=AsyncMock, side_effect=RuntimeError('boom')):
                with patch.object(o, '_execute_ta_analysis', new_callable=AsyncMock):
                    with patch.object(o, '_execute_sentiment_analysis', new_callable=AsyncMock):
                        with patch.object(o, '_execute_volatility_analysis', new_callable=AsyncMock):
                            with patch('loats.rules.rules_engine') as mre:
                                mre.is_trading_allowed.return_value = True
                                with patch('loats.orchestrator.record_cycle_time'):
                                    with pytest.raises(RuntimeError, match='boom'):
                                        await o._execute_trading_cycle()
    @pytest.mark.asyncio
    async def test_trading_not_allowed(self):
        o = TradingOrchestrator()
        ms = MagicMock(); ms.default_symbol = 'NIFTY'
        with patch('loats.orchestrator.settings', ms):
            with patch.object(o, '_execute_market_data_update', new_callable=AsyncMock):
                with patch.object(o, '_execute_ta_analysis', new_callable=AsyncMock):
                    with patch.object(o, '_execute_sentiment_analysis', new_callable=AsyncMock):
                        with patch.object(o, '_execute_volatility_analysis', new_callable=AsyncMock):
                            with patch.object(o, '_execute_risk_management', new_callable=AsyncMock):
                                with patch('loats.rules.rules_engine') as mre:
                                    mre.is_trading_allowed.return_value = False
                                    mre.session_state.value = 'CLOSING'
                                    with patch('loats.orchestrator.record_cycle_time'):
                                        await o._execute_trading_cycle()

class TestExecuteStrikeSelection:
    @pytest.mark.asyncio
    async def test_empty_chain(self):
        o = TradingOrchestrator()
        result = await o._execute_strike_selection([])
        assert result == []
    @pytest.mark.asyncio
    async def test_normal_selection(self):
        o = TradingOrchestrator()
        from loats.models import OptionContract
        chain = [OptionContract(symbol=f'NIFTY24000{i}CE', strike_price=24000+i*100, expiry=dt.datetime(2025,2,1), option_type='CE', last_price=100.0, open_interest=1000, volume=500) for i in range(5)]
        with patch('loats.orchestrator.select_strikes', new_callable=AsyncMock, return_value=[24000.0, 24100.0, 24200.0]):
            with patch('loats.orchestrator.datetime') as mdt:
                mdt.datetime.now.return_value = dt.datetime.now(dt.UTC)
                mdt.UTC = dt.UTC
                result = await o._execute_strike_selection(chain)
        assert result == [24000.0, 24100.0, 24200.0]
    @pytest.mark.asyncio
    async def test_timeout_fallback(self):
        o = TradingOrchestrator()
        from loats.models import OptionContract
        chain = [OptionContract(symbol=f'NIFTY24000{i}CE', strike_price=24000+i*100, expiry=dt.datetime(2025,2,1), option_type='CE', last_price=100.0, open_interest=1000, volume=500) for i in range(10)]
        async def slow_select(**kw): await asyncio.sleep(1)
        with patch('loats.orchestrator.select_strikes', side_effect=slow_select):
            with patch('loats.orchestrator.datetime') as mdt:
                mdt.datetime.now.return_value = dt.datetime.now(dt.UTC)
                mdt.UTC = dt.UTC
                result = await o._execute_strike_selection(chain)
        assert len(result) > 0


class TestShutdownWithTask:
    @pytest.mark.asyncio
    async def test_shutdown_cancels_task(self):
        o = TradingOrchestrator()
        o.running = True
        async def forever():
            await asyncio.sleep(100)
        o._cycle_task = asyncio.create_task(forever())
        await o.shutdown()
        assert o.running is False


class TestSafeGetterExceptions:
    @pytest.mark.asyncio
    async def test_quotes_failure(self):
        o = TradingOrchestrator()
        with patch('loats.orchestrator.async_client') as mc:
            mc.get_quotes = AsyncMock(side_effect=Exception('fail'))
            result = await o._safe_get_quotes(['NIFTY'])
        assert result is None
    @pytest.mark.asyncio
    async def test_position_book_failure(self):
        o = TradingOrchestrator()
        with patch('loats.orchestrator.async_client') as mc:
            mc.get_position_book = AsyncMock(side_effect=Exception('fail'))
            result = await o._safe_get_position_book()
        assert result is None
    @pytest.mark.asyncio
    async def test_funds_failure(self):
        o = TradingOrchestrator()
        with patch('loats.orchestrator.async_client') as mc:
            mc.get_funds = AsyncMock(side_effect=Exception('fail'))
            result = await o._safe_get_funds()
        assert result is None


class TestMarketDataUpdateWithPositions:
    @pytest.mark.asyncio
    async def test_with_positions_and_funds(self):
        o = TradingOrchestrator()
        ms = MagicMock(); ms.default_symbol = 'NIFTY'
        mdb = MagicMock()
        mdb.async_store_quote = AsyncMock()
        mdb.async_store_position = AsyncMock()
        mdb.async_store_funds = AsyncMock()
        qd = {'last_price': 24000, 'open': 23900, 'high': 24100, 'low': 23800, 'close': 24000, 'volume': 1000, 'change': 100, 'change_percent': 0.42}
        pos_data = {'data': [{'symbol': 'NIFTY', 'quantity': 100, 'average_price': 23900, 'last_price': 24000, 'pnl': 10000, 'product_type': 'MIS'}]}
        funds_data = {'data': {'available_cash': 50000, 'utilized_margin': 10000, 'available_margin': 40000, 'total_equity': 100000}}
        with patch('loats.orchestrator.settings', ms):
            with patch('loats.orchestrator.db', mdb):
                with patch.object(o, '_safe_get_quotes', new_callable=AsyncMock, return_value={'data': {'NIFTY': qd}}):
                    with patch.object(o, '_safe_get_position_book', new_callable=AsyncMock, return_value=pos_data):
                        with patch.object(o, '_safe_get_funds', new_callable=AsyncMock, return_value=funds_data):
                            with patch('loats.orchestrator._fetch_cached_vix', new_callable=AsyncMock, return_value=14.0):
                                with patch('loats.orchestrator.rules_engine'):
                                    with patch('loats.orchestrator.datetime') as mdt:
                                        mdt.datetime.now.return_value = dt.datetime.now(dt.UTC)
                                        mdt.UTC = dt.UTC
                                        await o._execute_market_data_update()
        mdb.async_store_position.assert_called_once()
        mdb.async_store_funds.assert_called_once()


class TestUpdateTrailingStops:
    @pytest.mark.asyncio
    async def test_no_position_data(self):
        with patch('loats.orchestrator.async_client') as ac:
            ac.get_position_book = AsyncMock(return_value={})
            await update_trailing_stops()
    @pytest.mark.asyncio
    async def test_empty_positions(self):
        with patch('loats.orchestrator.async_client') as ac:
            ac.get_position_book = AsyncMock(return_value={'data': []})
            await update_trailing_stops()
    @pytest.mark.asyncio
    async def test_no_trailing_config(self):
        mock_pos = MagicMock(); mock_pos.trailing_config = None
        with patch('loats.orchestrator.async_client') as ac:
            ac.get_position_book = AsyncMock(return_value={'data': [{'symbol': 'NIFTY'}]})
            with patch('loats.orchestrator.db') as mdb:
                mdb.get_position = MagicMock(return_value=mock_pos)
                await update_trailing_stops()
    @pytest.mark.asyncio
    async def test_with_modification(self):
        mock_pos = MagicMock()
        mock_pos.trailing_config = {'trigger_price': 23800, 'type': 'percentage', 'trail_percent': 1.0}
        mock_pos.order_id = 'ORD123'
        with patch('loats.orchestrator.async_client') as ac:
            ac.get_position_book = AsyncMock(return_value={'data': [{'symbol': 'NIFTY'}]})
            ac.get_quotes = AsyncMock(return_value={'data': {'NIFTY': {'last_price': 24100}}})
            ac.modify_order = AsyncMock()
            with patch('loats.orchestrator.db') as mdb:
                mdb.get_position = MagicMock(return_value=mock_pos)
                mdb.async_record_ratchet_event = AsyncMock()
                mdb.store_position = MagicMock()
                with patch('loats.trailing_stop.trailing_stop_engine') as mtse:
                    mtse.update_trailing_stop.return_value = ({'trigger_price': 23900}, True)
                    with patch('loats.rules.rules_engine') as mre:
                        mre.get_modification_counter.return_value = 0
                        mre.increment_modification_counter = MagicMock()
                        await update_trailing_stops()
                        ac.modify_order.assert_called_once()
    @pytest.mark.asyncio
    async def test_no_quote_data(self):
        mock_pos = MagicMock()
        mock_pos.trailing_config = {'trigger_price': 23800, 'type': 'percentage', 'trail_percent': 1.0}
        with patch('loats.orchestrator.async_client') as ac:
            ac.get_position_book = AsyncMock(return_value={'data': [{'symbol': 'NIFTY'}]})
            ac.get_quotes = AsyncMock(return_value=None)
            with patch('loats.orchestrator.db') as mdb:
                mdb.get_position = MagicMock(return_value=mock_pos)
                await update_trailing_stops()

class TestStart:
    @pytest.mark.asyncio
    async def test_start_creates_task(self):
        o = TradingOrchestrator()
        with patch.object(o, '_run_cycle_loop', new_callable=AsyncMock):
            await o.start()
        assert o.running is True
        assert o._cycle_task is not None
    @pytest.mark.asyncio
    async def test_start_already_running(self):
        o = TradingOrchestrator()
        o.running = True
        o._cycle_task = asyncio.create_task(asyncio.sleep(10))
        with patch.object(o, '_run_cycle_loop', new_callable=AsyncMock) as m:
            await o.start()
            m.assert_not_called()


class TestRunCycleLoopError:
    @pytest.mark.asyncio
    async def test_error_sends_alert(self):
        o = TradingOrchestrator()
        call_count = 0
        async def boom():
            nonlocal call_count
            call_count += 1
            if call_count == 1: raise RuntimeError('err')
            o._shutdown_event.set()
        with patch.object(o, '_execute_trading_cycle', side_effect=boom):
            with patch.object(o, '_check_kill_switch', new_callable=AsyncMock):
                with patch('loats.orchestrator.alerts') as ma:
                    ma.send_system_alert = AsyncMock()
                    await o._run_cycle_loop()
                    ma.send_system_alert.assert_called_once()


class TestValidateRSSFeedHTTP:
    @pytest.mark.asyncio
    async def test_404_status(self):
        with patch('loats.orchestrator.httpx.AsyncClient') as mcc:
            mc = AsyncMock()
            mc.__aenter__ = AsyncMock(return_value=mc)
            mc.__aexit__ = AsyncMock(return_value=False)
            mock_resp = MagicMock(); mock_resp.status_code = 404
            mc.get = AsyncMock(return_value=mock_resp)
            mcc.return_value = mc
            assert await validate_rss_feed('https://example.com/feed.xml') is False
    @pytest.mark.asyncio
    async def test_xml_content_type(self):
        with patch('loats.orchestrator.httpx.AsyncClient') as mcc:
            mc = AsyncMock()
            mc.__aenter__ = AsyncMock(return_value=mc)
            mc.__aexit__ = AsyncMock(return_value=False)
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.headers = {'content-type': 'application/xml'}
            mc.get = AsyncMock(return_value=mock_resp)
            mcc.return_value = mc
            assert await validate_rss_feed('https://example.com/feed.xml') is True
    @pytest.mark.asyncio
    async def test_rss_tag_in_content(self):
        with patch('loats.orchestrator.httpx.AsyncClient') as mcc:
            mc = AsyncMock()
            mc.__aenter__ = AsyncMock(return_value=mc)
            mc.__aexit__ = AsyncMock(return_value=False)
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.headers = {'content-type': 'text/html'}
            mock_resp.text = '<html><rss></rss></html>'
            mc.get = AsyncMock(return_value=mock_resp)
            mcc.return_value = mc
            assert await validate_rss_feed('https://example.com/feed.xml') is True


class TestSentimentSellSignal:
    @pytest.mark.asyncio
    async def test_sell_signal(self):
        o = TradingOrchestrator()
        ms = MagicMock(); ms.default_symbol = 'NIFTY'; ms.sentiment_threshold = 0.3
        mock_result = MagicMock()
        mock_result.sentiment_score = -0.7
        mock_result.news_count = 3
        with patch('loats.orchestrator.settings', ms):
            with patch('loats.orchestrator.validate_rss_feed', new_callable=AsyncMock, return_value=True):
                with patch('loats.orchestrator.sentiment') as msent:
                    msent.analyze_symbol_sentiment = AsyncMock(return_value=mock_result)
                    with patch('loats.orchestrator.db') as mdb:
                        mdb.async_create_signal = AsyncMock()
                        await o._execute_sentiment_analysis()
                        mdb.async_create_signal.assert_called_once()

