"""
LOATS13July2026 Lite OpenAlgo Trading System
lightweight, production-grade trading system using OpenAlgo APIs.
"""

__version__ = "0.1.0"
__all__ = ["configure_logging", "get_logger", "logger", "settings"]

from .config.settings import settings
from .initialization import initialize_system
from .logging import configure_logging, get_logger

# Initialize system when package is imported
initialize_system()

# Get default logger
logger = get_logger("loats")

