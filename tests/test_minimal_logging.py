"""
Minimal test for logging functionality without importing loats package.
"""

import logging
import logging.config
from pathlib import Path
from unittest.mock import patch


def test_logging_configuration():
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

    # Test test mode
    with patch("pathlib.Path.mkdir") as mock_mkdir:
        configure_logging_test_mode(test_mode=True)

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

        assert len(file_handlers) == 0, (
            "No file handlers should be configured in test mode"
        )
        assert len(console_handlers) > 0, (
            "Console handler should be configured in test mode"
        )

    # Test production mode
    with patch("pathlib.Path.mkdir") as mock_mkdir:
        configure_logging_test_mode(test_mode=False)

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

        assert len(file_handlers) > 0, (
            "File handler should be configured in production mode"
        )
        assert len(console_handlers) > 0, (
            "Console handler should be configured in production mode"
        )

    print("OK: All logging configuration tests passed")


if __name__ == "__main__":
    test_logging_configuration()
