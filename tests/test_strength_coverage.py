"""
Comprehensive test coverage for strength.py module.
This test file aims to achieve 80%+ coverage for the StrengthEngine class.
"""

import datetime

from loats.models import Signal, SignalType
from loats.strength import StrengthEngine, StrengthSource, strength_engine


def create_signal(
    signal_id: str,
    symbol: str,
    signal_type: SignalType,
    strength: float,
    indicators: dict[str, float] | None = None,
    metadata: dict[str, str] | None = None,
) -> Signal:
    """Helper function to create a valid Signal with proper timestamp."""
    if indicators is None:
        indicators = {}
    if metadata is None:
        metadata = {}

    return Signal(
        signal_id=signal_id,
        symbol=symbol,
        signal_type=signal_type,
        strength=strength,
        timestamp=datetime.datetime.now(datetime.UTC),
        indicators=indicators,
        metadata=metadata,
    )


class TestStrengthEngineInitialization:
    """Test StrengthEngine initialization and basic properties."""

    def test_initialization(self) -> None:
        """Test that StrengthEngine initializes correctly."""
        engine = StrengthEngine()
        assert len(engine.source_weights) == 7
        assert engine.min_sources == 3
        assert engine.opposition_threshold == 0.6

        # Check default weights
        assert engine.source_weights[StrengthSource.TECHNICAL_ANALYSIS] == 0.4
        assert engine.source_weights[StrengthSource.SENTIMENT] == 0.3
        assert engine.source_weights[StrengthSource.PRICE_ACTION] == 0.2

    def test_strength_source_enum(self) -> None:
        """Test StrengthSource enumeration."""
        assert StrengthSource.TECHNICAL_ANALYSIS == "ta"
        assert StrengthSource.SENTIMENT == "sentiment"
        assert StrengthSource.PRICE_ACTION == "price_action"
        assert StrengthSource.VOLATILITY == "volatility"
        assert StrengthSource.FUNDAMENTAL == "fundamental"
        assert StrengthSource.MACHINE_LEARNING == "ml"
        assert StrengthSource.OPTIONS_FLOW == "options_flow"


class TestNormalization:
    """Test strength normalization functionality."""

    def test_normalize_strength(self) -> None:
        """Test strength normalization."""
        engine = StrengthEngine()

        # Test values within range
        assert engine.normalize_strength(0.5) == 0.5
        assert engine.normalize_strength(0.0) == 0.0
        assert engine.normalize_strength(1.0) == 1.0

        # Test values outside range (should be clipped)
        assert engine.normalize_strength(1.5) == 1.0
        assert engine.normalize_strength(-0.5) == 0.0
        assert engine.normalize_strength(2.0) == 1.0
        assert engine.normalize_strength(-1.0) == 0.0


