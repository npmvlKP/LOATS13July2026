"""Pytest configuration fixtures LOATS13July2026."""

from __future__ import annotations

import collections.abc
import datetime
import gc
import os
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

# Set test environment variables BEFORE importing any loats modules.
# database.py creates a module-level singleton that calls get_settings(),
# which requires OPENALGO_API_KEY. pytest_configure runs too late
# (after conftest imports), so env vars must be set here at module scope.
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("OPENALGO_API_KEY", "test_api_key")
os.environ.setdefault("OPENALGO_BASE_URL", "https://test.openalgo.com")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test_bot_token")
os.environ.setdefault("TELEGRAM_CHAT_ID", "123456789")
# Adopt the documented F8-L-06 suppression knob so the benign newspaper4k
# "nltk is not installed" UserWarning does not fire during the suite (the
# optional [nlp] extra is intentionally not installed here). The suppression
# regression tests copy os.environ and control the knob explicitly, so both
# sides of their contract stay observable.
os.environ.setdefault("LOATS_SUPPRESS_NLTK_WARNING", "1")

# F8-H-01 test isolation (2026-09-07, hard fail-closed): the ``db`` singleton
# inside the loats process under test binds ``Settings.sqlite_db_path`` /
# ``audit_log_path``. Tests that patch collaborators but not that singleton
# wrote 186 production audit rows (test-fixture analyzer responses in
# data/audit.log) and production trade_decisions. The suite therefore pins
# BOTH paths to a private temp directory with a HARD override (not
# setdefault): a stray real path in the environment must lose in tests.
# Prod data lives only where the supervisor/process env points it.
_TEST_DATA_DIR = Path(tempfile.mkdtemp(prefix="loats-test-data-"))
os.environ["SQLITE_DB_PATH"] = str(_TEST_DATA_DIR / "test_loats.db")
os.environ["AUDIT_LOG_PATH"] = str(_TEST_DATA_DIR / "test_audit.log")

# 2026-09-11 pre-push incident (git-env redirection hermeticity): git
# exports GIT_DIR / GIT_INDEX_FILE / GIT_WORK_TREE into hook subprocesses
# (upstream pre-commit ships no_git_env() for exactly this reason), and
# any fixture git call scoped by cwd= alone then re-targets the live
# worktree instead of its disposable clone. Hard-scrub the redirection
# triplet before any loats import; pinned by
# TestGitEnvRedirectionHermeticity in tests/test_repo_hygiene.py.
# Literal per-variable pops (not a loop) so the pinning net can anchor on
# the exact statements:
os.environ.pop("GIT_DIR", None)
os.environ.pop("GIT_INDEX_FILE", None)
os.environ.pop("GIT_WORK_TREE", None)

# Coverage mutual-exclusion guard (2026-09-13 incident). Every coverage
# writer in this repo -- manual ``pytest --cov`` runs, CI's
# pytest-coverage job, the pre-push pytest hook, and the embedded
# full-suite runs of scripts/verify_coverage_full.py,
# fr7_health_check.py (HC-12) and verify_hc_all.py -- is a pytest
# process, so THIS conftest is the single choke point for the class.
# pytest-cov writes a per-process parallel data file
# (.coverage.<host>.<pid>.<rand>) and combines every sibling file at
# session end; two concurrent writers make one combine() sweep the
# other's still-open file, which on Windows dies with
# ``PermissionError: [WinError 32]`` as a pytest INTERNALERROR (live
# 2026-09-13: 1815 passed, then the verdict was lost at combine time,
# and the surviving green run overwrote .pytest_cache lastfailed so the
# lost run's single real failure became unidentifiable). A --cov run
# therefore takes an exclusive cross-process lock for the whole session
# or is refused fail-closed (exit code 4) BEFORE any test runs.
# The lock file lives in .git/: invisible to status by construction
# (the tracked-file ceiling sits at zero headroom; no slot is spent),
# and on the same drive as the data it guards.
COV_LOCK_ENABLED = os.environ.get("LOATS_COV_LOCK_DISABLED") != "1"
import sys  # conftest env-first layout; E402 granted per-file in pyproject

if sys.platform == "win32":
    import msvcrt
else:
    import fcntl

# Module-global handle: a pytest_configure local would be garbage
# collected when the hook returns, closing the file and silently
# releasing the OS lock after the first test. Held for the interpreter
# lifetime; the OS reclaims the lock at process exit on any path.
_COV_LOCK_HANDLE = None


