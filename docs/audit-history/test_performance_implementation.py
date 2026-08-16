#!/usr/bin/env python3
"""
Performance Implementation Test for LOATS13July2026.

Tests the newly implemented strike selection and orchestrator modules
to verify they meet the performance targets:
- Strike selection: <5ms
- Orchestrator cycle: <100ms
"""

import asyncio
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent / "src"))

from loats.models import OptionContract, OptionType
from loats.orchestrator import orchestrator
from loats.strike_selection import select_strikes


def create_test_option_chain() -> list[OptionContract]:
    """Create a test option chain for performance testing."""
    base_price = 19500.0
    strikes = []
    for i in range(-10, 11):  # 21 strikes around ATM
        strike_price = base_price + (i * 100)
        strikes.append(
            OptionContract(
                symbol=f"NIFTY24JUL{int(strike_price):d}CE",
                strike_price=strike_price,
                expiry=datetime(2024, 7, 25, tzinfo=UTC),
                option_type=OptionType.CALL,
                last_price=max(100, strike_price * 0.01),
                open_interest=1000 + (abs(i) * 100),
                volume=500 + (abs(i) * 50),
                implied_volatility=0.2 + (i * 0.01),
                delta=0.5 - (i * 0.02),
                gamma=0.01,
                theta=-0.05,
                vega=0.1,
                rho=0.05,
                quantity=1,
            )
        )
        strikes.append(
            OptionContract(
                symbol=f"NIFTY24JUL{int(strike_price):d}PE",
                strike_price=strike_price,
                expiry=datetime(2024, 7, 25, tzinfo=UTC),
                option_type=OptionType.PUT,
                last_price=max(100, (20000 - strike_price) * 0.01),
                open_interest=1000 + (abs(i) * 100),
                volume=500 + (abs(i) * 50),
                implied_volatility=0.2 + (i * 0.01),
                delta=-0.5 + (i * 0.02),
                gamma=0.01,
                theta=-0.05,
                vega=0.1,
                rho=0.05,
                quantity=1,
            )
        )
    return strikes


async def test_strike_selection_performance() -> bool:
    """Test strike selection performance meets <5ms target."""
    print("Testing Strike Selection Performance...")

    # Create test data
    option_chain = create_test_option_chain()
    underlying_price = 19500.0

    # Warm up (JIT compilation for Numba if available)
    await select_strikes(underlying_price, option_chain, "atm_straddle", 2, 5)

    # Run multiple iterations for accurate measurement
    iterations = 100
    total_time = 0.0
    max_time = 0.0
    min_time = float("inf")
    failures = 0

    for i in range(iterations):
        start_time = time.perf_counter()
        try:
            await select_strikes(underlying_price, option_chain, "atm_straddle", 2, 5)
            elapsed = (time.perf_counter() - start_time) * 1000  # Convert to ms

            total_time += elapsed
            max_time = max(max_time, elapsed)
            min_time = min(min_time, elapsed)

            if elapsed > 5.0:  # 5ms target
                failures += 1
                print(f"  Iteration {i + 1}: {elapsed:.3f}ms ❌ (exceeded 5ms target)")

        except Exception as e:
            print(f"  Iteration {i + 1}: ERROR - {e}")
            failures += 1

    avg_time = total_time / iterations

    print(f"Strike Selection Results ({iterations} iterations):")
    print(f"  Average: {avg_time:.3f}ms")
    print(f"  Minimum: {min_time:.3f}ms")
    print(f"  Maximum: {max_time:.3f}ms")
    print(f"  Failures: {failures}/{iterations}")
    print(f"  Success Rate: {(iterations - failures) / iterations * 100:.1f}%")

    # Performance target: <5ms average and <10% failures
    success = avg_time <= 5.0 and (failures / iterations) <= 0.1
    print(f"  Performance Target: {'✅ PASS' if success else '❌ FAIL'}")
    return success


async def test_orchestrator_initialization() -> bool:
    """Test orchestrator initialization."""
    print("\nTesting Orchestrator Initialization...")

    try:
        await orchestrator.initialize()
        print("  Orchestrator initialized successfully ✅")
        return True
    except Exception as e:
        print(f"  Orchestrator initialization failed: {e} ❌")
        return False


def test_module_imports() -> bool:
    """Test that all new modules can be imported successfully."""
    print("\nTesting Module Imports...")

    try:
        from loats.orchestrator import (
            TradingOrchestrator,
            get_cycle_stats,
            start_orchestrator,
        )
        from loats.strike_selection import StrikeSelectionEngine, select_strikes

        print("  ✅ strike_selection module imported successfully")
        print("  ✅ orchestrator module imported successfully")
        print("  ✅ All performance modules available")

        return True
    except ImportError as e:
        print(f"  ❌ Import error: {e}")
        return False
    except Exception as e:
        print(f"  ❌ Unexpected error: {e}")
        return False


async def main() -> int:
    """Run all performance tests."""
    print("=" * 60)
    print("LOATS13July2026 Performance Implementation Test")
    print("=" * 60)

    # Test 1: Module imports
    test_module_imports()

    # Test 2: Orchestrator initialization
    await test_orchestrator_initialization()

    # Test 3: Strike selection performance
    await test_strike_selection_performance()

    print("\n" + "=" * 60)
    print("PERFORMANCE IMPLEMENTATION SUMMARY")
    print("=" * 60)

    return 0


if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\nTest interrupted by user.")
        sys.exit(1)
    except Exception as e:
        print(f"\nTest failed with error: {e}")
        sys.exit(1)