class TestSourceStrengthCalculation:
    """Test source-specific strength calculations."""

    def test_calculate_source_strength_technical_analysis(self) -> None:
        """Test source strength calculation for technical analysis."""
        engine = StrengthEngine()

        signal = create_signal(
            signal_id="test-001",
            symbol="NIFTY",
            signal_type=SignalType.BUY,
            strength=0.7,
            indicators={"rsi": 30.0},
        )

        strength = engine.calculate_source_strength(
            signal, StrengthSource.TECHNICAL_ANALYSIS
        )
        expected = engine.normalize_strength(
            0.7 * 1.1 * 0.4
        )  # base * adjustment * weight
        assert strength == expected

    def test_calculate_source_strength_sentiment(self) -> None:
        """Test source strength calculation for sentiment."""
        engine = StrengthEngine()

        signal = create_signal(
            signal_id="test-001",
            symbol="NIFTY",
            signal_type=SignalType.BUY,
            strength=0.6,
            indicators={"sentiment_score": 0.8},
        )

        strength = engine.calculate_source_strength(signal, StrengthSource.SENTIMENT)
        expected = engine.normalize_strength(
            0.6 * 0.9 * 0.3
        )  # base * adjustment * weight
        assert strength == expected

    def test_calculate_source_strength_price_action(self) -> None:
        """Test source strength calculation for price action."""
        engine = StrengthEngine()

        signal = create_signal(
            signal_id="test-001",
            symbol="NIFTY",
            signal_type=SignalType.BUY,
            strength=0.8,
            indicators={"price_action": 0.8},
        )

        strength = engine.calculate_source_strength(signal, StrengthSource.PRICE_ACTION)
        expected = engine.normalize_strength(
            0.8 * 1.2 * 0.2
        )  # base * adjustment * weight
        assert strength == expected

    def test_calculate_source_strength_other_sources(self) -> None:
        """Test source strength calculation for other sources."""
        engine = StrengthEngine()

        signal = create_signal(
            signal_id="test-001",
            symbol="NIFTY",
            signal_type=SignalType.BUY,
            strength=0.5,
            indicators={"volatility": 0.05},
        )

        strength = engine.calculate_source_strength(signal, StrengthSource.VOLATILITY)
        expected = engine.normalize_strength(
            0.5 * 1.0 * 0.1
        )  # base * adjustment * weight
        assert strength == expected

    def test_calculate_source_strength_unknown_source(self) -> None:
        """Test source strength calculation for unknown source."""
        engine = StrengthEngine()

        # Create signals with one unknown source and other known sources
        signals = [
            create_signal(
                signal_id="test-001",
                symbol="NIFTY",
                signal_type=SignalType.BUY,
                strength=0.6,
                indicators={},
                metadata={"source": "unknown"},  # Unknown source
            ),
            create_signal(
                signal_id="test-002",
                symbol="NIFTY",
                signal_type=SignalType.BUY,
                strength=0.7,
                indicators={},
                metadata={"source": "ta"},  # Known source
            ),
            create_signal(
                signal_id="test-003",
                symbol="NIFTY",
                signal_type=SignalType.BUY,
                strength=0.8,
                indicators={},
                metadata={"source": "sentiment"},  # Known source
            ),
        ]

        # Test that unknown sources are handled through composite strength calculation
        # The composite method should default unknown sources to TECHNICAL_ANALYSIS
        strength, details = engine.calculate_composite_strength(
            signals, require_opposition_gate=False
        )

        # Check that the unknown source was processed and is in the contributions
        assert strength > 0.0  # Should have valid strength
        assert "unknown" in details["source_contributions"]
        assert details["reason"] == "composite_calculated"
        assert details["sources"] == 3


