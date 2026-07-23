"""
LOATS13July2026 Lite OpenAlgo Trading System
lightweight, production-grade trading system using OpenAlgo APIs.
"""

from __future__ import annotations

__version__ = "0.1.0"
__all__ = [
    "configure_logging",
    "get_logger",
    "get_settings",
    "initialize_system",
    "settings",
]

from .config._settings import get_settings
from .initialization import initialize_system
from .logging import configure_logging, get_logger

# Initialize system when package is imported
initialize_system()

# Get default logger
logger = get_logger("loats")


# Lazy-loaded settings accessor for backward compatibility
# Uses __getattr__ to defer Settings() instantiation until first access
# This preserves lru_cache lazy-init purpose - validation runs on first use, not import
def __getattr__(name: str) -> object:
    if name == "settings":
        return get_settings()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    """Expose ``settings`` to IDEs/introspection alongside ``__all__``."""
    return sorted({*globals().keys(), *__all__})
