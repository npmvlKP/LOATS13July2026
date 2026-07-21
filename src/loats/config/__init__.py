"""Configuration package for LOATS13July2026."""

from ._settings import Settings, get_settings

__all__ = ["Settings", "get_settings", "settings"]

# Pre-initialize settings at module load time.
# With pydantic SettingsConfigDict(extra="ignore"), missing .env won't cause errors.
# This provides proper type information for mypy instead of using __getattr__.
settings: Settings = get_settings()
