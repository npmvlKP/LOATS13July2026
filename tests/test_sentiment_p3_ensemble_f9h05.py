"""F9-H-05 (TODO-14) -- CMP P3 sentiment ensemble/decay/bounds pins.

RED-first evidence for docs/audit-history/21Sep2026-F9H05-p3-ensemble-
decay-bounds.md. FR9 finding: CMP P3 mandates an "RSS+VADER ensemble
(news 70/social 30), decay. Gate: scores always [-1,+1]"; the shipped
implementation was a plain VADER mean with unbounded
``sentiment_score: float`` on both models (models.py NewsItem +
SentimentAnalysisResult), no decay, no ensemble, and no property test.

Delivery semantics (ADR-0017, docs/adr/0017-p3-sentiment-ensemble-
decay-bounds.md):
- Bounds are a HARD model invariant: ``Field(ge=-1.0, le=1.0)`` on both
  ``NewsItem.sentiment_score`` and ``SentimentAnalysisResult.sentiment_score``.
- Recency decay: ``0.5 ** (age_hours / 4)`` per article, applied BEFORE
  averaging (timezone-aware UTC math).
- Ensemble scaffold: news leg only, weight 1.0 on the CMP 70% scale.
  The social leg is ADR-DEFERRED -- a social score must NOT be
  fabricated (FR9 disposition), so ``ENSEMBLE_WEIGHTS`` carries exactly
  one key until a real social producer exists.
- The cold-start path and the detached refresh share ONE aggregation
  core (``_compute_and_count``) so the ensemble semantics cannot drift
  between the two callers.
"""

import inspect
import json
import math
import random
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from pydantic import ValidationError

from loats.models import NewsItem, SentimentAnalysisResult
from loats.sentiment import (
    ENSEMBLE_WEIGHTS,
    SENTIMENT_HALF_LIFE_HOURS,
    SentimentAnalyzer,
)

MODULE = "loats.sentiment"


def _news(score: float, age_hours: float = 0.0) -> NewsItem:
    """One feed item with a controlled score and publication age."""
    if score > 0:
        label = "positive"
    elif score < 0:
        label = "negative"
    else:
        label = "neutral"
    return NewsItem(
        title="t",
        content="c",
        source="s",
        url="u",
        published_date=datetime.now(UTC) - timedelta(hours=age_hours),
        sentiment_score=score,
        sentiment_label=label,
    )


def _result(
    score: float,
    symbol: str = "TEST",
) -> SentimentAnalysisResult:
    """A minimal in-range result for bounds-construction probes."""
    return SentimentAnalysisResult(
        symbol=symbol,
        timestamp=datetime.now(UTC),
        sentiment_score=score,
        sentiment_label="neutral",
        news_count=0,
        positive_count=0,
        negative_count=0,
        neutral_count=0,
        top_news=[],
    )