class TestCompositeStrengthCalculation:
    """Test composite strength calculation functionality."""

    def test_calculate_composite_strength_insufficient_sources(self) -> None:
        """Test composite strength with insufficient sources."""
        engine = StrengthEngine()

        signals = [
            create_signal(
                signal_id=f"test-{i:03d}",
                symbol="NIFTY",
                signal_type=SignalType.BUY,
                strength=0.6 + i * 0.1,
                indicators={},
                metadata={
                    "source": ["ta", "sentiment", "price_action", "volatility"][i]
                },
            )
            for i in range(2)  # Only 2 sources (need 3)
        ]

        strength, details = engine.calculate_composite_strength(signals)
        assert strength == 0.0
        assert details["reason"] == "insufficient_sources"
        assert details["required"] == 3
        assert details["available"] == 2

    def test_calculate_composite_strength_sufficient_sources(self) -> None:
        """Test composite strength with sufficient sources."""
        engine = StrengthEngine()

        signals = [
            create_signal(
                signal_id=f"test-{i:03d}",
                symbol="NIFTY",
                signal_type=SignalType.BUY,
                strength=0.6 + i * 0.1,
                indicators={},
                metadata={"source": f"source-{i}"},
            )
            for i in range(4)  # 4 sources (meets requirement)
        ]

        strength, details = engine.calculate_composite_strength(signals)
        assert 0.0 <= strength <= 1.0
        assert details["reason"] == "composite_calculated"
        assert details["sources"] == 4
        assert "source_contributions" in details
        assert "opposition_check" in details

    def test_calculate_composite_strength_opposition_gate_failed(self) -> None:
        """Test composite strength when opposition gate fails."""
        engine = StrengthEngine()

        signals = [
            create_signal(
                signal_id="test-001",
                symbol="NIFTY",
                signal_type=SignalType.BUY,
                strength=0.8,
                indicators={},
                metadata={"source": "ta"},
            ),
            create_signal(
                signal_id="test-002",
                symbol="NIFTY",
                signal_type=SignalType.BUY,
                strength=0.7,
                indicators={},
                metadata={"source": "sentiment"},
            ),
            create_signal(
                signal_id="test-003",
                symbol="NIFTY",
                signal_type=SignalType.SELL,  # Opposing signal
                strength=0.8,  # Strong opposition (> 0.6 threshold)
                indicators={},
                metadata={"source": "price_action"},
            ),
        ]

        strength, details = engine.calculate_composite_strength(signals)
        assert strength == 0.0
        assert details["reason"] == "opposition_gate_failed"
        assert "opposition_details" in details

    def test_calculate_composite_strength_no_opposition_gate(self) -> None:
        """Test composite strength without opposition gate."""
        engine = StrengthEngine()

        signals = [
            create_signal(
                signal_id="test-001",
                symbol="NIFTY",
                signal_type=SignalType.BUY,
                strength=0.8,
                indicators={},
                metadata={"source": "ta"},
            ),
            create_signal(
                signal_id="test-002",
                symbol="NIFTY",
                signal_type=SignalType.BUY,
                strength=0.7,
                indicators={},
                metadata={"source": "sentiment"},
            ),
            create_signal(
                signal_id="test-003",
                symbol="NIFTY",
                signal_type=SignalType.SELL,  # Opposing signal
                strength=0.8,  # Strong opposition
                indicators={},
                metadata={"source": "price_action"},
            ),
        ]

        # Disable opposition gate
        strength, details = engine.calculate_composite_strength(
            signals, require_opposition_gate=False
        )
        assert strength > 0.0  # Should pass without opposition gate
        assert details["reason"] == "composite_calculated"


