"""
LOATS13July2026 - Lite OpenAlgo Trading System

A lightweight, production-grade trading system using OpenAlgo APIs.
"""

__version__ = "0.1.0"
__all__ = ["settings", "configure_logging", "get_logger", "logger"]

from .initialization import initialize_system
from .logging import get_logger

# Initialize the system when the package is imported
initialize_system()

# Get the default logger
logger = get_logger("loats")