class TestDecayContract:
    """CMP P3: 4-hour half-life decay applied per article, pre-average."""

    def test_half_life_constant_is_four_hours(self):
        assert SENTIMENT_HALF_LIFE_HOURS == 4.0

    async def test_fresh_article_has_full_weight(self):
        analyzer = SentimentAnalyzer()
        result = await await_result(analyzer, [_news(0.8)])
        assert result.sentiment_score == pytest.approx(0.8)

    async def test_single_item_score_invariant_under_age(self):
        """Weighted-mean scale invariance (documented semantic, ADR-0017):
        one article at any age still scores its own score -- decay
        reweights RELATIVE recency in mixed sets; uniform staleness is
        surfaced by the result timestamp / degraded chain instead."""
        analyzer = SentimentAnalyzer()
        with patch(
            f"{MODULE}.SentimentAnalyzer.parse_rss_feed", new_callable=AsyncMock
        ) as mock_parse:
            mock_parse.return_value = [_news(0.8, age_hours=4.0)]
            result = await analyzer.analyze_symbol_sentiment("T", ["http://f"])
        assert result.sentiment_score == pytest.approx(0.8)

    async def test_age_dominance_symmetric_hand_computed(self):
        """Hand-computed recency dominance, both directions:
        (0.6*1.0 + -0.6*0.5) / 1.5 = +0.2, and mirrored
        (0.6*0.5 + -0.6*1.0) / 1.5 = -0.2. The fresher side dominates."""
        analyzer = SentimentAnalyzer()
        with patch(
            f"{MODULE}.SentimentAnalyzer.parse_rss_feed", new_callable=AsyncMock
        ) as mock_parse:
            mock_parse.return_value = [_news(0.6), _news(-0.6, age_hours=4.0)]
            result = await analyzer.analyze_symbol_sentiment("T", ["http://f"])
        assert result.sentiment_score == pytest.approx(0.2)
        with patch(
            f"{MODULE}.SentimentAnalyzer.parse_rss_feed", new_callable=AsyncMock
        ) as mock_parse:
            mock_parse.return_value = [
                _news(0.6, age_hours=4.0),
                _news(-0.6),
            ]
            mirrored = await analyzer.analyze_symbol_sentiment("T2", ["http://f"])
        assert mirrored.sentiment_score == pytest.approx(-0.2)

    async def test_decay_is_strictly_monotone_against_fixed_anchor(self):
        """0.8@age vs a fixed -0.8 fresh anchor: (0.8w - 0.8)/(w+1) with
        w = 0.5**(age/4) is strictly decreasing in age (0.0000, -0.0691,
        -0.2667, -0.4800, -0.7754, -0.8000 for 0/1/4/8/24/72 h;
        adversarial round 2 corrected the quoted decimals)."""
        analyzer = SentimentAnalyzer()
        previous: float | None = None
        for age in (0.0, 1.0, 4.0, 8.0, 24.0, 72.0):
            with patch(
                f"{MODULE}.SentimentAnalyzer.parse_rss_feed",
                new_callable=AsyncMock,
            ) as mock_parse:
                mock_parse.return_value = [
                    _news(0.8, age_hours=age),
                    _news(-0.8),
                ]
                # Unique symbol per age: iterations share the process,
                # and identical keys would serve iteration 1's cached
                # aggregation (by-design result cache, 300 s TTL).
                result = await analyzer.analyze_symbol_sentiment(
                    f"M{age}", ["http://f"]
                )
            if previous is not None:
                assert result.sentiment_score < previous - 1e-9
            previous = result.sentiment_score

    async def test_mixed_ensemble_hand_computed(self):
        """Hand-computed: 0.6 fresh (w=1.0) + -0.2 at 8 h (w=0.25).

        decayed mean = (0.6*1.0 + -0.2*0.25) / (1.0 + 0.25) = 0.44
        """
        analyzer = SentimentAnalyzer()
        with patch(
            f"{MODULE}.SentimentAnalyzer.parse_rss_feed", new_callable=AsyncMock
        ) as mock_parse:
            mock_parse.return_value = [_news(0.6), _news(-0.2, age_hours=8.0)]
            result = await analyzer.analyze_symbol_sentiment("T", ["http://f"])
        assert result.sentiment_score == pytest.approx(0.44)

    async def test_future_dated_article_treated_as_fresh(self):
        """Clock-skewed feeds must not poison the mean with huge weights."""
        analyzer = SentimentAnalyzer()
        item = NewsItem(
            title="t",
            content="c",
            source="s",
            url="u",
            published_date=datetime.now(UTC) + timedelta(hours=2),
            sentiment_score=0.5,
            sentiment_label="positive",
        )
        with patch(
            f"{MODULE}.SentimentAnalyzer.parse_rss_feed", new_callable=AsyncMock
        ) as mock_parse:
            mock_parse.return_value = [item]
            result = await analyzer.analyze_symbol_sentiment("T", ["http://f"])
        assert result.sentiment_score == pytest.approx(0.5)


class TestEnsembleScaffold:
    """CMP P3 70/30 scaffold: news leg real, social leg ADR-deferred."""

    def test_news_leg_weight_is_one(self):
        assert ENSEMBLE_WEIGHTS["news"] == 1.0

    def test_social_leg_is_not_fabricated(self):
        assert "social" not in ENSEMBLE_WEIGHTS

    def test_scaffold_has_no_silent_extra_legs(self):
        assert set(ENSEMBLE_WEIGHTS) == {"news"}


