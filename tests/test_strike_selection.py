#!/usr/bin/env python3
"""
Comprehensive test suite for strike_selection.py module.

This test file covers the main functionality of the StrikeSelectionEngine
to address the 18.3% coverage issue.
"""

import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

from loats.database import Database
from loats.models import OptionContract, OptionType
from loats.strike_selection import StrikeSelectionEngine, select_strikes


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    with tempfile.TemporaryDirectory() as temp_dir:
        db_path = Path(temp_dir) / "test.db"
        audit_log_path = Path(temp_dir) / "test_audit.jsonl"

        # Initialize database
        db = Database(db_path=db_path, audit_log_path=audit_log_path)
        db._initialize_database()

        yield db

        # Clean up
        db.close_all()


class TestStrikeSelectionUtilities(unittest.IsolatedAsyncioTestCase):
    """Test suite for strike selection utility functions."""

    async def test_select_strikes_function(self):
        """Test the select_strikes function directly."""
        # Create test option chain
        now = datetime.now(UTC)
        option_chain = [
            OptionContract(
                symbol="TEST24JUL100CE",
                strike_price=100.0,
                expiry=now,
                option_type=OptionType.CALL,
                last_price=5.0,
                open_interest=1000,
                volume=500,
                implied_volatility=0.25,
                delta=0.5,
                gamma=0.01,
                theta=-0.05,
                vega=0.1,
                rho=0.05,
                quantity=1,
            ),
            OptionContract(
                symbol="TEST24JUL105CE",
                strike_price=105.0,
                expiry=now,
                option_type=OptionType.CALL,
                last_price=3.0,
                open_interest=800,
                volume=400,
                implied_volatility=0.23,
                delta=0.4,
                gamma=0.008,
                theta=-0.04,
                vega=0.08,
                rho=0.04,
                quantity=1,
            ),
            OptionContract(
                symbol="TEST24JUL95CE",
                strike_price=95.0,
                expiry=now,
                option_type=OptionType.CALL,
                last_price=7.0,
                open_interest=1200,
                volume=600,
                implied_volatility=0.27,
                delta=0.6,
                gamma=0.012,
                theta=-0.06,
                vega=0.12,
                rho=0.06,
                quantity=1,
            ),
        ]

        # Test ATM straddle strategy
        selected = await select_strikes(100.0, option_chain, "atm_straddle", 1, 3)
        assert len(selected) == 3
        assert 100.0 in selected  # ATM strike should be included
        assert 95.0 in selected  # 1 strike below ATM
        assert 105.0 in selected  # 1 strike above ATM

        # Test delta neutral strategy
        with patch(
            "loats.strike_selection.StrikeSelectionEngine._select_delta_neutral_strikes"
        ) as mock_select:
            mock_select.return_value = [100.0, 105.0]
            selected = await select_strikes(100.0, option_chain, "delta_neutral", 1, 2)
            assert len(selected) == 2
            mock_select.assert_called_once()

        # Test OI based strategy
        with patch(
            "loats.strike_selection.StrikeSelectionEngine._select_oi_based_strikes"
        ) as mock_select:
            mock_select.return_value = [95.0, 100.0]
            selected = await select_strikes(100.0, option_chain, "oi_based", 1, 2)
            assert len(selected) == 2
            mock_select.assert_called_once()

        # Test unknown strategy (should default to ATM straddle)
        with patch(
            "loats.strike_selection.StrikeSelectionEngine._select_atm_straddle_strikes"
        ) as mock_select:
            mock_select.return_value = [100.0]
            selected = await select_strikes(
                100.0, option_chain, "unknown_strategy", 1, 1
            )
            assert len(selected) == 1
            mock_select.assert_called_once()

        # Test empty option chain - should return empty list
        selected = await select_strikes(100.0, [], "atm_straddle", 1, 3)
        assert len(selected) == 0


