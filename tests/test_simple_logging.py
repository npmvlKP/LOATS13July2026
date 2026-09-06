"""
Simple test for logging functionality without conftest dependencies.
"""

import logging
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _hermetic_cwd(tmp_path, monkeypatch):
    """Run from a fresh temp cwd: production mode must create logs/ itself.

    The dev host has a pre-existing logs/ directory, which hides the
    contract this pins (2026-09-06 workflow_dispatch run 34021260111:
    'Unable to configure handler file' on a fresh runner).
    """
    monkeypatch.chdir(tmp_path)


def test_logging_test_mode(monkeypatch):
    """Test that logging is configured correctly in test mode."""
    # Set test environment (monkeypatch restores it afterwards)
    monkeypatch.setenv("ENVIRONMENT", "test")

    # Import after setting environment
    from loats.loats_logging import configure_logging

    # Configure logging in test mode
    configure_logging(test_mode=True)

    # Check that no logs directory was created
    assert not Path("logs").exists()

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


def test_logging_production_mode(monkeypatch):
    """Test that logging is configured correctly in production mode."""
    # Remove test environment if set (monkeypatch restores it afterwards)
    monkeypatch.delenv("ENVIRONMENT", raising=False)

    # Import after setting environment
    from loats.loats_logging import configure_logging

    # Configure logging in production mode. The real directory creation is
    # the behavior under test: mocking Path.mkdir away (the old pattern)
    # starves the RotatingFileHandler and dictConfig fails with
    # "Unable to configure handler 'file'" on a fresh environment.
    configure_logging(test_mode=False)

    # Check that the logs directory was created for real
    assert Path("logs").is_dir()

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

    assert len(file_handlers) > 0, (
        "File handler should be configured in production mode"
    )
    assert len(console_handlers) > 0, (
        "Console handler should be configured in production mode"
    )

    # Release the file handles on the temp directory.
    for handler in file_handlers:
        handler.close()
        root_logger.removeHandler(handler)