class TestOppositionGate:
    """Test opposition gate functionality."""

    def test_check_opposition_gate_no_clear_direction(self) -> None:
        """Test opposition gate with no clear direction."""
        engine = StrengthEngine()

        source_signals = {
            "ta": [
                create_signal(
                    signal_id="test-001",
                    symbol="NIFTY",
                    signal_type=SignalType.BUY,
                    strength=0.5,  # BUY
                    indicators={},
                )
            ],
            "sentiment": [
                create_signal(
                    signal_id="test-002",
                    symbol="NIFTY",
                    signal_type=SignalType.BUY,
                    strength=0.5,  # BUY
                    indicators={},
                )
            ],
            "price_action": [
                create_signal(
                    signal_id="test-003",
                    symbol="NIFTY",
                    signal_type=SignalType.SELL,  # SELL
                    strength=1.0,  # Double strength to balance exactly
                    indicators={},
                )
            ],
        }

        result = engine.check_opposition_gate(source_signals)
        assert not result["passed"]
        assert result["reason"] == "no_clear_direction"

    def test_check_opposition_gate_strong_opposition(self) -> None:
        """Test opposition gate with strong opposition."""
        engine = StrengthEngine()

        source_signals = {
            "ta": [
                create_signal(
                    signal_id="test-001",
                    symbol="NIFTY",
                    signal_type=SignalType.BUY,
                    strength=0.8,
                    indicators={},
                )
            ],
            "sentiment": [
                create_signal(
                    signal_id="test-002",
                    symbol="NIFTY",
                    signal_type=SignalType.BUY,
                    strength=0.7,
                    indicators={},
                )
            ],
            "price_action": [
                create_signal(
                    signal_id="test-003",
                    symbol="NIFTY",
                    signal_type=SignalType.SELL,
                    strength=0.8,  # Strong opposition (> 0.6)
                    indicators={},
                )
            ],
        }

        result = engine.check_opposition_gate(source_signals)
        assert not result["passed"]
        assert result["reason"] == "strong_opposition_detected"
        assert result["strong_opposition"] == 1

    def test_check_opposition_gate_moderate_opposition(self) -> None:
        """Test opposition gate with moderate opposition."""
        engine = StrengthEngine()

        # BUY is the clear primary direction (aggregate 1.5 vs 1.2, >20% buffer)
        # while two sources show moderate (>0.5) SELL opposition.
        source_signals = {
            "ta": [
                create_signal(
                    signal_id="test-001",
                    symbol="NIFTY",
                    signal_type=SignalType.BUY,
                    strength=0.8,
                    indicators={},
                )
            ],
            "sentiment": [
                create_signal(
                    signal_id="test-002",
                    symbol="NIFTY",
                    signal_type=SignalType.SELL,
                    strength=0.6,  # Moderate opposition (> 0.5)
                    indicators={},
                )
            ],
            "price_action": [
                create_signal(
                    signal_id="test-003",
                    symbol="NIFTY",
                    signal_type=SignalType.SELL,
                    strength=0.6,  # Moderate opposition (> 0.5)
                    indicators={},
                )
            ],
            "volatility": [
                create_signal(
                    signal_id="test-004",
                    symbol="NIFTY",
                    signal_type=SignalType.BUY,
                    strength=0.7,
                    indicators={},
                )
            ],
        }

        result = engine.check_opposition_gate(source_signals)
        assert not result["passed"]
        assert result["reason"] == "moderate_opposition_detected"
        assert result["moderate_opposition"] == 2

    def test_check_opposition_gate_pass(self) -> None:
        """Test opposition gate that should pass."""
        engine = StrengthEngine()

        source_signals = {
            "ta": [
                create_signal(
                    signal_id="test-001",
                    symbol="NIFTY",
                    signal_type=SignalType.BUY,
                    strength=0.8,
                    indicators={},
                )
            ],
            "sentiment": [
                create_signal(
                    signal_id="test-002",
                    symbol="NIFTY",
                    signal_type=SignalType.BUY,
                    strength=0.7,
                    indicators={},
                )
            ],
            "price_action": [
                create_signal(
                    signal_id="test-003",
                    symbol="NIFTY",
                    signal_type=SignalType.SELL,
                    strength=0.4,  # Weak opposition (< 0.5)
                    indicators={},
                )
            ],
        }

        result = engine.check_opposition_gate(source_signals)
        assert result["passed"]
        assert result["reason"] == "opposition_check_passed"
        assert result["strong_opposition"] == 0
        assert result["moderate_opposition"] == 0


