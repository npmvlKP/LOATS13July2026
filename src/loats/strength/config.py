"""Configuration for the CMP Strategy Strength Engine."""

from functools import lru_cache

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class StrengthEngineSettings(BaseSettings):
    """Settings for the Strength Engine."""

    model_config = SettingsConfigDict(
        env_prefix="LOATS_STRENGTH_",
        case_sensitive=False,
        extra="ignore",
    )

    # Minimum sources required for composite calculation
    min_sources: int = Field(default=3, ge=2, le=10)

    # Opposition threshold (signals above this in opposite
    # direction count as opposition)
    opposition_threshold: float = Field(default=0.4, ge=0.0, le=1.0)

    # Source weights (can be overridden via env)
    ta_weight: float = Field(default=0.4, ge=0.0, le=1.0)
    sentiment_weight: float = Field(default=0.3, ge=0.0, le=1.0)
    price_action_weight: float = Field(default=0.2, ge=0.0, le=1.0)
    volatility_weight: float = Field(default=0.1, ge=0.0, le=1.0)
    fundamental_weight: float = Field(default=0.1, ge=0.0, le=1.0)
    ml_weight: float = Field(default=0.3, ge=0.0, le=1.0)
    options_flow_weight: float = Field(default=0.2, ge=0.0, le=1.0)

    # Source-specific adjustment factors
    ta_adjustment: float = Field(default=1.1, ge=0.5, le=2.0)
    sentiment_adjustment: float = Field(default=0.9, ge=0.5, le=2.0)
    price_action_adjustment: float = Field(default=1.2, ge=0.5, le=2.0)

    # Regime detection thresholds
    hurst_trending_threshold: float = Field(default=0.6, ge=0.0, le=1.0)
    regime_strong_threshold: float = Field(default=0.8, ge=0.0, le=1.0)
    hurst_mean_reverting_threshold: float = Field(default=0.4, ge=0.0, le=1.0)

    # Bollinger Bands thresholds
    bbands_overbought_threshold: float = Field(default=0.1, ge=0.0, le=0.5)
    bbands_oversold_threshold: float = Field(default=0.1, ge=0.0, le=0.5)

    # CCI thresholds
    cci_overbought: float = Field(default=100.0, ge=50.0, le=300.0)
    cci_oversold: float = Field(default=-100.0, ge=-300.0, le=-50.0)

    # Direction determination buffer
    direction_buffer: float = Field(default=1.2, ge=1.0, le=3.0)

    # Diversity threshold
    min_diversity_score: float = Field(default=0.5, ge=0.0, le=1.0)


class StrengthEngineConfig(BaseModel):
    """Configuration model for Strength Engine."""

    min_sources: int = 3
    opposition_threshold: float = 0.4
    source_weights: dict[str, float] = Field(default_factory=dict)
    source_adjustments: dict[str, float] = Field(default_factory=dict)
    regime_thresholds: dict[str, float] = Field(default_factory=dict)
    bbands_thresholds: dict[str, float] = Field(default_factory=dict)
    cci_thresholds: dict[str, float] = Field(default_factory=dict)
    direction_buffer: float = 1.2
    min_diversity_score: float = 0.5

    @classmethod
    def from_settings(cls, settings: StrengthEngineSettings) -> "StrengthEngineConfig":
        """Create config from settings."""
        return cls(
            min_sources=settings.min_sources,
            opposition_threshold=settings.opposition_threshold,
            source_weights={
                "ta": settings.ta_weight,
                "sentiment": settings.sentiment_weight,
                "price_action": settings.price_action_weight,
                "volatility": settings.volatility_weight,
                "fundamental": settings.fundamental_weight,
                "ml": settings.ml_weight,
                "options_flow": settings.options_flow_weight,
            },
            source_adjustments={
                "ta": settings.ta_adjustment,
                "sentiment": settings.sentiment_adjustment,
                "price_action": settings.price_action_adjustment,
            },
            regime_thresholds={
                "hurst_trending": settings.hurst_trending_threshold,
                "regime_strong": settings.regime_strong_threshold,
                "hurst_mean_reverting": settings.hurst_mean_reverting_threshold,
            },
            bbands_thresholds={
                "overbought": settings.bbands_overbought_threshold,
                "oversold": settings.bbands_oversold_threshold,
            },
            cci_thresholds={
                "overbought": settings.cci_overbought,
                "oversold": settings.cci_oversold,
            },
            direction_buffer=settings.direction_buffer,
            min_diversity_score=settings.min_diversity_score,
        )


@lru_cache(maxsize=1)
def get_settings() -> StrengthEngineSettings:
    """Get cached settings instance."""
    return StrengthEngineSettings()


@lru_cache(maxsize=1)
def get_config() -> StrengthEngineConfig:
    """Get cached config instance."""
    return StrengthEngineConfig.from_settings(get_settings())
