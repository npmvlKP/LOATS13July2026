"""Market session activation, per-market status, and regime classification.

02Oct2026 operator mandate wave (three requirements):

1. Every enabled market (NSE / MCX / CDS) working day, the running system
   must activate itself per segment session and communicate login and
   market-data availability through the Telegram bot.
2. Each market's status must be reported as BULL / BEAR / NEUTRAL.
3. Using sentiment analysis + volume analysis + market status, the system
   must identify candidate trading instruments per market.

Design constraints honored from the existing architecture:

- Signal production stays with the orchestrator (F8-H-03): this module
  REPORTS regime and candidates -- it never emits tradeable Signal rows
  and never routes decisions. The Telegram cooldown in ``alerts`` keeps
  report cadence safe.
- Session truth lives in :mod:`loats.segments` (per-segment sessions,
  holiday calendars, ENABLED_SEGMENTS gating) -- imported, not duplicated.
- Broker access goes through the shared ``async_client`` with per-segment
  exchange routing (MCX/CDS symbols need an explicit ``exchange`` on
  /quotes; the NSE benchmark is an index and routes to ``NSE_INDEX``).
- Sentiment analysis reuses the production ``SentimentAnalyzer`` ensemble
  (VADER over the validated RSS feed set) as a MARKET-WIDE sentiment
  proxy: one ensemble score per segment, shared by that segment's
  instruments.
- Any external-data failure degrades that one leg to None and the report
  still ships -- availability reporting must not die with a data source.

Regime classification is deterministic and documented in
:meth:`MarketStatusService._classify_regime` (price change, sentiment
agreement, volume-participation veto).
"""

from __future__ import annotations

import datetime
import html
from enum import StrEnum
from typing import Any
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field

from .alerts import alerts
from .lazy_settings import LazySettings
from .loats_logging import get_logger
from .segments import SEGMENT_SESSIONS, enabled_segments, is_segment_open
from .utils.resilience import openalgo_circuit_breaker_retry_async

settings: Any = LazySettings()  # LazySettings.__getattr__ proxies to Settings()
logger = get_logger(__name__)


class MarketRegime(StrEnum):
    """Per-market regime classification (mandate [2])."""

    BULL = "BULL"
    BEAR = "BEAR"
    NEUTRAL = "NEUTRAL"


#: Regime classification thresholds. Price change is % vs previous close;
#: sentiment is the ensemble score in [-1, +1]. Bands are deliberately
#: symmetric; the neutral band excludes noise.
REGIME_FLAT_PCT = 0.10  # |change| below this % is flat
REGIME_TREND_PCT = 0.10  # |change| at/above this % is directional
REGIME_FLAT_SENTIMENT = 0.15  # |sentiment| below this is neutral
REGIME_STRONG_PCT = 0.60  # |change| at/above this marks a strong regime
REGIME_STRONG_SENTIMENT = 0.35  # |sentiment| at/above this marks strength
#: Volume participation veto: current volume below this fraction of the
#: average volume means the move lacks participation -- classify NEUTRAL.
REGIME_VOLUME_VETO_RATIO = 0.8

#: Per-segment regime-proxy symbols. These are NOT trade recommendations:
#: each is the segment's most liquid benchmark whose quote stands in for
#: the segment-wide regime until per-segment strategy engines land (the
#: MCX/CDS dev wave). Spellings match the OpenAlgo/UiT symbol master
#: (verified 02Oct2026 host: MCX GOLD/SILVER/CRUDEOIL, CDS USDINR all
#: present in the 107237-symbol download).
SEGMENT_SYMBOLS: dict[str, tuple[str, ...]] = {
    "NSE": ("NIFTY",),
    "MCX": ("GOLD", "SILVER", "CRUDEOIL"),
    "CDS": ("USDINR",),
}

#: OpenAlgo exchange each segment's benchmark quotes on. NSE benchmarks
#: are indices and MUST route to NSE_INDEX (verified live 08Sep2026:
#: NIFTY -> 200 on NSE_INDEX / 400 on NSE).
SEGMENT_EXCHANGES: dict[str, str] = {
    "NSE": "NSE_INDEX",
    "MCX": "MCX",
    "CDS": "CDS",
}

