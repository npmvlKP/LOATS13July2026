"""Configuration package for LOATS13July2026."""

from ._settings import Settings, get_settings

__all__ = ["Settings", "get_settings"]


def __getattr__(name: str) -> object:
    """Lazy loading for settings instance."""
    if name == "settings":
        return get_settings()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