def _cov_lock_path(repo_root: Path) -> Path:
    """Exclusive-lock file for coverage writers (inside .git/: untracked)."""
    return repo_root / ".git" / "coverage_gate.lock"


def _cov_requested(argv: list[str]) -> bool:
    """True when this pytest invocation requests coverage anywhere.

    Any ``--cov*`` token counts (``--cov``, ``--cov=src``,
    ``--cov-branch``, ``--cov-report=...``), wherever it appears: a run
    that asks for coverage writes coverage data files and participates
    in the combine sweep. False-positive direction is fail-safe (a
    non-coverage run may be refused; a coverage run must never be
    admitted while the gate is held).
    """
    return any(arg.startswith("--cov") for arg in argv)


def _acquire_coverage_lock(lock_path: Path):
    """Take an exclusive cross-process lock; ``None`` when already held.

    msvcrt byte-range lock on Windows, fcntl.flock elsewhere. Returns
    the open binary handle (the lock lives as long as the handle) or
    ``None`` when another coverage writer holds the gate -- or when the
    guard is disabled via ``LOATS_COV_LOCK_DISABLED=1`` (callers gate
    on ``COV_LOCK_ENABLED`` before treating ``None`` as a refusal).
    """
    if not COV_LOCK_ENABLED:
        return None
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    handle = open(lock_path, "a+b")
    try:
        if sys.platform == "win32":
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        return None
    return handle


def _release_coverage_lock(handle) -> None:
    """Unlock and close a lock handle; tolerates a refused (``None``)."""
    if handle is None:
        return
    try:
        if sys.platform == "win32":
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
    finally:
        handle.close()


from loats.database import Database
from loats.models import (
    HistoricalData,
    Order,
    OrderStatus,
    OrderType,
    OrderVariety,
    ProductType,
    Signal,
    SignalType,
    Trade,
    TransactionType,
)

if TYPE_CHECKING:
    from loats.config.settings import Settings

from loats.loats_logging import configure_logging


@pytest.fixture(autouse=True)
def configure_test_logging() -> None:
    """Configure logging test environment."""
    configure_logging(test_mode=True)


@pytest.fixture
def test_settings() -> Settings:
    """Create test settings for temporary paths."""
    from pydantic import SecretStr

    from loats.config.settings import Settings

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        test_settings = Settings(
            environment="test",
            sqlite_db_path=temp_path / "test_loats.db",
            audit_log_path=temp_path / "test_audit.log",
            openalgo_api_key=SecretStr("test_api_key"),
            openalgo_base_url="https://test.openalgo.com",
            telegram_bot_token=SecretStr("test_bot_token"),
            telegram_chat_id="123456789",
        )
        yield test_settings


@pytest.fixture
def db(test_settings) -> collections.abc.Generator[Database, None, None]:
    """Create test database instance."""
    db_instance = Database(
        db_path=test_settings.sqlite_db_path,
        audit_log_path=test_settings.audit_log_path,
    )
    db_instance.retention_days = 30
    db_instance._initialize_database()
    yield db_instance
    db_instance.close()
    gc.collect()


@pytest.fixture
def sample_trade() -> Trade:
    """Create sample trade testing."""
    return Trade(
        symbol="TEST",
        quantity=10,
        entry_price=100.0,
        entry_time=datetime.datetime(2023, 1, 1, 10, 0),
        transaction_type=TransactionType.BUY,
        product_type=ProductType.MIS,
        strategy="test_strategy",
        stop_loss=95.0,
        take_profit=110.0,
        trailing_stop_loss=5.0,
    )


@pytest.fixture
def sample_order() -> Order:
    """Create sample order testing."""
    return Order(
        order_id="test_order_123",
        symbol="TEST",
        quantity=10,
        order_type=OrderType.LIMIT,
        price=100.0,
        variety=OrderVariety.REGULAR,
        transaction_type=TransactionType.BUY,
        product_type=ProductType.MIS,
        status=OrderStatus.OPEN,
        timestamp=datetime.datetime(2023, 1, 1, 10, 0),
        filled_quantity=0,
    )


@pytest.fixture
def sample_signal() -> Signal:
    """Create sample signal testing."""
    return Signal(
        symbol="TEST",
        signal_type=SignalType.BUY,
        strength=0.8,
        timestamp=datetime.datetime(2023, 1, 1, 10, 0),
        indicators={"rsi": 25.0, "macd": 1.5, "supertrend": 99.5},
        confidence=0.85,
        metadata={"scan_type": "ta", "timeframe": "1min"},
    )


