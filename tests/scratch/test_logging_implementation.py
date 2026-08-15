"""
Test actual logging implementation loats package.
"""

import logging
import os
import sys
from pathlib import Path
from unittest.mock import patch

# Add src directory path
sys.path.insert(0, str(Path(__file__).parent.parent))

from loats.loats_logging import configure_logging


def test_logging_implementation():
    """Test actual logging implementation."""

    # Test 1: Test mode configuration
    print("Testing test mode configuration...")

    # Set test environment
    os.environ["ENVIRONMENT"] = "test"

    # Reset logging configuration
    logging.root.handlers = []

    # Import configure logging
    # (Using the imported function)

    with patch("pathlib.Path.mkdir") as mock_mkdir:
        configure_logging(test_mode=True)

        # Check mkdir not called
        mock_mkdir.assert_not_called()

    # Check only console handler configured
    root_logger = logging.getLogger()
    file_handlers = [
        h for h in root_logger.handlers if isinstance(h, logging.FileHandler)
    ]
    console_handlers = [
        h for h in root_logger.handlers if isinstance(h, logging.StreamHandler)
    ]

    assert len(file_handlers) == 0, "No file handlers configured in test mode"
    assert len(console_handlers) > 0, (
        "Console handler should be configured in test mode"
    )

    print("OK: Test mode configuration works correctly")

    # Test 2: Production mode configuration
    print("Testing production mode configuration...")

    # Remove test environment
    if "ENVIRONMENT" in os.environ:
        del os.environ["ENVIRONMENT"]

    # Reset logging configuration
    logging.root.handlers = []

    # Import configure logging (already imported)

    with patch("pathlib.Path.mkdir") as mock_mkdir:
        configure_logging(test_mode=False)

        # Check mkdir called
        mock_mkdir.assert_called_once()

    # Check both console and file handlers configured
    root_logger = logging.getLogger()
    file_handlers = [
        h for h in root_logger.handlers if isinstance(h, logging.FileHandler)
    ]
    console_handlers = [
        h for h in root_logger.handlers if isinstance(h, logging.StreamHandler)
    ]

    assert len(file_handlers) > 0, (
        "File handler should be configured in production mode"
    )
    assert len(console_handlers) > 0, (
        "Console handler should be configured in production mode"
    )

    print("OK: Production mode configuration works correctly")

    print("All logging implementation tests passed!")


if __name__ == "__main__":
    test_logging_implementation()