class TestModelBounds:
    """CMP P3 gate: scores always in [-1, +1] -- hard model invariant."""

    @pytest.mark.parametrize("score", [-1.0, -0.5, 0.0, 0.5, 1.0])
    def test_result_accepts_in_range(self, score: float):
        assert _result(score).sentiment_score == score

    @pytest.mark.parametrize("score", [1.000_001, 2.0, 100.0])
    def test_result_rejects_above_one(self, score: float):
        with pytest.raises(ValidationError):
            _result(score)

    @pytest.mark.parametrize("score", [-1.000_001, -2.0, -100.0])
    def test_result_rejects_below_minus_one(self, score: float):
        with pytest.raises(ValidationError):
            _result(score)

    @pytest.mark.parametrize("score", [1.5, -1.5])
    def test_news_item_rejects_out_of_range(self, score: float):
        with pytest.raises(ValidationError):
            _news(score)

    def test_seeded_fuzz_every_construction_in_bounds_rejected(self):
        """Seeded fuzz (no hypothesis dependency): 2000 draws in
        [-3, 3]; every draw with |score| > 1 must be rejected, every
        in-range draw accepted."""
        rng = random.Random(0xF9E05)
        rejected = accepted = 0
        for _ in range(2000):
            score = rng.uniform(-3.0, 3.0)
            if abs(score) > 1.0:
                with pytest.raises(ValidationError):
                    _result(score)
                rejected += 1
            else:
                assert _result(score).sentiment_score == score
                accepted += 1
        assert rejected > 1000  # fuzz actually exercised the rejection arm
        assert accepted > 500  # and the acceptance arm

    async def test_aggregation_stays_in_bounds_under_seeded_fuzz(self):
        """The averaged result is clamped for ANY combination of extreme
        per-article scores and ages -- the CMP P3 gate holds at the
        aggregation boundary too, not just at model construction."""
        rng = random.Random(0xF9E06)
        analyzer = SentimentAnalyzer()
        for iteration in range(40):
            count = rng.randint(1, 8)
            items = [
                _news(
                    rng.uniform(-1.0, 1.0),
                    age_hours=rng.uniform(0.0, 72.0),
                )
                for _ in range(count)
            ]
            with patch(
                f"{MODULE}.SentimentAnalyzer.parse_rss_feed",
                new_callable=AsyncMock,
            ) as mock_parse:
                mock_parse.return_value = items
                # Unique symbol per iteration: identical keys would hit
                # the by-design 5-minute result cache and serve the
                # first iteration's aggregation (isolation, not a
                # production defect).
                result = await analyzer.analyze_symbol_sentiment(
                    f"F{iteration}", ["http://f"]
                )
            assert math.isfinite(result.sentiment_score)
            assert -1.0 <= result.sentiment_score <= 1.0
            assert result.news_count == count


class TestColdPathDelegation:
    """F9-H-05 hygiene: the inline cold path must reuse the shared core."""

    async def test_cold_start_runs_exactly_one_shared_core_call(self):
        analyzer = SentimentAnalyzer()
        calls: list[tuple[str, list[str], int]] = []
        real = SentimentAnalyzer._compute_and_count

        async def spy(self, symbol, rss_urls, max_items):  # type: ignore[no-untyped-def]
            calls.append((symbol, rss_urls, max_items))
            return await real(self, symbol, rss_urls, max_items)

        with (
            patch.object(SentimentAnalyzer, "_compute_and_count", spy),
            patch(
                f"{MODULE}.SentimentAnalyzer.parse_rss_feed",
                new_callable=AsyncMock,
            ) as mock_parse,
        ):
            mock_parse.return_value = [_news(0.6), _news(-0.2, age_hours=8.0)]
            result = await analyzer.analyze_symbol_sentiment("T", ["http://f"])
        assert len(calls) == 1
        assert calls[0] == ("T", ["http://f"], 20)
        # Same ensemble math as the hand-computed pin above: the cold
        # path serves the shared core's result verbatim.
        assert result.sentiment_score == pytest.approx(0.44)

    async def test_counts_are_decay_invariant(self):
        """Decay reweights scores; it must not touch the tallies."""
        analyzer = SentimentAnalyzer()
        items = [_news(0.6), _news(-0.2, age_hours=8.0)]
        with patch(
            f"{MODULE}.SentimentAnalyzer.parse_rss_feed", new_callable=AsyncMock
        ) as mock_parse:
            mock_parse.return_value = items
            result = await analyzer.analyze_symbol_sentiment("T", ["http://f"])
        assert result.news_count == 2
        assert result.positive_count == 1
        assert result.negative_count == 1
        assert result.neutral_count == 0


class TestLegacyFailureTolerancePreserved:
    """The dedup must keep the legacy per-feed failure tolerance: one
    dead feed degrades the ensemble, it never raises out of the
    producer."""

    async def test_all_feeds_failing_yields_neutral_zero(self):
        analyzer = SentimentAnalyzer()
        with patch(
            f"{MODULE}.SentimentAnalyzer.parse_rss_feed",
            new_callable=AsyncMock,
            side_effect=RuntimeError("boom"),
        ):
            result = await analyzer.analyze_symbol_sentiment("T", ["http://f"])
        assert result.sentiment_score == 0.0
        assert result.sentiment_label == "neutral"
        assert result.news_count == 0

    async def test_mixed_feeds_survive_one_failure(self):
        analyzer = SentimentAnalyzer()

        async def failing_feed(url: str, max_items: int = 20):
            if "bad" in url:
                raise RuntimeError("feed down")
            return [_news(0.4)]

        with patch(
            f"{MODULE}.SentimentAnalyzer.parse_rss_feed",
            side_effect=failing_feed,
        ):
            result = await analyzer.analyze_symbol_sentiment(
                "T", ["http://good", "http://bad"]
            )
        assert result.news_count == 1
        assert result.sentiment_score == pytest.approx(0.4)


async def await_result(analyzer: SentimentAnalyzer, items: list[NewsItem]):
    """Small helper so the fresh-weight pin reads like the spec line."""
    with patch(
        f"{MODULE}.SentimentAnalyzer.parse_rss_feed", new_callable=AsyncMock
    ) as mock_parse:
        mock_parse.return_value = items
        return await analyzer.analyze_symbol_sentiment("T", ["http://f"])