class TestDirectionDetermination:
    """Test primary direction determination functionality."""

    def test_determine_primary_direction_buy(self) -> None:
        """Test primary direction determination for BUY."""
        engine = StrengthEngine()

        source_signals = {
            "ta": [
                create_signal(
                    signal_id="test-001",
                    symbol="NIFTY",
                    signal_type=SignalType.BUY,
                    strength=0.8,
                    indicators={},
                )
            ],
            "sentiment": [
                create_signal(
                    signal_id="test-002",
                    symbol="NIFTY",
                    signal_type=SignalType.BUY,
                    strength=0.7,
                    indicators={},
                )
            ],
            "price_action": [
                create_signal(
                    signal_id="test-003",
                    symbol="NIFTY",
                    signal_type=SignalType.SELL,
                    strength=0.3,
                    indicators={},
                )
            ],
        }

        direction = engine._determine_primary_direction(source_signals)
        assert direction == "BUY"

    def test_determine_primary_direction_sell(self) -> None:
        """Test primary direction determination for SELL."""
        engine = StrengthEngine()

        source_signals = {
            "ta": [
                create_signal(
                    signal_id="test-001",
                    symbol="NIFTY",
                    signal_type=SignalType.SELL,
                    strength=0.8,
                    indicators={},
                )
            ],
            "sentiment": [
                create_signal(
                    signal_id="test-002",
                    symbol="NIFTY",
                    signal_type=SignalType.SELL,
                    strength=0.7,
                    indicators={},
                )
            ],
            "price_action": [
                create_signal(
                    signal_id="test-003",
                    symbol="NIFTY",
                    signal_type=SignalType.BUY,
                    strength=0.3,
                    indicators={},
                )
            ],
        }

        direction = engine._determine_primary_direction(source_signals)
        assert direction == "SELL"

    def test_determine_primary_direction_no_clear_direction(self) -> None:
        """Test primary direction determination with no clear direction."""
        engine = StrengthEngine()

        source_signals = {
            "ta": [
                create_signal(
                    signal_id="test-001",
                    symbol="NIFTY",
                    signal_type=SignalType.BUY,
                    strength=0.5,
                    indicators={},
                )
            ],
            "sentiment": [
                create_signal(
                    signal_id="test-002",
                    symbol="NIFTY",
                    signal_type=SignalType.SELL,
                    strength=0.76,  # Increased to create truly balanced scenario
                    indicators={},
                )
            ],
            "price_action": [
                create_signal(
                    signal_id="test-003",
                    symbol="NIFTY",
                    signal_type=SignalType.BUY,
                    strength=0.3,
                    indicators={},
                )
            ],
        }

        direction = engine._determine_primary_direction(source_signals)
        assert direction is None


class TestStrengthDiversity:
    """Test strength diversity calculation functionality."""

    def test_calculate_strength_diversity(self) -> None:
        """Test strength diversity calculation."""
        engine = StrengthEngine()

        source_signals = {
            "ta": [
                create_signal(
                    signal_id="test-001",
                    symbol="NIFTY",
                    signal_type=SignalType.BUY,
                    strength=0.8,
                    indicators={},
                )
            ],
            "sentiment": [
                create_signal(
                    signal_id="test-002",
                    symbol="NIFTY",
                    signal_type=SignalType.BUY,
                    strength=0.7,
                    indicators={},
                )
            ],
            "price_action": [
                create_signal(
                    signal_id="test-003",
                    symbol="NIFTY",
                    signal_type=SignalType.BUY,
                    strength=0.6,
                    indicators={},
                )
            ],
        }

        diversity = engine.calculate_strength_diversity(source_signals)
        assert 0.0 <= diversity <= 1.0
        assert diversity > 0.0  # Should have some diversity with 3 different sources

    def test_calculate_strength_diversity_single_source(self) -> None:
        """Test strength diversity with single source."""
        engine = StrengthEngine()

        source_signals = {
            "ta": [
                create_signal(
                    signal_id="test-001",
                    symbol="NIFTY",
                    signal_type=SignalType.BUY,
                    strength=0.8,
                    indicators={},
                )
            ]
        }

        diversity = engine.calculate_strength_diversity(source_signals)
        assert diversity == 1.0 / len(StrengthSource)  # 1 source out of total