class TestStrikeSelectionEngine(unittest.IsolatedAsyncioTestCase):
    """Test suite for StrikeSelectionEngine."""

    def setUp(self):
        """Set up test fixtures."""
        self.engine = StrikeSelectionEngine()

    async def test_initialize(self):
        """Test engine initialization."""
        assert self.engine is not None
        assert hasattr(self.engine, "_cache")
        # Cache is now SimpleStrikeCache for better performance
        from loats.strike_selection import SimpleStrikeCache

        assert isinstance(self.engine._cache, SimpleStrikeCache)

    async def test_select_strikes_atm_straddle(self):
        """Test ATM straddle strike selection."""
        # Create test option chain (used for type reference only)
        now = datetime.now(UTC)
        _ = [
            OptionContract(
                symbol="TEST24JUL95CE",
                strike_price=95.0,
                expiry=now,
                option_type=OptionType.CALL,
                last_price=7.0,
                open_interest=1200,
                volume=600,
                implied_volatility=0.27,
                delta=0.6,
                gamma=0.012,
                theta=-0.06,
                vega=0.12,
                rho=0.06,
                quantity=1,
            ),
            OptionContract(
                symbol="TEST24JUL100CE",
                strike_price=100.0,
                expiry=now,
                option_type=OptionType.CALL,
                last_price=5.0,
                open_interest=1000,
                volume=500,
                implied_volatility=0.25,
                delta=0.5,
                gamma=0.01,
                theta=-0.05,
                vega=0.1,
                rho=0.05,
                quantity=1,
            ),
            OptionContract(
                symbol="TEST24JUL105CE",
                strike_price=105.0,
                expiry=now,
                option_type=OptionType.CALL,
                last_price=3.0,
                open_interest=800,
                volume=400,
                implied_volatility=0.23,
                delta=0.4,
                gamma=0.008,
                theta=-0.04,
                vega=0.08,
                rho=0.04,
                quantity=1,
            ),
            OptionContract(
                symbol="TEST24JUL110CE",
                strike_price=110.0,
                expiry=now,
                option_type=OptionType.CALL,
                last_price=1.5,
                open_interest=600,
                volume=300,
                implied_volatility=0.21,
                delta=0.3,
                gamma=0.006,
                theta=-0.03,
                vega=0.06,
                rho=0.03,
                quantity=1,
            ),
        ]  # Used for type reference only

        # Test ATM straddle selection
        selected = await self.engine._select_atm_straddle_strikes(
            100.0, [95.0, 100.0, 105.0, 110.0], 1, 3
        )
        assert len(selected) == 3
        assert 100.0 in selected  # ATM strike
        assert 95.0 in selected  # 1 strike below ATM
        assert 105.0 in selected  # 1 strike above ATM

        # Test with wider width
        selected = await self.engine._select_atm_straddle_strikes(
            100.0, [95.0, 100.0, 105.0, 110.0], 2, 5
        )
        assert len(selected) == 4  # Should include 95, 100, 105, 110 (but max 4)
        assert 100.0 in selected
        assert 95.0 in selected
        assert 105.0 in selected
        assert 110.0 in selected

        # Test with underlying price between strikes
        selected = await self.engine._select_atm_straddle_strikes(
            97.5, [95.0, 100.0, 105.0], 1, 3
        )
        assert len(selected) == 2  # Should include 95 and 100 (closest to 97.5)
        assert 95.0 in selected
        assert 100.0 in selected

    async def test_select_strikes_delta_neutral(self):
        """Test delta neutral strike selection."""
        # Create test option chain
        now = datetime.now(UTC)
        option_chain = [
            OptionContract(
                symbol="TEST24JUL95CE",
                strike_price=95.0,
                expiry=now,
                option_type=OptionType.CALL,
                last_price=7.0,
                open_interest=1200,
                volume=600,
                implied_volatility=0.27,
                delta=0.65,
                gamma=0.012,
                theta=-0.06,
                vega=0.12,
                rho=0.06,
                quantity=1,
            ),
            OptionContract(
                symbol="TEST24JUL100CE",
                strike_price=100.0,
                expiry=now,
                option_type=OptionType.CALL,
                last_price=5.0,
                open_interest=1000,
                volume=500,
                implied_volatility=0.25,
                delta=0.5,
                gamma=0.01,
                theta=-0.05,
                vega=0.1,
                rho=0.05,
                quantity=1,
            ),
            OptionContract(
                symbol="TEST24JUL105CE",
                strike_price=105.0,
                expiry=now,
                option_type=OptionType.CALL,
                last_price=3.0,
                open_interest=800,
                volume=400,
                implied_volatility=0.23,
                delta=0.35,
                gamma=0.008,
                theta=-0.04,
                vega=0.08,
                rho=0.04,
                quantity=1,
            ),
            OptionContract(
                symbol="TEST24JUL95PE",
                strike_price=95.0,
                expiry=now,
                option_type=OptionType.PUT,
                last_price=2.0,
                open_interest=800,
                volume=400,
                implied_volatility=0.24,
                delta=-0.35,
                gamma=0.008,
                theta=-0.04,
                vega=0.08,
                rho=-0.04,
                quantity=1,
            ),
            OptionContract(
                symbol="TEST24JUL100PE",
                strike_price=100.0,
                expiry=now,
                option_type=OptionType.PUT,
                last_price=4.0,
                open_interest=1000,
                volume=500,
                implied_volatility=0.26,
                delta=-0.5,
                gamma=0.01,
                theta=-0.05,
                vega=0.1,
                rho=-0.05,
                quantity=1,
            ),
            OptionContract(
                symbol="TEST24JUL105PE",
                strike_price=105.0,
                expiry=now,
                option_type=OptionType.PUT,
                last_price=6.0,
                open_interest=1200,
                volume=600,
                implied_volatility=0.28,
                delta=-0.65,
                gamma=0.012,
                theta=-0.06,
                vega=0.12,
                rho=-0.06,
                quantity=1,
            ),
        ]

        # Test delta neutral selection (target delta = 0)
        selected = await self.engine._select_delta_neutral_strikes(
            100.0, option_chain, 1, 2
        )

        # Should select strikes that create a delta-neutral position
        # For example, 100CE (delta=0.5) + 100PE (delta=-0.5) = net delta 0
        assert len(selected) == 2
        assert 100.0 in selected  # ATM strike should be included

    async def test_select_strikes_oi_based(self):
        """Test open interest based strike selection."""
        # Create test option chain
        now = datetime.now(UTC)
        option_chain = [
            OptionContract(
                symbol="TEST24JUL95CE",
                strike_price=95.0,
                expiry=now,
                option_type=OptionType.CALL,
                last_price=7.0,
                open_interest=1200,
                volume=600,
                implied_volatility=0.27,
                delta=0.6,
                gamma=0.012,
                theta=-0.06,
                vega=0.12,
                rho=0.06,
                quantity=1,
            ),
            OptionContract(
                symbol="TEST24JUL100CE",
                strike_price=100.0,
                expiry=now,
                option_type=OptionType.CALL,
                last_price=5.0,
                open_interest=2000,  # Highest OI
                volume=500,
                implied_volatility=0.25,
                delta=0.5,
                gamma=0.01,
                theta=-0.05,
                vega=0.1,
                rho=0.05,
                quantity=1,
            ),
            OptionContract(
                symbol="TEST24JUL105CE",
                strike_price=105.0,
                expiry=now,
                option_type=OptionType.CALL,
                last_price=3.0,
                open_interest=800,
                volume=400,
                implied_volatility=0.23,
                delta=0.4,
                gamma=0.008,
                theta=-0.04,
                vega=0.08,
                rho=0.04,
                quantity=1,
            ),
            OptionContract(
                symbol="TEST24JUL95PE",
                strike_price=95.0,
                expiry=now,
                option_type=OptionType.PUT,
                last_price=2.0,
                open_interest=800,
                volume=400,
                implied_volatility=0.24,
                delta=-0.35,
                gamma=0.008,
                theta=-0.04,
                vega=0.08,
                rho=-0.04,
                quantity=1,
            ),
            OptionContract(
                symbol="TEST24JUL100PE",
                strike_price=100.0,
                expiry=now,
                option_type=OptionType.PUT,
                last_price=4.0,
                open_interest=1500,  # Second highest OI
                volume=500,
                implied_volatility=0.26,
                delta=-0.5,
                gamma=0.01,
                theta=-0.05,
                vega=0.1,
                rho=-0.05,
                quantity=1,
            ),
            OptionContract(
                symbol="TEST24JUL105PE",
                strike_price=105.0,
                expiry=now,
                option_type=OptionType.PUT,
                last_price=6.0,
                open_interest=1000,
                volume=600,
                implied_volatility=0.28,
                delta=-0.65,
                gamma=0.012,
                theta=-0.06,
                vega=0.12,
                rho=-0.06,
                quantity=1,
            ),
        ]

        # Test OI based selection
        selected = await self.engine._select_oi_based_strikes(100.0, option_chain, 1, 2)

        # Should select strikes with highest open interest
        assert len(selected) == 2
        assert 100.0 in selected  # Highest OI for calls
        # Could also include 100.0 (second highest OI for puts) or 95.0 (highest OI for puts)

    async def test_select_strikes_caching(self):
        """Test strike selection caching."""
        # Create test option chain
        now = datetime.now(UTC)
        option_chain = [
            OptionContract(
                symbol="TEST24JUL100CE",
                strike_price=100.0,
                expiry=now,
                option_type=OptionType.CALL,
                last_price=5.0,
                open_interest=1000,
                volume=500,
                implied_volatility=0.25,
                delta=0.5,
                gamma=0.01,
                theta=-0.05,
                vega=0.1,
                rho=0.05,
                quantity=1,
            )
        ]

        # Clear cache
        self.engine._cache.clear()

        # First call should not be cached
        with patch.object(self.engine, "_select_atm_straddle_strikes") as mock_select:
            mock_select.return_value = [100.0]
            selected1 = await self.engine.select_strikes(
                100.0, option_chain, "atm_straddle", 1, 1
            )
            assert len(selected1) == 1
            mock_select.assert_called_once()

        # Second call with same parameters should be cached
        with patch.object(self.engine, "_select_atm_straddle_strikes") as mock_select:
            selected2 = await self.engine.select_strikes(
                100.0, option_chain, "atm_straddle", 1, 1
            )
            assert len(selected2) == 1
            mock_select.assert_not_called()  # Should not be called due to cache

    async def test_select_strikes_performance_monitoring(self):
        """Test performance monitoring in strike selection."""
        # Create test option chain
        now = datetime.now(UTC)
        option_chain = [
            OptionContract(
                symbol="TEST24JUL100CE",
                strike_price=100.0,
                expiry=now,
                option_type=OptionType.CALL,
                last_price=5.0,
                open_interest=1000,
                volume=500,
                implied_volatility=0.25,
                delta=0.5,
                gamma=0.01,
                theta=-0.05,
                vega=0.1,
                rho=0.05,
                quantity=1,
            )
        ]

        # Test that performance warning is logged when exceeding 5ms threshold
        with patch("loats.strike_selection.logger") as mock_logger:
            with patch("loats.strike_selection.datetime") as mock_datetime:
                # Mock datetime to simulate slow execution
                mock_datetime.datetime.now.side_effect = [
                    datetime.now(UTC),
                    datetime.now(UTC) + timedelta(milliseconds=6),  # 6ms later
                ]

                selected = await self.engine.select_strikes(
                    100.0, option_chain, "atm_straddle", 1, 1
                )
                assert len(selected) == 1
                mock_logger.warning.assert_called_once()

        # Test that debug message is logged for fast execution
        with patch("loats.strike_selection.logger") as mock_logger:
            with patch("loats.strike_selection.datetime") as mock_datetime:
                # Mock datetime to simulate fast execution
                mock_datetime.datetime.now.side_effect = [
                    datetime.now(UTC),
                    datetime.now(UTC) + timedelta(milliseconds=2),  # 2ms later
                ]

                selected = await self.engine.select_strikes(
                    100.0, option_chain, "atm_straddle", 1, 1
                )
                assert len(selected) == 1
                mock_logger.debug.assert_called_once()

    async def test_select_strikes_empty_chain(self):
        """Test strike selection with empty option chain."""
        selected = await self.engine.select_strikes(100.0, [], "atm_straddle", 1, 3)
        assert len(selected) == 0

    async def test_select_strikes_single_strike(self):
        """Test strike selection with single strike option chain."""
        # Create test option chain with single strike
        now = datetime.now(UTC)
        option_chain = [
            OptionContract(
                symbol="TEST24JUL100CE",
                strike_price=100.0,
                expiry=now,
                option_type=OptionType.CALL,
                last_price=5.0,
                open_interest=1000,
                volume=500,
                implied_volatility=0.25,
                delta=0.5,
                gamma=0.01,
                theta=-0.05,
                vega=0.1,
                rho=0.05,
                quantity=1,
            )
        ]

        selected = await self.engine.select_strikes(
            100.0, option_chain, "atm_straddle", 1, 3
        )
        assert len(selected) == 1
        assert 100.0 in selected

    async def test_atm_straddle_edge_cases(self):
        """Test ATM straddle selection edge cases."""
        # Test with underlying price below all strikes
        strikes = [100.0, 105.0, 110.0]
        selected = await self.engine._select_atm_straddle_strikes(95.0, strikes, 1, 3)
        assert len(selected) == 1
        assert 100.0 in selected  # Should select the lowest strike

        # Test with underlying price above all strikes
        selected = await self.engine._select_atm_straddle_strikes(115.0, strikes, 1, 3)
        assert len(selected) == 1
        assert 110.0 in selected  # Should select the highest strike

        # Test with exact ATM strike
        selected = await self.engine._select_atm_straddle_strikes(105.0, strikes, 1, 3)
        assert len(selected) == 3
        assert 100.0 in selected
        assert 105.0 in selected
        assert 110.0 in selected

    async def test_delta_neutral_edge_cases(self):
        """Test delta neutral selection edge cases."""
        # Create test option chain
        now = datetime.now(UTC)
        option_chain = [
            OptionContract(
                symbol="TEST24JUL100CE",
                strike_price=100.0,
                expiry=now,
                option_type=OptionType.CALL,
                last_price=5.0,
                open_interest=1000,
                volume=500,
                implied_volatility=0.25,
                delta=0.5,
                gamma=0.01,
                theta=-0.05,
                vega=0.1,
                rho=0.05,
                quantity=1,
            ),
            OptionContract(
                symbol="TEST24JUL100PE",
                strike_price=100.0,
                expiry=now,
                option_type=OptionType.PUT,
                last_price=4.0,
                open_interest=1000,
                volume=500,
                implied_volatility=0.26,
                delta=-0.5,
                gamma=0.01,
                theta=-0.05,
                vega=0.1,
                rho=-0.05,
                quantity=1,
            ),
        ]

        # Test with only ATM options available
        selected = await self.engine._select_delta_neutral_strikes(
            100.0, option_chain, 1, 2
        )
        assert len(selected) == 2  # Should select both ATM call and put
        assert 100.0 in selected

    async def test_oi_based_edge_cases(self):
        """Test open interest based selection edge cases."""
        # Create test option chain with all strikes having same OI
        now = datetime.now(UTC)
        option_chain = [
            OptionContract(
                symbol="TEST24JUL95CE",
                strike_price=95.0,
                expiry=now,
                option_type=OptionType.CALL,
                last_price=7.0,
                open_interest=1000,
                volume=500,
                implied_volatility=0.27,
                delta=0.6,
                gamma=0.012,
                theta=-0.06,
                vega=0.12,
                rho=0.06,
                quantity=1,
            ),
            OptionContract(
                symbol="TEST24JUL100CE",
                strike_price=100.0,
                expiry=now,
                option_type=OptionType.CALL,
                last_price=5.0,
                open_interest=1000,
                volume=500,
                implied_volatility=0.25,
                delta=0.5,
                gamma=0.01,
                theta=-0.05,
                vega=0.1,
                rho=0.05,
                quantity=1,
            ),
            OptionContract(
                symbol="TEST24JUL105CE",
                strike_price=105.0,
                expiry=now,
                option_type=OptionType.CALL,
                last_price=3.0,
                open_interest=1000,
                volume=500,
                implied_volatility=0.23,
                delta=0.4,
                gamma=0.008,
                theta=-0.04,
                vega=0.08,
                rho=0.04,
                quantity=1,
            ),
        ]

        # Test with all strikes having same OI
        selected = await self.engine._select_oi_based_strikes(100.0, option_chain, 1, 2)
        assert len(selected) == 2
        # Should select strikes closest to ATM
        assert 100.0 in selected


if __name__ == "__main__":
    # Run the tests
    unittest.main(verbosity=2)
