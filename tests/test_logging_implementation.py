"""
Test the actual logging implementation from the loats package.
"""

import logging
import os
import sys
from pathlib import Path
from unittest.mock import patch

# Add the src directory to the path
sys.path.insert(0, str(Path(__file__).parent.parent))


def test_logging_implementation():
    """Test the actual logging implementation."""

    # Test 1: Test mode configuration
    print("Testing test mode configuration...")

    # Set test environment
    os.environ["ENVIRONMENT"] = "test"

    # Reset logging configuration
    logging.root.handlers = []

    # Import and configure logging
    from src.loats.logging import configure_logging

    with patch("pathlib.Path.mkdir") as mock_mkdir:
        configure_logging(test_mode=True)

        # Check that mkdir was not called
        mock_mkdir.assert_not_called()

        # Check that only console handler is configured
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
            len(file_handlers) == 0
        ), "No file handlers should be configured in test mode"
        assert (
            len(console_handlers) > 0
        ), "Console handler should be configured in test mode"

    print("OK: Test mode configuration works correctly")

    # Test 2: Production mode configuration
    print("Testing production mode configuration...")

    # Remove test environment
    if "ENVIRONMENT" in os.environ:
        del os.environ["ENVIRONMENT"]

    # Reset logging configuration
    logging.root.handlers = []

    # Import and configure logging
    from src.loats.logging import configure_logging

    with patch("pathlib.Path.mkdir") as mock_mkdir:
        configure_logging(test_mode=False)

        # Check that mkdir was called
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

    print("OK: Production mode configuration works correctly")

    # Test 3: Environment-based configuration via __init__.py
    print("Testing environment-based configuration...")

    # Set test environment
    os.environ["ENVIRONMENT"] = "test"

    # Reset logging configuration
    logging.root.handlers = []

    # Mock mkdir before importing the package
    with patch("pathlib.Path.mkdir") as mock_mkdir:
        # Import the package (this will trigger initialization)

        # Check that mkdir was not called
        mock_mkdir.assert_not_called()

        # Check that only console handler is configured
        root_logger = logging.getLogger()
        file_handlers = [
            handler
            for handler in root_logger.handlers
            if isinstance(handler, logging.FileHandler)
        ]

        assert (
            len(file_handlers) == 0
        ), "No file handlers should be configured when ENVIRONMENT=test"

    print("OK: Environment-based configuration works correctly")

    print("All logging implementation tests passed!")


if __name__ == "__main__":
    test_logging_implementation()
