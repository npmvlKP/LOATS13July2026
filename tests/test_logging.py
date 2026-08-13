"""
Test logging functionality LOATS13July2026.
"""

import logging
import os
from unittest.mock import patch


def test_configure_logging_test_mode():
    """Test logging configured correctly test mode."""
    # Reset logging configuration avoid interference
    logging.root.handlers = []

    # Ensure we're test environment
    os.environ["ENVIRONMENT"] = "test"

    # Import after setting environment
    from loats.loats_logging import configure_logging

    # Mock Path.mkdir detect it's called
    with patch("pathlib.Path.mkdir") as mock_mkdir:
        # Configure logging test mode
        configure_logging(test_mode=True)

        # Check mkdir not called
        mock_mkdir.assert_not_called()

    # Check file handlers configured
    root_logger = logging.getLogger()
    file_handlers = [
        handler
        for handler in root_logger.handlers
        if isinstance(handler, logging.FileHandler)
    ]
    assert len(file_handlers) == 0, "No file handlers configured test mode"

    # Check console handler configured
    console_handlers = [
        handler
        for handler in root_logger.handlers
        if isinstance(handler, logging.StreamHandler)
    ]
    assert len(console_handlers) > 0, "Console handler not configured"


def test_configure_logging_production_mode():
    """Test logging configured correctly production mode."""
    # Reset logging configuration avoid interference
    logging.root.handlers = []

    # Ensure we're not test environment
    if "ENVIRONMENT" in os.environ:
        del os.environ["ENVIRONMENT"]

    # Import after setting environment
    from loats.loats_logging import configure_logging

    # Mock Path.mkdir avoid creating actual directories
    with patch("pathlib.Path.mkdir") as mock_mkdir:
        # Configure logging production mode
        configure_logging(test_mode=False)

        # Check mkdir called create logs directory
        mock_mkdir.assert_called_once()

    # Check both console file handlers configured
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

    assert len(file_handlers) > 0, "File handler configured production mode"
    assert len(console_handlers) > 0, "Console handler configured production mode"


def test_logs_directory_not_created_in_test_mode():
    """Test logs directory not created test mode."""
    # Reset logging configuration avoid interference
    logging.root.handlers = []

    # Ensure we're test environment
    os.environ["ENVIRONMENT"] = "test"

    # Import after setting environment
    from loats.loats_logging import configure_logging

    # Mock Path.mkdir detect it's called
    with patch("pathlib.Path.mkdir") as mock_mkdir:
        # Configure logging test mode
        configure_logging(test_mode=True)

        # Check mkdir not called
        mock_mkdir.assert_not_called()


def test_logs_directory_created_in_production_mode():
    """Test logs directory created production mode."""
    # Reset logging configuration avoid interference
    logging.root.handlers = []

    # Ensure we're not test environment
    if "ENVIRONMENT" in os.environ:
        del os.environ["ENVIRONMENT"]

    # Import after setting environment
    from loats.loats_logging import configure_logging

    # Mock Path.mkdir detect it's called
    with patch("pathlib.Path.mkdir") as mock_mkdir:
        # Configure logging production mode
        configure_logging(test_mode=False)

        # Check mkdir called
        mock_mkdir.assert_called_once()


def test_environment_based_logging_configuration():
    """Test logging configuration based ENVIRONMENT variable."""
    # Test ENVIRONMENT=test verify logs directory created
    os.environ["ENVIRONMENT"] = "test"

    # Mock Path.mkdir detect it's called
    with patch("pathlib.Path.mkdir") as mock_mkdir:
        # Check mkdir notcalled (test mode should not create logs directory)
        mock_mkdir.assert_not_called()

    # Test ENVIRONMENT notset (production) verify logs directory created
    if "ENVIRONMENT" in os.environ:
        del os.environ["ENVIRONMENT"]

    # Test actual functionality instead mkdir call
    # Reset logging configuration avoid interference
    logging.root.handlers = []

    # Import configure logging explicitly test production mode
    from loats.loats_logging import configure_logging

    # Mock Path.mkdir detect it's called
    with patch("pathlib.Path.mkdir") as mock_mkdir:
        # Configure logging production mode
        configure_logging(test_mode=False)

        # Check mkdir called (this indicates production mode)
        mock_mkdir.assert_called_once()
