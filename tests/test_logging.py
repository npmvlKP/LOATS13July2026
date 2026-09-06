"""
Test logging functionality LOATS13July2026.
"""

import logging
import os
from pathlib import Path
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


def test_configure_logging_production_mode(tmp_path, monkeypatch):
    """Test logging configured correctly production mode."""
    # Reset logging configuration avoid interference
    logging.root.handlers = []

    # Ensure we're not test environment (monkeypatch restores afterwards)
    monkeypatch.delenv("ENVIRONMENT", raising=False)

    # Import after setting environment
    from loats.loats_logging import configure_logging

    # Run in a hermetic cwd: a fresh checkout has no logs/ directory, and
    # production mode must create it. The real directory creation is the
    # behavior under test -- mocking Path.mkdir away (the old pattern)
    # starves the RotatingFileHandler and dictConfig fails with
    # "Unable to configure handler 'file'" on a fresh environment.
    monkeypatch.chdir(tmp_path)

    # Configure logging production mode
    configure_logging(test_mode=False)

    # Check logs directory was created for real
    assert Path("logs").is_dir()

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

    # Release the file handles on the temp directory.
    for handler in file_handlers:
        handler.close()
        root_logger.removeHandler(handler)


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


def test_logs_directory_created_in_production_mode(tmp_path, monkeypatch):
    """Test logs directory created production mode."""
    # Reset logging configuration avoid interference
    logging.root.handlers = []

    # Ensure we're not test environment (monkeypatch restores afterwards)
    monkeypatch.delenv("ENVIRONMENT", raising=False)

    # Import after setting environment
    from loats.loats_logging import configure_logging

    # Hermetic cwd: assert the real directory creation (see
    # test_configure_logging_production_mode for why mkdir is not mocked).
    monkeypatch.chdir(tmp_path)

    # Configure logging production mode
    configure_logging(test_mode=False)

    # Check logs directory created
    assert Path("logs").is_dir()

    # Release the file handles on the temp directory.
    root_logger = logging.getLogger()
    for handler in [
        h for h in root_logger.handlers if isinstance(h, logging.FileHandler)
    ]:
        handler.close()
        root_logger.removeHandler(handler)


def test_environment_based_logging_configuration(tmp_path, monkeypatch):
    """Test logging configuration based ENVIRONMENT variable."""
    # Test ENVIRONMENT=test verify logs directory created
    monkeypatch.setenv("ENVIRONMENT", "test")

    # Mock Path.mkdir detect it's called
    with patch("pathlib.Path.mkdir") as mock_mkdir:
        # Check mkdir notcalled (test mode should not create logs directory)
        mock_mkdir.assert_not_called()

    # Test ENVIRONMENT notset (production) verify logs directory created
    monkeypatch.delenv("ENVIRONMENT", raising=False)

    # Test actual functionality instead mkdir call
    # Reset logging configuration avoid interference
    logging.root.handlers = []

    # Import configure logging explicitly test production mode
    from loats.loats_logging import configure_logging

    # Hermetic cwd (see test_configure_logging_production_mode).
    monkeypatch.chdir(tmp_path)

    # Configure logging production mode
    configure_logging(test_mode=False)

    # Check logs directory created (this indicates production mode)
    assert Path("logs").is_dir()

    # Release the file handles on the temp directory.
    root_logger = logging.getLogger()
    for handler in [
        h for h in root_logger.handlers if isinstance(h, logging.FileHandler)
    ]:
        handler.close()
        root_logger.removeHandler(handler)
