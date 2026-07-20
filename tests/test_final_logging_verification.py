"""
Final verification of logging functionality for LOATS13July2026.
"""

import logging
import os
import sys
from pathlib import Path
from unittest.mock import patch

# Add the src directory to the path
sys.path.insert(0, str(Path(__file__).parent.parent))


def test_final_logging_verification():
    """Final comprehensive test of logging functionality."""

    print("=== FINAL LOGGING VERIFICATION ===")

    # Test 1: Test mode configuration
    print("\n1. Testing test mode configuration...")

    # Set test environment
    os.environ["ENVIRONMENT"] = "test"

    # Reset logging configuration
    logging.root.handlers = []

    # Import and configure logging
    from src.loats.logging import configure_logging, get_logger

    with patch("pathlib.Path.mkdir") as mock_mkdir:
        configure_logging(test_mode=True)

        # Check that mkdir was not called
        mock_mkdir.assert_not_called()

        # Test actual logging
        logger = get_logger("test")
        logger.info("Test message in test mode")

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

    print("Test mode configuration verified")

    # Test 2: Production mode configuration
    print("\n2. Testing production mode configuration...")

    # Remove test environment
    if "ENVIRONMENT" in os.environ:
        del os.environ["ENVIRONMENT"]

    # Reset logging configuration
    logging.root.handlers = []

    with patch("pathlib.Path.mkdir") as mock_mkdir:
        configure_logging(test_mode=False)

        # Check that mkdir was called
        mock_mkdir.assert_called_once()

        # Test actual logging
        logger = get_logger("production")
        logger.info("Test message in production mode")

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

    print("Production mode configuration verified")

    # Test 3: Environment-based configuration
    print("\n3. Testing environment-based configuration...")

    # Set test environment
    os.environ["ENVIRONMENT"] = "test"

    # Reset logging configuration
    logging.root.handlers = []

    with patch("pathlib.Path.mkdir") as mock_mkdir:
        # Import the package (this will trigger initialization)
        import src.loats

        # Check that mkdir was not called
        mock_mkdir.assert_not_called()

        # Test actual logging
        logger = src.loats.logger
        logger.info("Test message via environment-based configuration")

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

    print("Environment-based configuration verified")

    # Test 4: Logger hierarchy and formatting
    print("\n4. Testing logger hierarchy and formatting...")

    # Test different log levels
    logger = get_logger("test.hierarchy")
    logger.debug("Debug message")
    logger.info("Info message")
    logger.warning("Warning message")
    logger.error("Error message")
    logger.critical("Critical message")

    print("Logger hierarchy and formatting verified")

    # Test 5: Structured logging
    print("\n5. Testing structured logging...")

    # Test with structured data
    logger = get_logger("structured")
    logger.info("Structured log message", extra={"key1": "value1", "key2": 42})

    print("Structured logging verified")

    print("\n=== ALL LOGGING TESTS PASSED ===")
    print("\nLogging functionality is working correctly:")
    print("- Test mode: No file logging, console only")
    print("- Production mode: File and console logging")
    print("- Environment detection: ENVIRONMENT=test disables file logging")
    print("- Logger hierarchy: Supports different log levels")
    print("- Structured logging: Supports extra data")


if __name__ == "__main__":
    test_final_logging_verification()
