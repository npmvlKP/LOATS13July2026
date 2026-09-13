"""
Logging configuration LOATS13July2026 using structlog.
"""

import logging
import logging.config
import os
from pathlib import Path
from typing import Any

import structlog
from structlog.types import Processor

# Repo root anchor for file logging: src/loats/loats_logging.py -> parents[2].
# Never resolve log paths against the CWD: scheduled tasks (LOATS_P5_Watchdog
# -> p5_resume_wrapper.cmd) run with System32 as CWD, and the previous
# CWD-relative ./logs crashed every resume attempt with PermissionError
# (WinError 5) on 2026-09-13 06:17-06:23 IST.
_REPO_ROOT = Path(__file__).resolve().parents[2]


def resolve_log_dir() -> Path:
    """Return the anchored logs directory for file logging.

    Anchored to the repository root via this module's location, never the
    CWD. ``LOATS_LOG_DIR`` overrides (same pattern as ``P5_RUN_LOG_DIR``)
    for ops wrappers and tests; the override is returned verbatim (created
    by the caller on demand).
    """
    override = os.environ.get("LOATS_LOG_DIR")
    if override:
        return Path(override)
    return _REPO_ROOT / "logs"


def configure_logging(test_mode: bool = False) -> None:
    """Configure structured logging for LOATS using structlog.

    Args:
        test_mode: If True, disables file logging for test environments.
    """
    # Create the anchored logs directory if it doesn't exist (unless in
    # test mode). resolve_log_dir() is CWD-independent; parents=True keeps
    # a LOATS_LOG_DIR override naming a deeper path creatable.
    if not test_mode:
        log_dir = resolve_log_dir()
        log_dir.mkdir(parents=True, exist_ok=True)

    # Shared processors for both console and file logging. These PREPARE
    # each event (context, logger name, level, timestamp, exc info); the
    # final renderer lives ONLY in the handlers' ProcessorFormatter below.
    # This list is also the handlers' foreign_pre_chain, so it must NOT
    # contain wrap_for_formatter (that terminator is for structlog-native
    # events only -- running it over foreign stdlib records corrupts them
    # into tuples).
    #
    # Defect fixed here (F-2026-09-11): configure_logging previously ended
    # structlog's chain with a ConsoleRenderer while the handler's
    # ProcessorFormatter rendered the result a second time, so every line
    # in reports/p5_supervisor.log carried its timestamp/level/logger
    # rendered twice.
    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    # Configure structlog FIRST (before dictConfig).
    # The chain ENDS with ProcessorFormatter.wrap_for_formatter: it hands the
    # prepared event dict to the stdlib handlers, whose ProcessorFormatter
    # (dictConfig below) performs the one and only rendering. A renderer in
    # this chain would render the event before the handler renders it again.
    structlog.configure(
        processors=shared_processors
        + [
            # Final processor: mark the event as prepared and hand it to
            # the stdlib handler's ProcessorFormatter for rendering.
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # Configure handlers
    handlers: dict[str, dict[str, Any]] = {
        "default": {
            "level": "INFO",
            "class": "logging.StreamHandler",
            "formatter": "plain",
        }
    }

    # Add file handler only if not in test mode. The filename is ABSOLUTE:
    # dictConfig resolves a relative filename against the CWD, which
    # recreates the CWD-dependence the anchored directory just removed.
    if not test_mode:
        handlers["file"] = {
            "level": "INFO",
            "class": "logging.handlers.RotatingFileHandler",
            "filename": str(resolve_log_dir() / "loats.log"),
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
                "keep_stack_info": True,
                "use_get_message": False,
            },
            "json": {
                "()": structlog.stdlib.ProcessorFormatter,
                "processor": structlog.processors.JSONRenderer(),
                "foreign_pre_chain": shared_processors,
                "keep_stack_info": True,
                "use_get_message": False,
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

    # Apply logging configuration AFTER structlog.configure
    # This ensures handlers are set up properly with structlog integration
    logging.config.dictConfig(logging_config)


def get_logger(name: str) -> Any:
    """Get a configured logger with the given name."""
    return structlog.get_logger(name)


# Initialize default logger
logger = get_logger("loats")
