"""
Minimal test for logging functionality without importing loats package.
"""

import logging
import logging.config
from pathlib import Path


def test_logging_configuration(tmp_path, monkeypatch):
    """Test logging configuration with test_mode parameter."""

    # Test 1: Test mode (no file logging)
    def configure_logging_test_mode(test_mode: bool = False) -> None:
        """Configure logging with test_mode parameter."""
        # Create logs directory if it doesn't exist (unless in test mode)
        if not test_mode:
            log_dir = Path("logs")
            log_dir.mkdir(exist_ok=True)

        # Configure handlers
        handlers = {
            "default": {
                "level": "INFO",
                "class": "logging.StreamHandler",
                "formatter": "plain",
            },
        }

        # Add file handler only if not in test mode
        if not test_mode:
            handlers["file"] = {
                "level": "INFO",
                "class": "logging.handlers.RotatingFileHandler",
                "filename": "logs/loats.log",
                "maxBytes": 10485760,  # 10MB
                "backupCount": 5,
                "formatter": "json",
            }

        logging_config = {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "plain": {
                    "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
                },
                "json": {
                    "format": '{"timestamp": "%(asctime)s", "name": "%(name)s", "level": "%(levelname)s", "message": "%(message)s"}',
                },
            },
            "handlers": handlers,
            "loggers": {
                "": {
                    "handlers": list(handlers.keys()),
                    "level": "INFO",
                    "propagate": False,
                },
            },
        }

        # Apply logging configuration
        logging.config.dictConfig(logging_config)

    # Test test mode in a hermetic cwd: no logs directory may be created
    # (fresh-checkout contract), and only the console handler is configured.
    monkeypatch.chdir(tmp_path)
    configure_logging_test_mode(test_mode=True)

    # Check that no logs directory was created
    assert not Path("logs").exists()

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

    assert len(file_handlers) == 0, "No file handlers should be configured in test mode"
    assert len(console_handlers) > 0, (
        "Console handler should be configured in test mode"
    )

    # Test production mode: the real directory creation is the behavior
    # under test -- mocking Path.mkdir away starves the RotatingFileHandler
    # and dictConfig fails with "Unable to configure handler 'file'" on a
    # fresh environment (no pre-existing logs/ directory).
    configure_logging_test_mode(test_mode=False)

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
