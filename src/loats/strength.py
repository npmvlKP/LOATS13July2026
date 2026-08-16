"""
CMP Strategy Strength Engine for LOATS13July2026.

Implements composite strength calculation with:
- ≥3-source requirement
- Opposition gate logic
- Source weighting and normalization
"""

from enum import StrEnum
from typing import Any

import numpy as np

from .config import get_settings
from .loats_logging import get_logger
from .models import Signal, SignalType

logger = get_logger(__name__)
settings = get_settings()


class StrengthSource(StrEnum):
    """Signal source enumeration."""

    TECHNICAL_ANALYSIS = "ta"
    SENTIMENT = "sentiment"
    PRICE_ACTION = "price_action"
    VOLATILITY = "volatility"
    FUNDAMENTAL = "fundamental"
    MACHINE_LEARNING = "ml"
    OPTIONS_FLOW = "options_flow"


class StrengthEngine:
    """CMP Strategy Strength Engine with composite calculation."""

    def __init__(self) -> None:
        """Initialize StrengthEngine."""
        self.source_weights = {
            StrengthSource.TECHNICAL_ANALYSIS: 0.4,
            StrengthSource.SENTIMENT: 0.3,
            StrengthSource.PRICE_ACTION: 0.2,
            StrengthSource.VOLATILITY: 0.1,
            StrengthSource.FUNDAMENTAL: 0.1,
            StrengthSource.MACHINE_LEARNING: 0.3,
            StrengthSource.OPTIONS_FLOW: 0.2,
        }

        self.min_sources = 3
        self.opposition_threshold = 0.6

    def normalize_strength(self, strength: float) -> float:
        """Normalize strength value to 0-1 range."""
        return float(np.clip(strength, 0.0, 1.0))

    def calculate_source_strength(
        self, signal: Signal, source: StrengthSource
    ) -> float:
        """
        Calculate strength contribution from a specific source.

        Applies source-specific weighting and normalization.
        """
        base_strength = signal.strength
        weight = self.source_weights.get(source, 0.1)

        # Apply source-specific adjustments
        if source == StrengthSource.TECHNICAL_ANALYSIS:
            # TA strength is typically more reliable
            adjusted_strength = base_strength * 1.1
        elif source == StrengthSource.SENTIMENT:
            # Sentiment can be more volatile
            adjusted_strength = base_strength * 0.9
        elif source == StrengthSource.PRICE_ACTION:
            # Price action is very reliable
            adjusted_strength = base_strength * 1.2
        else:
            # Default adjustment
            adjusted_strength = base_strength

        return self.normalize_strength(adjusted_strength * weight)

    def calculate_composite_strength(
        self, signals: list[Signal], require_opposition_gate: bool = True
    ) -> tuple[float, dict[str, Any]]:
        """
        Calculate composite strength from multiple signals.

        Requirements:
        - ≥3 sources for valid composite strength
        - Opposition gate: no strong opposing signals
        - Source diversity check
        """
        if len(signals) < self.min_sources:
            return 0.0, {
                "reason": "insufficient_sources",
                "required": self.min_sources,
                "available": len(signals),
            }

        # Group signals by source
        source_signals: dict[str, list[Signal]] = {}
        for signal in signals:
            source = signal.metadata.get("source", "unknown")
            if source not in source_signals:
                source_signals[source] = []
            source_signals[source].append(signal)

        # Check for opposition
        if require_opposition_gate:
            opposition_result = self.check_opposition_gate(source_signals)
            if not opposition_result["passed"]:
                return 0.0, {
                    "reason": "opposition_gate_failed",
                    "opposition_details": opposition_result,
                }

        # Calculate weighted composite strength
        total_strength = 0.0
        total_weight = 0.0
        source_contributions: dict[str, float] = {}

        for source, signal_list in source_signals.items():
            # Use the strongest signal from each source
            strongest_signal = max(signal_list, key=lambda s: s.strength)

            try:
                source_enum = StrengthSource(source)
            except ValueError:
                source_enum = StrengthSource.TECHNICAL_ANALYSIS  # Default

            source_strength = self.calculate_source_strength(
                strongest_signal, source_enum
            )
            total_strength += source_strength
            total_weight += self.source_weights.get(source_enum, 0.1)
            source_contributions[source] = source_strength

        # Normalize to 0-1 range
        if total_weight > 0:
            composite_strength = total_strength / total_weight
        else:
            composite_strength = 0.5  # Neutral default

        return self.normalize_strength(composite_strength), {
            "reason": "composite_calculated",
            "sources": len(source_signals),
            "source_contributions": source_contributions,
            "opposition_check": opposition_result,
            "total_strength": total_strength,
            "total_weight": total_weight,
        }

    def check_opposition_gate(
        self, source_signals: dict[str, list[Signal]]
    ) -> dict[str, Any]:
        """
        Check for opposing signals that would invalidate the composite.

        Opposition gate fails if:
        - Any source has strong signal (>0.7) in opposite direction
        - Multiple sources have moderate signals (>0.5) in opposite direction
        """
        # Determine primary direction
        primary_direction = self._determine_primary_direction(source_signals)

        if primary_direction is None:
            return {
                "passed": False,
                "reason": "no_clear_direction",
                "primary_direction": None,
            }

        # Check for opposition
        strong_opposition = 0
        moderate_opposition = 0

        for source, signals in source_signals.items():
            strongest_signal = max(signals, key=lambda s: s.strength)

            if (
                primary_direction == "BUY"
                and strongest_signal.signal_type == SignalType.SELL
            ) or (
                primary_direction == "SELL"
                and strongest_signal.signal_type == SignalType.BUY
            ):
                if strongest_signal.strength > self.opposition_threshold:
                    strong_opposition += 1
                elif strongest_signal.strength > 0.5:
                    moderate_opposition += 1

        # Apply opposition rules
        if strong_opposition >= 1:
            return {
                "passed": False,
                "reason": "strong_opposition_detected",
                "primary_direction": primary_direction,
                "strong_opposition": strong_opposition,
                "moderate_opposition": moderate_opposition,
            }
        elif moderate_opposition >= 2:
            return {
                "passed": False,
                "reason": "moderate_opposition_detected",
                "primary_direction": primary_direction,
                "strong_opposition": strong_opposition,
                "moderate_opposition": moderate_opposition,
            }
        else:
            return {
                "passed": True,
                "reason": "opposition_check_passed",
                "primary_direction": primary_direction,
                "strong_opposition": strong_opposition,
                "moderate_opposition": moderate_opposition,
            }

    def _determine_primary_direction(
        self, source_signals: dict[str, list[Signal]]
    ) -> str | None:
        """Determine primary trading direction from multiple sources."""
        buy_strength = 0.0
        sell_strength = 0.0

        for signals in source_signals.values():
            strongest_signal = max(signals, key=lambda s: s.strength)

            if strongest_signal.signal_type == SignalType.BUY:
                buy_strength += strongest_signal.strength
            elif strongest_signal.signal_type == SignalType.SELL:
                sell_strength += strongest_signal.strength

        if buy_strength > sell_strength * 1.2:  # 20% buffer
            return "BUY"
        elif sell_strength > buy_strength * 1.2:  # 20% buffer
            return "SELL"
        else:
            return None  # No clear direction

    def calculate_strength_diversity(
        self, source_signals: dict[str, list[Signal]]
    ) -> float:
        """
        Calculate source diversity score (0-1).

        Higher diversity means signals come from different types of sources,
        reducing correlation risk.
        """
        source_types = set()

        for source in source_signals.keys():
            try:
                source_enum = StrengthSource(source)
                source_types.add(source_enum)
            except ValueError:
                source_types.add(StrengthSource.TECHNICAL_ANALYSIS)

        # Diversity score based on number of unique source types
        diversity_score = min(len(source_types) / len(StrengthSource), 1.0)
        return float(diversity_score)

    def validate_signal_sources(
        self, signals: list[Signal]
    ) -> tuple[bool, dict[str, Any]]:
        """
        Validate that signals meet CMP requirements.

        Requirements:
        - ≥3 unique sources
        - Source diversity
        - No duplicate sources
        """
        source_set = set()
        for signal in signals:
            source = signal.metadata.get("source", "unknown")
            source_set.add(source)

        if len(source_set) < self.min_sources:
            return False, {
                "reason": "insufficient_unique_sources",
                "required": self.min_sources,
                "available": len(source_set),
                "sources": list(source_set),
            }

        # Check source diversity
        diversity_score = self.calculate_strength_diversity(
            dict.fromkeys(source_set, signals)
        )
        if diversity_score < 0.5:  # Minimum diversity threshold
            return False, {
                "reason": "insufficient_source_diversity",
                "diversity_score": diversity_score,
                "min_required": 0.5,
            }

        return True, {
            "reason": "source_validation_passed",
            "unique_sources": len(source_set),
            "diversity_score": diversity_score,
            "sources": list(source_set),
        }

    def get_source_strength_breakdown(self, signals: list[Signal]) -> dict[str, Any]:
        """
        Get detailed breakdown of strength by source.

        Useful for debugging and analysis.
        """
        breakdown: dict[str, Any] = {
            "sources": {},
            "total_strength": 0.0,
            "total_weight": 0.0,
            "composite_strength": 0.5,
        }

        source_signals: dict[str, list[Signal]] = {}
        for signal in signals:
            source = signal.metadata.get("source", "unknown")
            if source not in source_signals:
                source_signals[source] = []
            source_signals[source].append(signal)

        for source, signal_list in source_signals.items():
            strongest_signal = max(signal_list, key=lambda s: s.strength)

            try:
                source_enum = StrengthSource(source)
            except ValueError:
                source_enum = StrengthSource.TECHNICAL_ANALYSIS

            source_strength = self.calculate_source_strength(
                strongest_signal, source_enum
            )
            weight = self.source_weights.get(source_enum, 0.1)

            breakdown["sources"][source] = {
                "strength": source_strength,
                "weight": weight,
                "signal_type": str(strongest_signal.signal_type),
                "raw_strength": strongest_signal.strength,
                "indicators": strongest_signal.indicators,
            }

            breakdown["total_strength"] += source_strength
            breakdown["total_weight"] += weight

        if breakdown["total_weight"] > 0:
            breakdown["composite_strength"] = (
                breakdown["total_strength"] / breakdown["total_weight"]
            )

        breakdown["composite_strength"] = self.normalize_strength(
            breakdown["composite_strength"]
        )

        return breakdown


# Module-level singleton instance
strength_engine = StrengthEngine()

__all__ = ["StrengthEngine", "StrengthSource", "strength_engine"]
