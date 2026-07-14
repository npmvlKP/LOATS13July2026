"""
Simple test for logging functionality without conftest dependencies.
"""

import logging
import os
import sys
from pathlib import Path
from unittest.mock import patch

# Add the src directory to the path
sys.path.insert(0, str(Path(__file__).parent.parent))


def test_logging_test_mode():
    """Test that logging is configured correctly in test mode."""
    # Set test environment
    os.environ["ENVIRONMENT"] = "test"

    # Import after setting environment
    from src.loats.logging import configure_logging

    # Configure logging in test mode
    configure_logging(test_mode=True)

    # Check that no file handlers are configured
    root_logger = logging.getLogger()
    file_handlers = [
        handler
        for handler in root_logger.handlers
        if isinstance(handler, logging.FileHandler)
    ]

    assert len(file_handlers) == 0, "No file handlers should be configured in test mode"

    # Check that console handler is configured
    console_handlers = [
        handler
        for handler in root_logger.handlers
        if isinstance(handler, logging.StreamHandler)
    ]

    assert len(console_handlers) > 0, "Console handler should be configured"

    print("✓ Test mode logging test passed")


def test_logging_production_mode():
    """Test that logging is configured correctly in production mode."""
    # Remove test environment if set
    if "ENVIRONMENT" in os.environ:
        del os.environ["ENVIRONMENT"]

    # Import after setting environment
    from src.loats.logging import configure_logging

    # Mock the Path.mkdir to avoid creating actual directories
    with patch("pathlib.Path.mkdir") as mock_mkdir:
        # Configure logging in production mode
        configure_logging(test_mode=False)

        # Check that mkdir was called to create logs directory
        mock_mkdir.assert_called_once()

        # Check that both console and file handlers are configured
        root_logger = logging.getLogger()
        file_handlers = [
            handler
            for handler in root_logger.handlers
            if isinstance(handler, logging.FileHandler)
        ]
        console_handlers = [
            handler
            for handler in root_logger.handlers
            if isinstance(handler, logging.StreamHandler)
        ]

        assert (
            len(file_handlers) > 0
        ), "File handler should be configured in production mode"
        assert (
            len(console_handlers) > 0
        ), "Console handler should be configured in production mode"

    print("✓ Production mode logging test passed")


if __name__ == "__main__":
    test_logging_test_mode()
    test_logging_production_mode()
    print("All logging tests passed!")
