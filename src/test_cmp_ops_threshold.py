"""Test CMP OPS threshold compliance."""
import asyncio
import os
from unittest.mock import patch

import pytest

from src.loats.config import get_settings
from src.loats.utils.rate_limiter import (
    get_order_rate_limiter,
    get_smart_order_rate_limiter,
    get_sync_order_rate_limiter,
    get_sync_smart_order_rate_limiter,
    _reset_singletons_for_testing,
)

@pytest.fixture
def setup_env():
    """Set up environment for testing."""
    # Set required environment variable
    os.environ["OPENALGO_API_KEY"] = "test_key"
    # Reset singletons before each test
    _reset_singletons_for_testing()
    yield
    # Clean up
    del os.environ["OPENALGO_API_KEY"]
    _reset_singletons_for_testing()

def test_settings_max_ops():
    """Test that settings.max_ops is correctly set to 3."""
    settings = get_settings()
    assert settings.max_ops == 3, f"Expected max_ops=3, got {settings.max_ops}"

async def test_async_order_rate_limiter_uses_settings(setup_env):
    """Test that async order rate limiter uses settings.max_ops."""
    # Reset singletons to ensure clean state
    _reset_singletons_for_testing()

    # Get the default rate limiter (should use settings.max_ops)
    rate_limiter = get_order_rate_limiter()

    # Verify it uses the correct max_ops from settings
    settings = get_settings()
    assert rate_limiter.max_ops == settings.max_ops, \
        f"Expected rate_limiter.max_ops={settings.max_ops}, got {rate_limiter.max_ops}"

async def test_async_smart_order_rate_limiter_uses_settings(setup_env):
    """Test that async smart order rate limiter uses settings.max_ops."""
    # Reset singletons to ensure clean state
    _reset_singletons_for_testing()

    # Get the default rate limiter (should use settings.max_ops)
    rate_limiter = get_smart_order_rate_limiter()

    # Verify it uses the correct max_ops from settings
    settings = get_settings()
    assert rate_limiter.max_ops == settings.max_ops, \
        f"Expected rate_limiter.max_ops={settings.max_ops}, got {rate_limiter.max_ops}"

def test_sync_order_rate_limiter_uses_settings(setup_env):
    """Test that sync order rate limiter uses settings.max_ops."""
    # Reset singletons to ensure clean state
    _reset_singletons_for_testing()

    # Get the default rate limiter (should use settings.max_ops)
    rate_limiter = get_sync_order_rate_limiter()

    # Verify it uses the correct max_ops from settings
    settings = get_settings()
    assert rate_limiter.max_ops == settings.max_ops, \
        f"Expected rate_limiter.max_ops={settings.max_ops}, got {rate_limiter.max_ops}"

def test_sync_smart_order_rate_limiter_uses_settings(setup_env):
    """Test that sync smart order rate limiter uses settings.max_ops."""
    # Reset singletons to ensure clean state
    _reset_singletons_for_testing()

    # Get the default rate limiter (should use settings.max_ops)
    rate_limiter = get_sync_smart_order_rate_limiter()

    # Verify it uses the correct max_ops from settings
    settings = get_settings()
    assert rate_limiter.max_ops == settings.max_ops, \
        f"Expected rate_limiter.max_ops={settings.max_ops}, got {rate_limiter.max_ops}"

async def test_order_rate_limiter_enforces_max_ops(setup_env):
    """Test that order rate limiter enforces the max_ops limit."""
    # Reset singletons to ensure clean state
    _reset_singletons_for_testing()

    rate_limiter = get_order_rate_limiter()
    settings = get_settings()

    # Test that we can acquire exactly max_ops tokens
    acquired = []
    for _ in range(settings.max_ops):
        result = await rate_limiter.acquire()
        acquired.append(result)
        assert result is True, f"Failed to acquire token {len(acquired)}"

    # The next acquisition should fail
    result = await rate_limiter.acquire()
    assert result is False, "Should not be able to acquire more than max_ops tokens"

    # Verify we got exactly max_ops successful acquisitions
    assert sum(acquired) == settings.max_ops, \
        f"Expected {settings.max_ops} successful acquisitions, got {sum(acquired)}"

async def test_smart_order_rate_limiter_enforces_max_ops(setup_env):
    """Test that smart order rate limiter enforces the max_ops limit."""
    # Reset singletons to ensure clean state
    _reset_singletons_for_testing()

    rate_limiter = get_smart_order_rate_limiter()
    settings = get_settings()

    # Test that we can acquire exactly max_ops tokens
    acquired = []
    for _ in range(settings.max_ops):
        result = await rate_limiter.acquire()
        acquired.append(result)
        assert result is True, f"Failed to acquire token {len(acquired)}"

    # The next acquisition should fail
    result = await rate_limiter.acquire()
    assert result is False, "Should not be able to acquire more than max_ops tokens"

    # Verify we got exactly max_ops successful acquisitions
    assert sum(acquired) == settings.max_ops, \
        f"Expected {settings.max_ops} successful acquisitions, got {sum(acquired)}"

def test_cmp_rule_4_compliance():
    """Test CMP Rule 4: OPS threshold 10; self-limit ≤3."""
    settings = get_settings()

    # Verify the setting is ≤3 (self-limit)
    assert settings.max_ops <= 3, \
        f"CMP Rule 4 violated: max_ops={settings.max_ops} should be ≤3"

    # Verify the setting is ≤10 (NSE threshold)
    assert settings.max_ops <= 10, \
        f"CMP Rule 4 violated: max_ops={settings.max_ops} should be ≤10"

    # Verify it's exactly 3 as configured
    assert settings.max_ops == 3, \
        f"Expected max_ops=3 for CMP compliance, got {settings.max_ops}"

async def test_rate_limiter_singleton_behavior(setup_env):
    """Test that rate limiter singletons work correctly."""
    # Reset singletons to ensure clean state
    _reset_singletons_for_testing()

    # Get two instances of the same rate limiter
    limiter1 = get_order_rate_limiter()
    limiter2 = get_order_rate_limiter()

    # They should be the same instance (singleton)
    assert limiter1 is limiter2, "Rate limiter should be a singleton"

    # Both should have the same max_ops from settings
    settings = get_settings()
    assert limiter1.max_ops == settings.max_ops
    assert limiter2.max_ops == settings.max_ops

if __name__ == "__main__":
    # Run the tests
    pytest.main([__file__, "-v"])