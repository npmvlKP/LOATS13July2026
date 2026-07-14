"""
System initialization for LOATS13July2026.
"""

import os

from .logging import configure_logging


def initialize_system() -> None:
    """Initialize the LOATS system.

    This function should be called at application startup to:
    1. Configure logging
    2. Initialize settings
    3. Set up any required directories
    """
    # Configure logging
    if os.environ.get("ENVIRONMENT") == "test":
        configure_logging(test_mode=True)
    else:
        configure_logging()

    # Note: Settings initialization is deferred to avoid circular imports
    # Applications should call settings.initialize() explicitly when needed