@pytest.fixture
def sample_historical_data() -> list[HistoricalData]:
    """Create sample historical data testing."""
    return [
        HistoricalData(
            symbol="TEST",
            timestamp=datetime.datetime(2023, 1, 1, 9, 15),
            open=99.5,
            high=100.5,
            low=99.0,
            close=100.0,
            volume=1000,
            interval="1min",
        ),
        HistoricalData(
            symbol="TEST",
            timestamp=datetime.datetime(2023, 1, 1, 9, 16),
            open=100.0,
            high=101.0,
            low=99.5,
            close=100.5,
            volume=1200,
            interval="1min",
        ),
        HistoricalData(
            symbol="TEST",
            timestamp=datetime.datetime(2023, 1, 1, 9, 17),
            open=100.5,
            high=101.5,
            low=100.0,
            close=101.0,
            volume=1500,
            interval="1min",
        ),
    ]


def pytest_configure(config: pytest.Config) -> None:
    """Pytest configuration hook.

    Env vars are now set at conftest module-scope (above the loats imports)
    to prevent import-time Settings() validation failures.  The assignments
    below are kept as a defensive backstop using setdefault so they never
    accidentally overwrite values injected by a CI pipeline or tox config.

    Coverage mutual-exclusion guard (session scope, before any test
    runs): a --cov invocation acquires the repo-wide exclusive lock or
    refuses fail-closed. Non-coverage runs are never gated; a refused
    re-acquire (this process already holds the lock) proceeds silently.
    """
    os.environ.setdefault("ENVIRONMENT", "test")
    os.environ.setdefault("OPENALGO_API_KEY", "test_api_key")
    os.environ.setdefault("OPENALGO_BASE_URL", "https://test.openalgo.com")
    os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test_bot_token")
    os.environ.setdefault("TELEGRAM_CHAT_ID", "123456789")

    global _COV_LOCK_HANDLE
    if COV_LOCK_ENABLED and _cov_requested(sys.argv):
        repo_root = Path(__file__).resolve().parent.parent
        handle = _acquire_coverage_lock(_cov_lock_path(repo_root))
        if handle is None:
            # pytest.exit is the only sanctioned exit from a hook:
            # sys.exit() here is swallowed by the mainloop and
            # re-raised as an INTERNALERROR with exit code 3.
            pytest.exit(
                "REFUSED: another pytest --cov run is active in this "
                "repo. Concurrent coverage writers corrupt each other's "
                "combine step on Windows (WinError 32); this guard "
                "serializes them. Wait for the active run to finish, or "
                "set LOATS_COV_LOCK_DISABLED=1 to bypass "
                "(single-writer-certain situations only).",
                returncode=4,
            )
        _COV_LOCK_HANDLE = handle
        os.environ["LOATS_COV_LOCK_ACTIVE"] = "1"


@pytest.fixture(autouse=True, scope="function")
async def clear_cache_before_each_test() -> None:
    """Clear cache before each test to prevent stale data."""
    from loats.utils.cache import cache_manager

    if cache_manager._cache:
        await cache_manager.clear()


@pytest.fixture(autouse=True, scope="function")
def reset_metrics_before_each_test() -> None:
    """Reset metrics manager state before each test to ensure isolation."""
    from loats.metrics import MetricsManager

    manager = MetricsManager()
    manager.reset_for_testing()


@pytest.fixture(autouse=True, scope="function")
def reset_circuit_breakers_before_each_test() -> None:
    """Reset circuit breakers state before each test to ensure isolation."""
    from loats.utils.circuit_breaker import (
        OPENALGO_CIRCUIT_BREAKER,
        TELEGRAM_CIRCUIT_BREAKER,
    )

    # Reset both global circuit breakers to ensure test isolation
    OPENALGO_CIRCUIT_BREAKER.reset()
    TELEGRAM_CIRCUIT_BREAKER.reset()


@pytest.fixture(autouse=True, scope="function")
def reset_rate_limiters_before_each_test() -> None:
    """Reset rate limiter singletons before each test to ensure isolation."""
    from loats.utils.rate_limiter import (
        _order_rate_limiter_instance,
        _rate_limiter_lock,
        _smart_order_rate_limiter_instance,
        _smart_rate_limiter_lock,
    )

    # Reset both global rate limiter singletons to ensure test isolation
    with _rate_limiter_lock:
        _order_rate_limiter_instance = None

    with _smart_rate_limiter_lock:
        _smart_order_rate_limiter_instance = None