_AVAILABILITY_PHASE = {
    "halted": "halted",
    "pre_open": "pre_open",
    "closed": "closed",
}


class InstrumentMetrics(BaseModel):
    """Per-symbol price/volume legs from one quote payload."""

    ltp: float | None = None
    prev_close: float | None = None
    change_pct: float | None = None
    volume_ratio: float | None = None


class SegmentStatus(BaseModel):
    """One enabled segment's session, availability, and regime state."""

    segment: str
    session_open: bool
    session_window: str
    #: "available" | "unavailable: <reason>" | "halted" (weekend/holiday) |
    #: "pre_open" | "closed" (outside session on a trading day)
    availability: str
    ltp: float | None = None
    prev_close: float | None = None
    change_pct: float | None = None
    sentiment_score: float | None = Field(default=None, ge=-1.0, le=1.0)
    volume_ratio: float | None = None
    regime: MarketRegime = MarketRegime.NEUTRAL
    regime_reason: str = ""
    #: Per-benchmark metrics for the segment's candidate pool
    #: (mandate [3]); keyed by symbol, real per-symbol quote data.
    instruments: dict[str, InstrumentMetrics] = Field(default_factory=dict)


class InstrumentOpportunity(BaseModel):
    """A candidate instrument surfaced by mandate [3]."""

    segment: str
    symbol: str
    regime: MarketRegime
    change_pct: float | None
    sentiment_score: float | None
    volume_ratio: float | None
    score: float = Field(ge=0.0, description="Ranking score 0..1")


class MarketStatusReport(BaseModel):
    """Consolidated activation report for all enabled segments."""

    timestamp: str
    any_session_open: bool
    segments: list[SegmentStatus] = Field(default_factory=list)
    opportunities: list[InstrumentOpportunity] = Field(default_factory=list)

    def summary_line(self) -> str:
        """One-line digest for logs."""
        parts = [
            (
                f"{s.segment}={s.regime.value}"
                f"({'open' if s.session_open else 'shut'},"
                f"{s.availability.split(':')[0]})"
            )
            for s in self.segments
        ]
        return f"open={self.any_session_open} " + " ".join(parts)

    def telegram_text(self) -> str:
        """HTML-formatted Telegram report (all external text escaped)."""
        esc = html.escape
        state = "OPEN" if self.any_session_open else "SHUT"
        lines = [
            f"SESSION ACTIVATION [{esc(self.timestamp)}]",
            f"Session state: <b>{state}</b>",
            "",
        ]
        for s in self.segments:
            ltp = f"{s.ltp:.2f}" if s.ltp is not None else "n/a"
            chg = f"{s.change_pct:+.2f}%" if s.change_pct is not None else "n/a"
            sent = (
                f"{s.sentiment_score:+.2f}" if s.sentiment_score is not None else "n/a"
            )
            vol = f"{s.volume_ratio:.2f}x" if s.volume_ratio is not None else "n/a"
            lines.append(
                f"<b>[{esc(s.segment)}]</b> session="
                f"{'OPEN' if s.session_open else 'shut'} "
                f"({esc(s.session_window)}) availability={esc(s.availability)}"
            )
            lines.append(
                f"  regime=<b>{esc(s.regime.value)}</b> LTP={ltp} chg={chg} "
                f"sent={sent} vol={vol}"
            )
            if s.regime_reason:
                lines.append(f"  reason: {esc(s.regime_reason)}")
            if s.instruments:
                lines.append(f"  candidates: {esc(', '.join(s.instruments))}")
        if self.opportunities:
            names = ", ".join(
                f"{esc(o.symbol)}({o.regime.value})" for o in self.opportunities
            )
            lines.append(f"Top candidates: {names}")
        return "\n".join(lines)


