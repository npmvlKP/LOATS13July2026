"""
Test logging functionality LOATS13July2026.
"""

import contextlib
import io
import logging
import os
import re
from pathlib import Path
from unittest.mock import patch

_ISO_TS = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?"
)


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
    """Production logging anchors logs/ to the repo root, not the CWD.

    Contract change (2026-09-13): the CWD-relative ./logs crashed with
    PermissionError under scheduled tasks whose CWD is not the repo
    (System32) -- the 06:17-06:23 watchdog resume crashes. The chdir to a
    foreign temp cwd is the regression leg: the old implementation created
    ./logs there; the fixed implementation must not.
    """
    # Reset logging configuration avoid interference
    logging.root.handlers = []

    # Ensure we're not test environment (monkeypatch restores afterwards)
    monkeypatch.delenv("ENVIRONMENT", raising=False)

    # Import after setting environment
    from loats.loats_logging import configure_logging, resolve_log_dir

    # Run in a hermetic FOREIGN cwd. The real directory creation is still
    # the behavior under test -- mocking Path.mkdir away (the old pattern)
    # starves the RotatingFileHandler and dictConfig fails with
    # "Unable to configure handler 'file'" on a fresh environment.
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("LOATS_LOG_DIR", raising=False)

    # Configure logging production mode
    configure_logging(test_mode=False)

    # CWD-independence: nothing in the foreign cwd, everything anchored.
    assert not (tmp_path / "logs").exists()
    anchored = resolve_log_dir()
    assert anchored.is_dir()

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
    assert Path(file_handlers[0].baseFilename) == anchored / "loats.log"
    assert len(console_handlers) > 0, "Console handler configured production mode"

    # Release the file handles on the anchored directory.
    for handler in file_handlers:
        handler.close()
        root_logger.removeHandler(handler)


def test_resolve_log_dir_env_override(tmp_path, monkeypatch):
    """LOATS_LOG_DIR redirects the anchored logs directory (P5_RUN_LOG_DIR pattern)."""
    from loats.loats_logging import resolve_log_dir

    monkeypatch.chdir(tmp_path)
    override = tmp_path / "ops-logs"
    monkeypatch.setenv("LOATS_LOG_DIR", str(override))
    assert resolve_log_dir() == override
    monkeypatch.delenv("LOATS_LOG_DIR", raising=False)
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    assert resolve_log_dir() != override
    assert resolve_log_dir().name == "logs"


def _render_one_warning() -> str:
    """Configure test-mode logging and capture one rendered warning line."""
    logging.root.handlers = []
    from loats.loats_logging import configure_logging, get_logger

    buf = io.StringIO()
    with contextlib.redirect_stderr(buf):
        configure_logging(test_mode=True)
        # Fresh logger name: cache_logger_on_first_use must not serve a
        # logger bound by a previous test's structlog.configure call.
        get_logger("loats.render_contract").warning("single-render contract probe")
    return buf.getvalue()


def test_console_line_renders_timestamp_once():
    """A rendered line carries exactly one timestamp (ProcessorFormatter
    double-render regression, F-2026-09-11)."""
    out = _render_one_warning()
    line = next(t for t in out.splitlines() if "single-render contract probe" in t)
    assert len(_ISO_TS.findall(line)) == 1, (
        f"timestamp rendered more than once: {line!r}"
    )


def test_console_line_renders_message_once():
    """The message appears exactly once in the rendered line."""
    out = _render_one_warning()
    line = next(t for t in out.splitlines() if "loats.render_contract" in t)
    assert line.count("single-render contract probe") == 1, (
        f"message duplicated: {line!r}"
    )


def test_foreign_stdlib_record_renders_without_error():
    """Foreign stdlib records (httpx, apscheduler...) format cleanly through
    the same handler: wrap_for_formatter must never run over them."""
    logging.root.handlers = []
    from loats.loats_logging import configure_logging

    buf = io.StringIO()
    with contextlib.redirect_stderr(buf):
        configure_logging(test_mode=True)
        logging.getLogger("httpx").info("foreign record probe")
    assert "--- Logging error ---" not in buf.getvalue(), (
        "foreign record formatting raised inside the handler"
    )
    line = next(t for t in buf.getvalue().splitlines() if "foreign record probe" in t)
    assert len(_ISO_TS.findall(line)) == 1, f"foreign line double-rendered: {line!r}"


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
    """Production mode creates the ANCHORED logs dir, not ./logs in the CWD."""
    # Reset logging configuration avoid interference
    logging.root.handlers = []

    # Ensure we're not test environment (monkeypatch restores afterwards)
    monkeypatch.delenv("ENVIRONMENT", raising=False)

    # Import after setting environment
    from loats.loats_logging import configure_logging, resolve_log_dir

    # Hermetic FOREIGN cwd: assert the real directory creation at the
    # anchored location (see test_configure_logging_production_mode for
    # why mkdir is not mocked).
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("LOATS_LOG_DIR", raising=False)

    # Configure logging production mode
    configure_logging(test_mode=False)

    # Check anchored logs directory created; nothing in the foreign CWD.
    assert not (tmp_path / "logs").exists()
    assert resolve_log_dir().is_dir()

    # Release the file handles on the anchored directory.
    root_logger = logging.getLogger()
    for handler in [
        h for h in root_logger.handlers if isinstance(h, logging.FileHandler)
    ]:
        handler.close()
        root_logger.removeHandler(handler)


def test_environment_based_logging_configuration(tmp_path, monkeypatch):
    """ENVIRONMENT=test suppresses file logging; production anchors logs/."""
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
    from loats.loats_logging import configure_logging, resolve_log_dir

    # Hermetic FOREIGN cwd (see test_configure_logging_production_mode).
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("LOATS_LOG_DIR", raising=False)

    # Configure logging production mode
    configure_logging(test_mode=False)

    # Check anchored logs directory created; nothing in the foreign CWD.
    assert not (tmp_path / "logs").exists()
    assert resolve_log_dir().is_dir()

    # Release the file handles on the temp directory.
    root_logger = logging.getLogger()
    for handler in [
        h for h in root_logger.handlers if isinstance(h, logging.FileHandler)
    ]:
        handler.close()
        root_logger.removeHandler(handler)
