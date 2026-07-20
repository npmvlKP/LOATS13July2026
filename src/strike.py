"""
Strike Selection Module for LOATS13July2026.
High-performance strike selection for options trading with <5ms latency target.

Implements:
- Delta-based ATM/OTM/ITM strike selection
- moneyness filtering and analysis
- Open Interest (OI) based strike identification
- Sentiment-weighted strike adjustment
"""

import logging
import time
from dataclasses import dataclass
from typing import Any

from .loats.models import OptionContract


@dataclass(frozen=True)
class StrikeSelection:
    """Result of strike selection analysis."""

    atm_strike: float
    selected_strike: float
    option_type: str
    delta_target: float
    moneyness: float
    oi_weight: float
    sentiment_adjustment: float
    final_score: float
    selection_reason: str
    latency_ms: float


class StrikeSelector:
    """
    High-performance strike selection engine.
    Target latency: <5ms for single strike selection.
    """

    # Delta targets for different strategies
    DELTA_TARGETS: dict[str, float] = {
        "aggressive_call": 0.30,  # OTM call (Delta 0.25-0.35)
        "mild_call": 0.40,  # Slightly OTM call (Delta 0.35-0.45)
        "atm_call": 0.50,  # ATM call (Delta ~0.50)
        "aggressive_put": -0.30,  # OTM put (Delta -0.25 to -0.35)
        "mild_put": -0.40,  # Slightly OTM put (Delta -0.35 to -0.45)
        "atm_put": -0.50,  # ATM put (Delta ~-0.50)
    }

    def __init__(self) -> None:
        """Initialize StrikeSelector."""
        self.logger = logging.getLogger(__name__)
        self._strike_cache: dict[str, tuple[float, float]] = {}
        self._max_cache_size = 1000

    def select_strike(
        self,
        option_chain: list[OptionContract],
        underlying_price: float,
        option_type: str = "CE",
        sentiment_score: float = 0.0,
        delta_target: float | None = None,
        prefer_oi: bool = True,
    ) -> StrikeSelection:
        """
        Select optimal strike based on option chain, sentiment, and delta target.
        Target: <5ms latency.

        Args:
            option_chain: List of option contracts
            underlying_price: Current underlying price
            option_type: "CE" for call, "PE" for put
            sentiment_score: Sentiment score (-1 to 1)
            delta_target: Specific delta target (auto-select if None)
            prefer_oi: Whether to prefer strikes with high open interest

        Returns:
            StrikeSelection with chosen strike and metadata
        """
        start_time = time.perf_counter()

        # Filter by option type
        filtered_options = [
            opt for opt in option_chain if opt.option_type.value == option_type
        ]

        if not filtered_options:
            return self._empty_selection(
                underlying_price, option_type, sentiment_score, start_time
            )

        # Sort by strike price
        filtered_options.sort(key=lambda x: x.strike_price)

        # Calculate ATM strike (closest to underlying)
        atm_strike = self._find_atm_strike(filtered_options, underlying_price)

        # Determine delta target if not specified
        if delta_target is None:
            delta_target = self._determine_delta_target(option_type, sentiment_score)

        # Find best strike based on delta target
        selected = self._find_strike_by_delta(
            filtered_options, underlying_price, option_type, delta_target
        )

        # Calculate OI weight if prefer_oi
        oi_weight = 0.0
        if prefer_oi:
            oi_weight = self._calculate_oi_weight(selected, filtered_options)

        # Calculate moneyness
        moneyness = self._calculate_moneyness(selected.strike_price, underlying_price)

        # Calculate sentiment adjustment
        sentiment_adjustment = self._calculate_sentiment_adjustment(
            sentiment_score, option_type
        )

        # Calculate final score
        final_score = self._calculate_final_score(
            delta_target, selected.delta or 0.5, oi_weight, sentiment_adjustment
        )

        # Generate selection reason
        reason = self._generate_selection_reason(
            selected.strike_price,
            atm_strike,
            option_type,
            delta_target,
            selected.delta or 0.5,
            oi_weight,
            sentiment_adjustment,
        )

        elapsed_ms = (time.perf_counter() - start_time) * 1000

        if elapsed_ms > 5:
            self.logger.warning(
                f"Strike selection took {elapsed_ms:.2f}ms (target: <5ms)"
            )

        return StrikeSelection(
            atm_strike=atm_strike,
            selected_strike=selected.strike_price,
            option_type=option_type,
            delta_target=delta_target,
            moneyness=moneyness,
            oi_weight=oi_weight,
            sentiment_adjustment=sentiment_adjustment,
            final_score=final_score,
            selection_reason=reason,
            latency_ms=elapsed_ms,
        )

    def _find_atm_strike(
        self, options: list[OptionContract], underlying_price: float
    ) -> float:
        """Find at-the-money strike (closest to underlying)."""
        if not options:
            return underlying_price

        best = min(options, key=lambda x: abs(x.strike_price - underlying_price))
        return float(best.strike_price)

    def _determine_delta_target(
        self, option_type: str, sentiment_score: float
    ) -> float:
        """Determine delta target based on option type and sentiment."""
        if option_type == "CE":
            if sentiment_score > 0.3:
                return 0.35  # More bullish - slightly OTM
            elif sentiment_score > 0.1:
                return 0.45  # Mild bullish - closer to ATM
            else:
                return 0.50  # Neutral - ATM
        else:  # PUT
            if sentiment_score < -0.3:
                return -0.35  # More bearish - slightly OTM
            elif sentiment_score < -0.1:
                return -0.45  # Mild bearish - closer to ATM
            else:
                return -0.50  # Neutral - ATM

    def _find_strike_by_delta(
        self,
        options: list[OptionContract],
        underlying_price: float,
        option_type: str,
        target_delta: float,
    ) -> OptionContract:
        """Find strike closest to target delta."""
        # If no delta data, use moneyness-based selection
        options_with_delta = [opt for opt in options if opt.delta is not None]

        if not options_with_delta:
            return self._find_strike_by_moneyness(
                options, underlying_price, option_type
            )

        # Find option closest to target delta
        best = min(
            options_with_delta,
            key=lambda x: abs((x.delta or 0.5) - abs(target_delta)),
        )

        # Ensure direction matches (positive delta for calls, negative for puts)
        if option_type == "CE" and (best.delta or 0) < 0:
            # Find positive delta alternative
            positive_delta = [o for o in options_with_delta if (o.delta or 0) > 0]
            if positive_delta:
                best = min(
                    positive_delta,
                    key=lambda x: abs(abs(x.delta or 0.5) - abs(target_delta)),
                )
        elif option_type == "PE" and (best.delta or 0) > 0:
            # Find negative delta alternative
            negative_delta = [o for o in options_with_delta if (o.delta or 0) < 0]
            if negative_delta:
                best = min(
                    negative_delta,
                    key=lambda x: abs(abs(x.delta or 0.5) - abs(target_delta)),
                )

        return best

    def _find_strike_by_moneyness(
        self, options: list[OptionContract], underlying_price: float, option_type: str
    ) -> OptionContract:
        """Find strike by moneyness when no delta data available."""
        atm_idx = None
        for i, opt in enumerate(options):
            if opt.strike_price <= underlying_price:
                atm_idx = i

        if atm_idx is None:
            return options[-1]  # Most OTM

        if option_type == "CE":
            # For calls, select slightly OTM (next strike above ATM)
            if atm_idx + 1 < len(options):
                return options[atm_idx + 1]
            return options[atm_idx]
        else:  # PE
            # For puts, select slightly OTM (next strike below ATM)
            if atm_idx > 0:
                return options[atm_idx - 1]
            return options[atm_idx]

    def _calculate_oi_weight(
        self, selected: OptionContract, all_options: list[OptionContract]
    ) -> float:
        """Calculate OI weight for selected strike (0-1 scale)."""
        if not all_options:
            return 0.0

        max_oi = max(opt.open_interest for opt in all_options)
        if max_oi == 0:
            return 0.0

        return float(min(selected.open_interest / max_oi, 1.0))

    def _calculate_moneyness(
        self, strike_price: float, underlying_price: float
    ) -> float:
        """Calculate moneyness: (S-K)/K for calls, (K-S)/S for puts."""
        if strike_price == 0:
            return 0.0
        return (underlying_price - strike_price) / strike_price

    def _calculate_sentiment_adjustment(
        self, sentiment_score: float, option_type: str
    ) -> float:
        """Calculate sentiment-based adjustment factor."""
        # Normalize sentiment to 0-1 range, then adjust
        if option_type == "CE":
            # Positive sentiment supports call selection
            return max(0, sentiment_score)
        else:  # PE
            # Negative sentiment supports put selection
            return max(0, -sentiment_score)

    def _calculate_final_score(
        self,
        target_delta: float,
        actual_delta: float,
        oi_weight: float,
        sentiment_adjustment: float,
    ) -> float:
        """Calculate final strike selection score."""
        # Delta match is most important (60%)
        delta_score = 1.0 - min(abs(target_delta - abs(actual_delta)), 1.0)

        # OI weight contributes 25%
        oi_score = oi_weight

        # Sentiment contributes 15%
        sentiment_score = sentiment_adjustment

        return (0.60 * delta_score) + (0.25 * oi_score) + (0.15 * sentiment_score)

    def _generate_selection_reason(
        self,
        selected_strike: float,
        atm_strike: float,
        option_type: str,
        target_delta: float,
        actual_delta: float,
        oi_weight: float,
        sentiment_adjustment: float,
    ) -> str:
        """Generate human-readable selection reason."""
        otm_distance = abs(selected_strike - atm_strike)
        otm_pct = (otm_distance / atm_strike) * 100 if atm_strike > 0 else 0

        direction = "call" if option_type == "CE" else "put"
        moneyness = (
            "ATM"
            if abs(otm_pct) < 0.5
            else (
                f"{otm_pct:.1f}% OTM"
                if selected_strike > atm_strike
                else f"{abs(otm_pct):.1f}% ITM"
            )
        )

        reasons = [f"Selected {direction} strike {selected_strike:.2f} ({moneyness})"]

        if oi_weight > 0.7:
            reasons.append(f"high OI support ({oi_weight:.0%})")
        if abs(sentiment_adjustment) > 0.2:
            reasons.append(f"sentiment-aligned ({sentiment_adjustment:+.2f})")

        reasons.append(
            f"delta ~{abs(actual_delta):.2f} (target: {abs(target_delta):.2f})"
        )

        return "; ".join(reasons)

    def _empty_selection(
        self,
        underlying_price: float,
        option_type: str,
        sentiment_score: float,
        start_time: float,
    ) -> StrikeSelection:
        """Return empty selection when no options available."""
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        return StrikeSelection(
            atm_strike=underlying_price,
            selected_strike=underlying_price,
            option_type=option_type,
            delta_target=0.5 if option_type == "CE" else -0.5,
            moneyness=0.0,
            oi_weight=0.0,
            sentiment_adjustment=sentiment_score,
            final_score=0.0,
            selection_reason="No options available for selection",
            latency_ms=elapsed_ms,
        )

    def clear_cache(self) -> None:
        """Clear strike selection cache."""
        self._strike_cache.clear()