class MarketStatusService:
    """Session activation, regime classification, instrument selection."""

    def __init__(self) -> None:
        # Segments whose open transition has already been announced this
        # process lifetime; only segments whose report was CONFIRMED
        # delivered land here, so a Telegram failure retries next tick.
        self._announced_open: set[str] = set()

    # ------------------------------------------------------------------
    # External fetch legs (each isolated; failures degrade to None)
    # ------------------------------------------------------------------

    @openalgo_circuit_breaker_retry_async
    async def _safe_get_quotes(
        self, symbols: list[str], exchanges: list[str]
    ) -> dict[str, Any] | None:
        """Segment quotes through the shared breaker-protected client."""
        from .openalgo import async_client

        try:
            return await async_client.get_quotes(symbols, exchanges=exchanges)
        except Exception as exc:
            logger.warning(
                "Quote leg failed for %s (exchanges %s): %s",
                symbols,
                exchanges,
                exc,
            )
            raise  # Re-raise so the circuit breaker records the failure

    async def _safe_sentiment(self, symbol: str) -> float | None:
        """Ensemble sentiment score for ``symbol``; None on any failure."""
        try:
            from .sentiment import sentiment

            result = await sentiment.analyze_symbol_sentiment(
                symbol, list(settings.rss_feeds)
            )
            return result.sentiment_score
        except Exception as exc:
            logger.warning("Sentiment fetch failed for %s: %s", symbol, exc)
            return None

    # ------------------------------------------------------------------
    # Classification (pure, deterministic, unit-tested)
    # ------------------------------------------------------------------

    @staticmethod
    def volume_ratio(volume: float | None, avg_volume: float | None) -> float | None:
        """Current-vs-average participation ratio; None when not computable."""
        if volume is None or avg_volume is None or avg_volume <= 0:
            return None
        return volume / avg_volume

    @staticmethod
    def _classify_regime(
        change_pct: float | None,
        sentiment_score: float | None,
        volume_ratio: float | None,
    ) -> tuple[MarketRegime, str]:
        """Deterministic BULL/BEAR/NEUTRAL classification.

        Rules (evaluated in order, first match wins):
        1. No price leg (quote failed / missing prev_close) -> NEUTRAL.
        2. Volume participation veto: a computable ratio below
           REGIME_VOLUME_VETO_RATIO means the move lacks participation
           -> NEUTRAL regardless of direction agreement.
        3. Flat band: |change| < REGIME_FLAT_PCT AND |sentiment| (when
           present) < REGIME_FLAT_SENTIMENT -> NEUTRAL.
        4. BULL: change >= +REGIME_TREND_PCT AND sentiment >=
           +REGIME_FLAT_SENTIMENT (agreement required; a strong price
           move against a strong contrary sentiment stays NEUTRAL).
        5. BEAR: mirror of rule 4.
        6. Anything else (directional price, sentiment absent or
           disagreeing) -> NEUTRAL.
        """
        if change_pct is None:
            return MarketRegime.NEUTRAL, "no price data"
        if volume_ratio is not None and volume_ratio < REGIME_VOLUME_VETO_RATIO:
            return (
                MarketRegime.NEUTRAL,
                f"volume participation {volume_ratio:.2f}x below "
                f"{REGIME_VOLUME_VETO_RATIO}x veto threshold",
            )
        if abs(change_pct) < REGIME_FLAT_PCT and (
            sentiment_score is None or abs(sentiment_score) < REGIME_FLAT_SENTIMENT
        ):
            return MarketRegime.NEUTRAL, "inside flat band"
        if change_pct >= REGIME_TREND_PCT and (
            sentiment_score is not None and sentiment_score >= REGIME_FLAT_SENTIMENT
        ):
            strong = (
                change_pct >= REGIME_STRONG_PCT
                and sentiment_score >= REGIME_STRONG_SENTIMENT
            )
            return MarketRegime.BULL, (
                "strong up-move with sentiment agreement"
                if strong
                else "up-move with sentiment agreement"
            )
        if change_pct <= -REGIME_TREND_PCT and (
            sentiment_score is not None and sentiment_score <= -REGIME_FLAT_SENTIMENT
        ):
            strong = (
                change_pct <= -REGIME_STRONG_PCT
                and sentiment_score <= -REGIME_STRONG_SENTIMENT
            )
            return MarketRegime.BEAR, (
                "strong down-move with sentiment agreement"
                if strong
                else "down-move with sentiment agreement"
            )
        if sentiment_score is None:
            return MarketRegime.NEUTRAL, "directional price without sentiment data"
        return MarketRegime.NEUTRAL, "price and sentiment disagree"

    @staticmethod
    def score_instrument(
        change_pct: float | None,
        sentiment_score: float | None,
        volume_ratio: float | None,
    ) -> float:
        """Mandate [3] ranking score: 0.5*|change| (capped 2%) +
        0.3*|sentiment| + 0.2*volume participation (capped 2x). Missing
        legs contribute 0. Best-effort identification for operators --
        NOT a tradeable signal (F8-H-03: the orchestrator owns signals).
        """
        change_leg = min(abs(change_pct), 2.0) / 2.0 if change_pct is not None else 0.0
        sent_leg = abs(sentiment_score) if sentiment_score is not None else 0.0
        vol_leg = min(volume_ratio, 2.0) / 2.0 if volume_ratio is not None else 0.0
        return 0.5 * change_leg + 0.3 * sent_leg + 0.2 * vol_leg

    @staticmethod
    def select_instruments(
        statuses: list[SegmentStatus], per_market: int = 3
    ) -> list[InstrumentOpportunity]:
        """Rank candidate instruments from per-segment status inputs.

        Excluded: NEUTRAL segments, segments under the volume veto, and
        instruments with no computable price leg. Sentiment is the
        segment's market-wide ensemble proxy (one score per segment).
        """
        opportunities: list[InstrumentOpportunity] = []
        for status in statuses:
            if status.regime == MarketRegime.NEUTRAL:
                continue
            if (
                status.volume_ratio is not None
                and status.volume_ratio < REGIME_VOLUME_VETO_RATIO
            ):
                continue
            for symbol, metrics in status.instruments.items():
                if metrics.change_pct is None:
                    continue
                opportunities.append(
                    InstrumentOpportunity(
                        segment=status.segment,
                        symbol=symbol,
                        regime=status.regime,
                        change_pct=metrics.change_pct,
                        sentiment_score=status.sentiment_score,
                        volume_ratio=metrics.volume_ratio,
                        score=MarketStatusService.score_instrument(
                            metrics.change_pct,
                            status.sentiment_score,
                            metrics.volume_ratio,
                        ),
                    )
                )
        by_segment: dict[str, list[InstrumentOpportunity]] = {}
        for opp in opportunities:
            by_segment.setdefault(opp.segment, []).append(opp)
        selected: list[InstrumentOpportunity] = []
        for seg_opps in by_segment.values():
            seg_opps.sort(key=lambda o: o.score, reverse=True)
            selected.extend(seg_opps[:per_market])
        return selected

    # ------------------------------------------------------------------
    # Snapshot assembly
    # ------------------------------------------------------------------

    @staticmethod
    def _now() -> datetime.datetime:
        return datetime.datetime.now(ZoneInfo(settings.timezone))

    def _session_phase(self, seg: str, now: datetime.datetime) -> str:
        """halted (weekend/holiday) | pre_open | open | closed.

        Function-level imports keep the segments surface patchable in
        tests (same pattern as scheduler._market_status_check_task).
        """
        from .segments import SEGMENT_HOLIDAYS, _parse_hhmm

        if now.weekday() >= 5:
            return "halted"
        if now.date() in SEGMENT_HOLIDAYS[seg]:
            return "halted"
        if is_segment_open(seg, now):
            return "open"
        open_h, open_m = _parse_hhmm(SEGMENT_SESSIONS[seg][0])
        open_dt = now.replace(hour=open_h, minute=open_m, second=0, microsecond=0)
        return "pre_open" if now < open_dt else "closed"

    async def snapshot(self) -> MarketStatusReport:
        """Build the consolidated per-segment report for enabled segments."""
        now = self._now()
        statuses = [await self._segment_status(seg, now) for seg in enabled_segments()]
        report = MarketStatusReport(
            timestamp=now.strftime("%Y-%m-%d %H:%M:%S %Z"),
            any_session_open=any(s.session_open for s in statuses),
            segments=statuses,
        )
        report.opportunities = self.select_instruments(statuses)
        return report

    async def _segment_status(self, seg: str, now: datetime.datetime) -> SegmentStatus:
        """Assemble one segment's status; data legs degrade independently."""
        phase = self._session_phase(seg, now)
        status = SegmentStatus(
            segment=seg,
            session_open=phase == "open",
            session_window="-".join(SEGMENT_SESSIONS[seg]),
            availability=_AVAILABILITY_PHASE.get(phase, "pending"),
        )
        if phase != "open":
            # Outside the session there is nothing to activate or classify;
            # NEUTRAL with a phase reason is the honest state.
            status.regime_reason = f"session {phase}"
            return status

        symbols = SEGMENT_SYMBOLS.get(seg, ())
        if not symbols:
            status.availability = "unavailable: no benchmark symbols configured"
            status.regime_reason = status.availability
            return status

        quotes: dict[str, Any] | None = None
        try:
            quotes = await self._safe_get_quotes(
                list(symbols), [SEGMENT_EXCHANGES[seg]] * len(symbols)
            )
        except Exception:
            quotes = None
        if not quotes or not isinstance(quotes.get("data"), dict) or not quotes["data"]:
            status.availability = "unavailable: no quote data"
            status.regime_reason = status.availability
            return status

        status.availability = "available"
        await self._fill_quote_legs(status, symbols, quotes["data"])
        return status

    async def _fill_quote_legs(
        self,
        status: SegmentStatus,
        symbols: tuple[str, ...],
        data: dict[str, Any],
    ) -> None:
        """Fill price/volume legs per symbol; sentiment once per segment.

        The FIRST benchmark symbol drives segment regime (NIFTY for NSE,
        GOLD for MCX, USDINR for CDS). Every fetched symbol becomes a
        mandate-[3] candidate with its own real quote metrics; the
        ensemble sentiment score is the market-wide proxy shared by the
        segment's candidates.
        """
        primary = symbols[0]
        if not isinstance(data.get(primary), dict):
            status.availability = f"unavailable: no quote for {primary}"
            status.regime_reason = status.availability
            return

        for symbol in symbols:
            q = data.get(symbol)
            if not isinstance(q, dict):
                continue
            ltp = q.get("last_price", q.get("ltp"))
            prev = q.get("close", q.get("prev_close"))
            volume = q.get("volume")
            avg_volume = q.get("average_volume")
            ltp_f = float(ltp) if ltp is not None else None
            prev_f = float(prev) if prev is not None else None
            change_pct = (
                (ltp_f - prev_f) / prev_f * 100.0
                if ltp_f is not None and prev_f
                else None
            )
            status.instruments[symbol] = InstrumentMetrics(
                ltp=ltp_f,
                prev_close=prev_f,
                change_pct=change_pct,
                volume_ratio=self.volume_ratio(
                    float(volume) if volume is not None else None,
                    float(avg_volume) if avg_volume is not None else None,
                ),
            )

        primary_metrics = status.instruments.get(primary)
        if primary_metrics is None:
            status.availability = f"unavailable: no usable quote for {primary}"
            status.regime_reason = status.availability
            return

        status.ltp = primary_metrics.ltp
        status.prev_close = primary_metrics.prev_close
        status.change_pct = primary_metrics.change_pct
        status.volume_ratio = primary_metrics.volume_ratio
        status.sentiment_score = await self._safe_sentiment(primary)
        status.regime, status.regime_reason = self._classify_regime(
            status.change_pct, status.sentiment_score, status.volume_ratio
        )

    # ------------------------------------------------------------------
    # Activation (mandate [1])
    # ------------------------------------------------------------------

    async def run_activation_check(self) -> MarketStatusReport:
        """One scheduler tick of the activation duty.

        Sends the consolidated Telegram report the first time ANY enabled
        segment transitions into its open session. Segments are marked
        announced ONLY after confirmed delivery, so a Telegram failure
        retries on the next tick.
        """
        report = await self.snapshot()
        newly_open = [s.segment for s in report.segments if s.session_open]
        announce = [seg for seg in newly_open if seg not in self._announced_open]
        if not announce:
            return report
        delivered = await alerts.send_system_alert(report.telegram_text(), "activation")
        if delivered:
            self._announced_open.update(announce)
        logger.info(
            "Session activation report for %s: delivered=%s (%s)",
            ",".join(announce),
            delivered,
            report.summary_line(),
        )
        return report


market_status_service = MarketStatusService()


__all__ = [
    "InstrumentMetrics",
    "InstrumentOpportunity",
    "MarketRegime",
    "MarketStatusReport",
    "MarketStatusService",
    "REGIME_VOLUME_VETO_RATIO",
    "SEGMENT_EXCHANGES",
    "SEGMENT_SYMBOLS",
    "SegmentStatus",
    "market_status_service",
]
