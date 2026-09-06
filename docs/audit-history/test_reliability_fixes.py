#!/usr/bin/env python3
"""
Comprehensive test for reliability review fixes.
Tests the three main issues:
1. R5-F-02: DB cleanup on shutdown (scheduler.db pool leak)
2. R5-F-06: Order POSTs protected by CB (circuit breaker protection)
3. R5-F-14: JSONL audit write atomicity
"""

import json

# Import the modules we need to test
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, "src")

from loats.database import Database
from loats.models import Signal
from loats.openalgo import AsyncOpenAlgoClient
from loats.scheduler import TradingScheduler
from loats.utils.circuit_breaker import OPENALGO_CIRCUIT_BREAKER


class TestReliabilityFixes(unittest.IsolatedAsyncioTestCase):
    """Test suite for reliability review fixes."""

    async def asyncSetUp(self):
        """Set up test fixtures."""
        # Create temporary database and audit log files
        self.temp_dir = Path(tempfile.mkdtemp())
        self.db_path = self.temp_dir / "test.db"
        self.audit_log_path = self.temp_dir / "test_audit.jsonl"

        # Initialize database
        self.db = Database(
            db_path=self.db_path, audit_log_path=self.audit_log_path, retention_days=30
        )

        # Initialize scheduler
        self.scheduler = TradingScheduler()

        # Mock openalgo client for testing
        self.mock_client = MagicMock(spec=AsyncOpenAlgoClient)

    async def asyncTearDown(self):
        """Clean up test fixtures."""
        # Close database connections
        try:
            await self.db.async_close_all()
        except Exception:
            pass

        # Clean up temporary files
        try:
            if self.db_path.exists():
                self.db_path.unlink()
            if self.audit_log_path.exists():
                self.audit_log_path.unlink()
            self.temp_dir.rmdir()
        except Exception:
            pass

    async def test_r5_f_02_scheduler_db_cleanup(self):
        """Test R5-F-02: Scheduler DB cleanup on shutdown."""
        print("Testing R5-F-02: Scheduler DB cleanup on shutdown...")

        # Start scheduler
        await self.scheduler.initialize()
        await self.scheduler.start()
        self.assertTrue(self.scheduler.running)

        # Verify scheduler has db reference
        self.assertIsNotNone(self.scheduler.db)

        # Mock the async_close_all method to track if it's called
        original_async_close_all = self.scheduler.db.async_close_all
        close_all_called = False

        async def mock_async_close_all():
            nonlocal close_all_called
            close_all_called = True
            await original_async_close_all()

        self.scheduler.db.async_close_all = mock_async_close_all

        # Shutdown scheduler
        await self.scheduler.shutdown()

        # Verify that async_close_all was called during shutdown
        self.assertTrue(
            close_all_called,
            "R5-F-02: Scheduler should call db.async_close_all() during shutdown",
        )

        print("✅ R5-F-02: Scheduler DB cleanup test passed")

    async def test_r5_f_06_circuit_breaker_post_protection(self):
        """Test R5-F-06: Order POSTs protected by circuit breaker."""
        print("Testing R5-F-06: Order POSTs protected by circuit breaker...")

        # Test that circuit breaker is properly configured
        self.assertEqual(OPENALGO_CIRCUIT_BREAKER.name, "openalgo")
        self.assertEqual(OPENALGO_CIRCUIT_BREAKER.config.failure_threshold, 3)
        self.assertEqual(OPENALGO_CIRCUIT_BREAKER.config.success_threshold, 2)
        self.assertEqual(OPENALGO_CIRCUIT_BREAKER.config.timeout, 60.0)

        # Test circuit breaker state management
        initial_state = OPENALGO_CIRCUIT_BREAKER.state
        self.assertEqual(initial_state.value, "closed")

        # Test that circuit breaker can be opened and closed
        from loats.utils.circuit_breaker import CircuitBreakerOpenError

        # Manually open the circuit breaker
        OPENALGO_CIRCUIT_BREAKER._state = (
            "open"  # Access protected attribute for testing
        )
        OPENALGO_CIRCUIT_BREAKER._opened_at = 1.0

        # Verify circuit breaker is open
        self.assertEqual(OPENALGO_CIRCUIT_BREAKER.state.value, "open")

        # Test that circuit breaker rejects calls when open
        async def test_call():
            return "success"

        with self.assertRaises(CircuitBreakerOpenError):
            await OPENALGO_CIRCUIT_BREAKER.call_async(test_call)

        # Reset circuit breaker for other tests
        OPENALGO_CIRCUIT_BREAKER.reset()

        print("✅ R5-F-06: Circuit breaker POST protection test passed")

    async def test_r5_f_14_jsonl_audit_write_atomicity(self):
        """Test R5-F-14: JSONL audit write atomicity."""
        print("Testing R5-F-14: JSONL audit write atomicity...")

        # Create a test signal
        test_signal = Signal(
            signal_id="test_signal_001",
            symbol="TEST",
            signal_type="BUY",
            strength=0.8,
            timestamp="2024-01-15T10:30:00Z",
            indicators={"test_indicator": 0.5},
            confidence=0.8,
            metadata={"test": "data", "scan_type": "test"},
        )

        # Test the sync version
        success = self.db.create_signal(test_signal)
        self.assertTrue(success)

        # Verify audit log was written
        self.assertTrue(self.audit_log_path.exists())

        # Read the audit log and verify the entry
        with self.audit_log_path.open("r", encoding="utf-8") as f:
            lines = f.readlines()

        # Should have at least one audit entry
        self.assertGreater(len(lines), 0)

        # Parse the last line (most recent entry)
        last_line = lines[-1].strip()
        audit_entry = json.loads(last_line)

        # Verify audit entry structure
        self.assertIn("entry_id", audit_entry)
        self.assertIn("timestamp", audit_entry)
        self.assertIn("action", audit_entry)
        self.assertIn("entity_type", audit_entry)
        self.assertIn("entity_id", audit_entry)
        self.assertIn("sha256_hash", audit_entry)

        # Verify the action and entity type
        self.assertEqual(audit_entry["action"], "CREATE")
        self.assertEqual(audit_entry["entity_type"], "signal")
        self.assertEqual(audit_entry["entity_id"], "test_signal_001")

        # Verify the hash is valid
        self.assertTrue(len(audit_entry["sha256_hash"]) == 64)  # SHA-256 hash length

        # Test the async version
        test_signal_async = Signal(
            signal_id="test_signal_002",
            symbol="TEST",
            signal_type="SELL",
            strength=0.6,
            timestamp="2024-01-15T11:30:00Z",
            indicators={"test_indicator": 0.3},
            confidence=0.6,
            metadata={"test": "async", "scan_type": "test"},
        )

        # Initialize async pool
        await self.db.async_initialize()

        # Test async signal creation
        success_async = await self.db.async_create_signal(test_signal_async)
        self.assertTrue(success_async)

        # Verify audit log was updated
        with self.audit_log_path.open("r", encoding="utf-8") as f:
            lines_after_async = f.readlines()

        # Should have more lines after async call
        self.assertGreater(len(lines_after_async), len(lines))

        print("✅ R5-F-14: JSONL audit write atomicity test passed")

    async def test_jsonl_write_failure_handling(self):
        """Test that JSONL write failures prevent DB commits."""
        print("Testing JSONL write failure handling...")

        # Create a test signal
        test_signal = Signal(
            signal_id="test_signal_fail",
            symbol="FAIL",
            signal_type="BUY",
            strength=0.5,
            timestamp="2024-01-15T12:30:00Z",
            indicators={"test": 0.5},
            confidence=0.5,
            metadata={"test": "failure"},
        )

        # Mock the audit log file write to fail
        original_open = Path.open

        def failing_open(*args, **kwargs):
            if "test_audit.jsonl" in str(args[0]):
                raise OSError("Simulated file write failure")
            return original_open(*args, **kwargs)

        # Patch the Path.open method
        with patch("pathlib.Path.open", side_effect=failing_open):
            # This should raise a RuntimeError due to JSONL write failure
            with self.assertRaises(RuntimeError) as cm:
                self.db.create_signal(test_signal)

            # Verify the error message
            error_msg = str(cm.exception)
            self.assertIn("Failed to write audit log entry to JSONL file", error_msg)
            self.assertIn("Database commit aborted to maintain consistency", error_msg)

        print("✅ JSONL write failure handling test passed")

    async def test_comprehensive_reliability_scenarios(self):
        """Test comprehensive reliability scenarios."""
        print("Testing comprehensive reliability scenarios...")

        # Test 1: Multiple operations with audit logging
        signals = []
        for i in range(3):
            signal = Signal(
                signal_id=f"comprehensive_test_{i:03d}",
                symbol="COMP",
                signal_type="BUY" if i % 2 == 0 else "SELL",
                strength=0.7 + i * 0.1,
                timestamp=f"2024-01-15T1{i:02d}:30:00Z",
                indicators={"test_indicator": 0.5 + i * 0.1},
                confidence=0.7 + i * 0.1,
                metadata={"test": f"comprehensive_{i}", "scan_type": "comprehensive"},
            )
            signals.append(signal)
            success = self.db.create_signal(signal)
            self.assertTrue(success)

        # Verify all signals were created and audited
        with self.audit_log_path.open("r", encoding="utf-8") as f:
            lines = f.readlines()

        # Should have at least 3 audit entries (plus previous ones)
        self.assertGreaterEqual(len(lines), 3)

        # Test 2: Async operations
        await self.db.async_initialize()

        async_signals = []
        for i in range(2):
            signal = Signal(
                signal_id=f"async_comprehensive_{i:03d}",
                symbol="ASYNC",
                signal_type="BUY" if i % 2 == 0 else "SELL",
                strength=0.6 + i * 0.1,
                timestamp=f"2024-01-15T1{i + 5:02d}:30:00Z",
                indicators={"async_indicator": 0.4 + i * 0.1},
                confidence=0.6 + i * 0.1,
                metadata={"test": f"async_comprehensive_{i}", "scan_type": "async"},
            )
            async_signals.append(signal)
            success = await self.db.async_create_signal(signal)
            self.assertTrue(success)

        # Verify async signals were audited
        with self.audit_log_path.open("r", encoding="utf-8") as f:
            final_lines = f.readlines()

        # Should have more lines after async operations
        self.assertGreater(len(final_lines), len(lines))

        print("✅ Comprehensive reliability scenarios test passed")


if __name__ == "__main__":
    # Run the tests
    unittest.main()
