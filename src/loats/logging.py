"""
Logging configuration for LOATS13July2026 using structlog.
"""

import logging
import logging.config
from pathlib import Path
from typing import Any

import structlog
from structlog.types import Processor


def configure_logging(test_mode: bool = False) -> None:
    """Configure structured logging with structlog.

    Args:
        test_mode: If True, disables file logging for test environments
    """
    # Create logs directory if it doesn't exist (unless in test mode)
    if not test_mode:
        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)

    # Shared processors for both console and file logging
    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

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

    logging_config: dict[str, Any] = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "plain": {
                "()": structlog.stdlib.ProcessorFormatter,
                "processor": structlog.dev.ConsoleRenderer(colors=False),
                "foreign_pre_chain": shared_processors,
            },
            "json": {
                "()": structlog.stdlib.ProcessorFormatter,
                "processor": structlog.processors.JSONRenderer(),
                "foreign_pre_chain": shared_processors,
            },
        },
        "handlers": handlers,
        "loggers": {
            "": {
                "handlers": list(handlers.keys()),
                "level": "INFO",
                "propagate": False,
            },
            "loats": {
                "handlers": list(handlers.keys()),
                "level": "INFO",
                "propagate": False,
            },
        },
    }

    # Apply logging configuration
    logging.config.dictConfig(logging_config)

    # Configure structlog
    structlog.configure(
        processors=shared_processors
        + [
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Get a configured logger with the given name."""
    return structlog.get_logger(name)


# Initialize the default logger
logger = get_logger("loats")