class TestAdversarialRound2:
    """Findings from the independent adversarial review (AR-2/AR-3).

    AR-2 was a REAL production defect the wave's own pins missed:
    0.5 ** (age/4) underflows to exactly 0.0 in binary64 at age >~4300 h
    (~179 days); an all-ancient item set then hit 0.0/0.0 ->
    ZeroDivisionError out of the cold path, where the deleted inline
    code returned the plain mean for the identical input.
    """

    async def test_all_ancient_items_degrade_to_plain_mean(self):
        """Every weight underflowed -> plain mean, clamped, no raise."""
        analyzer = SentimentAnalyzer()
        with patch(
            f"{MODULE}.SentimentAnalyzer.parse_rss_feed", new_callable=AsyncMock
        ) as mock_parse:
            mock_parse.return_value = [
                _news(0.6, age_hours=5000.0),
                _news(-0.2, age_hours=6000.0),
            ]
            result = await analyzer.analyze_symbol_sentiment("AR2", ["http://f"])
        assert result.sentiment_score == pytest.approx(0.2)
        assert result.news_count == 2

    def test_underflow_boundary_weights_are_exact_zero(self):
        """Pins the ~4300 h threshold quoted in sentiment.py: below it
        weights are subnormal-but-positive, above it exactly 0.0."""
        assert 0.5 ** (4290.0 / 4.0) > 0.0
        assert 0.5 ** (4300.0 / 4.0) == 0.0

    async def test_ancient_item_cannot_regress_below_plain_mean_semantics(self):
        """A 500 h-old item still exercises the weighted path (weight is
        subnormal-but-positive ~2.3e-38): the fresh item dominates and
        the score is the fresh item's score to floating precision."""
        analyzer = SentimentAnalyzer()
        with patch(
            f"{MODULE}.SentimentAnalyzer.parse_rss_feed", new_callable=AsyncMock
        ) as mock_parse:
            mock_parse.return_value = [
                _news(-0.8, age_hours=500.0),
                _news(0.6),
            ]
            result = await analyzer.analyze_symbol_sentiment("AR2b", ["http://f"])
        assert result.sentiment_score == pytest.approx(0.6, rel=1e-6)

    def test_aggregation_does_not_silently_consume_the_scaffold(self):
        """AR-1/AR-3: ENSEMBLE_WEIGHTS is DECLARATIVE. The aggregation
        must not reference it until leg weighting is genuinely wired --
        a future 'social' key must be unable to change scores by
        appearing in the dict alone."""
        source = inspect.getsource(SentimentAnalyzer._compute_and_count)
        assert "ENSEMBLE_WEIGHTS" not in source

    def test_aggregation_signature_has_no_leg_parameter(self):
        """Same contract, signature level: no leg-weight parameter may
        appear without the ADR amendment the scaffold comment requires."""
        params = list(
            inspect.signature(SentimentAnalyzer._compute_and_count).parameters
        )
        assert params == ["self", "symbol", "rss_urls", "max_items"]

    def test_ensemble_weights_type_contract(self):
        assert ENSEMBLE_WEIGHTS == {"news": 1.0}
        assert all(isinstance(v, float) for v in ENSEMBLE_WEIGHTS.values())


class TestDeserializationBounds:
    """AR-5: the gate must hold on the paths the producer actually
    exercises -- cache round-trips (json.loads into the model at the
    result/LKG serving sites) and the nested top_news list -- not only
    direct construction."""

    @pytest.mark.parametrize("score", [1.5, -1.5, 100.0])
    def test_cached_payload_rejects_out_of_range_score(self, score: float):
        good = _result(0.3, symbol="RT")
        payload = good.model_dump_json().replace(
            '"sentiment_score":0.3', f'"sentiment_score":{score}'
        )
        with pytest.raises(ValidationError):
            SentimentAnalysisResult(**json.loads(payload))

    def test_cached_payload_round_trip_preserves_in_range_score(self):
        original = _result(-0.42, symbol="RT2")
        restored = SentimentAnalysisResult(**json.loads(original.model_dump_json()))
        assert restored.sentiment_score == pytest.approx(-0.42)
        assert restored.degraded is False

    @pytest.mark.parametrize("score", [1.2, -1.2, 3.4])
    def test_nested_top_news_rejects_out_of_range_item(self, score: float):
        with pytest.raises(ValidationError):
            SentimentAnalysisResult(
                symbol="NT",
                timestamp=datetime.now(UTC),
                sentiment_score=0.1,
                sentiment_label="neutral",
                news_count=1,
                positive_count=0,
                negative_count=1,
                neutral_count=0,
                top_news=[_news(score)],
            )