# Module-level singleton for convenience
_strike_selector: StrikeSelector | None = None


def get_strike_selector() -> StrikeSelector:
    """Get or create strike selector singleton."""
    global _strike_selector
    if _strike_selector is None:
        _strike_selector = StrikeSelector()
    return _strike_selector


def select_strike(
    option_chain: list[OptionContract],
    underlying_price: float,
    option_type: str = "CE",
    sentiment_score: float = 0.0,
    delta_target: float | None = None,
) -> StrikeSelection:
    """
    Convenience function for strike selection.
    Target: <5ms latency.
    """
    return get_strike_selector().select_strike(
        option_chain=option_chain,
        underlying_price=underlying_price,
        option_type=option_type,
        sentiment_score=sentiment_score,
        delta_target=delta_target,
    )


class Strike:
    """
    Backward-compatible Strike class for existing tests.
    Delegates to StrikeSelector for actual implementation.
    Target latency: <5ms.
    """

    def __init__(self) -> None:
        """Initialize Strike wrapper."""
        self.logger = logging.getLogger(__name__)
        self._selector = StrikeSelector()

    def calculate(self, data: dict[str, Any]) -> dict[str, Any]:
        """
        Calculate strike selection from data dict.
        Backward compatible interface.

        Args:
            data: Dict containing:
                - option_chain: list of option contracts
                - underlying_price: float
                - option_type: str ("CE" or "PE")
                - sentiment_score: float (optional)
                - delta_target: float (optional)

        Returns:
            dict with selection results
        """
        start = time.perf_counter()

        option_chain = data.get("option_chain", [])
        underlying_price = data.get("underlying_price", 0.0)
        option_type = data.get("option_type", "CE")
        sentiment_score = data.get("sentiment_score", 0.0)
        delta_target = data.get("delta_target")

        selection = self._selector.select_strike(
            option_chain=option_chain,
            underlying_price=underlying_price,
            option_type=option_type,
            sentiment_score=sentiment_score,
            delta_target=delta_target,
        )

        result = {
            "atm_strike": selection.atm_strike,
            "selected_strike": selection.selected_strike,
            "option_type": selection.option_type,
            "delta_target": selection.delta_target,
            "moneyness": selection.moneyness,
            "oi_weight": selection.oi_weight,
            "sentiment_adjustment": selection.sentiment_adjustment,
            "final_score": selection.final_score,
            "selection_reason": selection.selection_reason,
            "latency_ms": selection.latency_ms,
        }

        elapsed = (time.perf_counter() - start) * 1000
        if elapsed > 5:
            self.logger.warning(f"Strike calculation {elapsed:.2f}ms (target: <5ms)")

        return result


__all__ = [
    "Strike",
    "StrikeSelector",
    "StrikeSelection",
    "get_strike_selector",
    "select_strike",
]
