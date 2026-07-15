"""Configuration package for LOATS13July2026."""

from .settings import Settings, settings


def get_settings() -> Settings:
    """Get the global settings instance."""
    return settings


__all__ = ["Settings", "get_settings", "settings"]