class TestSourceValidation:
    """Test signal source validation functionality."""

    def test_validate_signal_sources_insufficient(self) -> None:
        """Test source validation with insufficient sources."""
        engine = StrengthEngine()

        signals = [
            create_signal(
                signal_id=f"test-{i:03d}",
                symbol="NIFTY",
                signal_type=SignalType.BUY,
                strength=0.6 + i * 0.1,
                indicators={},
                metadata={"source": f"source-{i}"},
            )
            for i in range(2)  # Only 2 sources (need 3)
        ]

        valid, details = engine.validate_signal_sources(signals)
        assert not valid
        assert details["reason"] == "insufficient_unique_sources"
        assert details["required"] == 3
        assert details["available"] == 2

    def test_validate_signal_sources_sufficient(self) -> None:
        """Test source validation with sufficient sources."""
        engine = StrengthEngine()

        # Use actual StrengthSource enum values for proper diversity calculation
        source_types = [
            StrengthSource.TECHNICAL_ANALYSIS,
            StrengthSource.SENTIMENT,
            StrengthSource.PRICE_ACTION,
            StrengthSource.VOLATILITY,
        ]

        signals = [
            create_signal(
                signal_id=f"test-{i:03d}",
                symbol="NIFTY",
                signal_type=SignalType.BUY,
                strength=0.6 + i * 0.1,
                indicators={},
                metadata={"source": str(source_types[i])},
            )
            for i in range(4)  # 4 sources (meets requirement)
        ]

        valid, details = engine.validate_signal_sources(signals)
        assert valid
        assert details["reason"] == "source_validation_passed"
        assert details["unique_sources"] == 4

    def test_validate_signal_sources_insufficient_diversity(self) -> None:
        """Test source validation with insufficient diversity."""
        engine = StrengthEngine()

        # Create signals from same source type
        signals = [
            create_signal(
                signal_id=f"test-{i:03d}",
                symbol="NIFTY",
                signal_type=SignalType.BUY,
                strength=0.6 + i * 0.1,
                indicators={},
                # Unique strings, but all resolve to the same source type
                metadata={"source": f"ta-{i}"},
            )
            for i in range(4)
        ]

        valid, details = engine.validate_signal_sources(signals)
        assert not valid
        assert details["reason"] == "insufficient_source_diversity"
        assert details["diversity_score"] < 0.5

    def test_validate_signal_sources_sufficient_diversity(self) -> None:
        """Test source validation with sufficient diversity."""
        engine = StrengthEngine()

        # Use valid StrengthSource values (4/7 sources >= 0.5 diversity)
        sources = ["ta", "sentiment", "price_action", "volatility"]

        signals = [
            create_signal(
                signal_id=f"test-{i:03d}",
                symbol="NIFTY",
                signal_type=SignalType.BUY,
                strength=0.6 + i * 0.1,
                indicators={},
                metadata={"source": sources[i]},
            )
            for i in range(4)
        ]

        valid, details = engine.validate_signal_sources(signals)
        assert valid
        assert details["diversity_score"] >= 0.5


class TestStrengthBreakdown:
    """Test strength breakdown functionality."""

    def test_get_source_strength_breakdown(self) -> None:
        """Test detailed strength breakdown."""
        engine = StrengthEngine()

        signals = [
            create_signal(
                signal_id=f"test-{i:03d}",
                symbol="NIFTY",
                signal_type=SignalType.BUY,
                strength=0.6 + i * 0.1,
                indicators={f"indicator-{i}": 0.5 + i * 0.1},
                metadata={"source": f"source-{i}"},
            )
            for i in range(4)
        ]

        breakdown = engine.get_source_strength_breakdown(signals)

        assert "sources" in breakdown
        assert "total_strength" in breakdown
        assert "total_weight" in breakdown
        assert "composite_strength" in breakdown
        assert 0.0 <= breakdown["composite_strength"] <= 1.0

        # Check that all sources are included
        assert len(breakdown["sources"]) == 4
        for source_id in range(4):
            source_key = f"source-{source_id}"
            assert source_key in breakdown["sources"]
            source_data = breakdown["sources"][source_key]
            assert "strength" in source_data
            assert "weight" in source_data
            assert "signal_type" in source_data
            assert "raw_strength" in source_data
            assert "indicators" in source_data


class TestModuleLevelSingleton:
    """Test module-level singleton instance."""

    def test_strength_engine_singleton(self) -> None:
        """Test that strength_engine is a proper singleton."""

        assert isinstance(strength_engine, StrengthEngine)
        assert strength_engine.min_sources == 3
        assert strength_engine.opposition_threshold == 0.6

        # Test that it's the same instance
        from loats.strength import strength_engine as strength_engine_2

        assert strength_engine is strength_engine_2
