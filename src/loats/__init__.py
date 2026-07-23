"""
LOATS13July2026 Lite OpenAlgo Trading System
lightweight, production-grade trading system using OpenAlgo APIs.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

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


if TYPE_CHECKING:
    # Static-typing only: declare ``settings`` as a module-level attribute
    # typed as the *Settings instance type*. This lets mypy resolve
    # ``settings.sqlite_db_path`` etc. to the concrete fields of Settings.
    # At runtime, ``settings`` is provided lazily by PEP 562 ``__getattr__``.
    from .config._settings import Settings

    settings: Settings


# Lazy-loaded settings accessor for backward compatibility
# Uses __getattr__ to defer Settings() instantiation until first access
# This preserves lru_cache lazy-init purpose - validation runs on first use, not import
#
# NOTE: signature return type must NOT be ``object`` (would erase the Settings
# type and surface ``"object" has no attribute ...`` errors at every consumer).
# ``Any`` keeps the static type generic, so mypy re-resolves attribute access
# at the call site against the runtime proxy.
def __getattr__(name: str) -> Any:
    if name == "settings":
        return get_settings()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    """Expose ``settings`` to IDEs/introspection alongside ``__all__``."""
    return sorted({*globals().keys(), *__all__})
