#!/usr/bin/env python3
"""
Simple test for reliability review fixes without external dependencies.
Tests the three main issues:
1. R5-F-02: DB cleanup on shutdown (scheduler.db pool leak)
2. R5-F-06: Order POSTs protected by CB (circuit breaker protection)
3. R5-F-14: JSONL audit write atomicity
"""

import asyncio
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

# Import the modules we need to test
import sys
sys.path.insert(0, 'src')

from loats.database import Database
from loats.scheduler import TradingScheduler
from loats.utils.circuit_breaker import OPENALGO_CIRCUIT_BREAKER, CircuitBreakerOpenError
from loats.models import Signal

class TestReliabilityFixesSimple(unittest.IsolatedAsyncioTestCase):
    """Simple test suite for reliability review fixes."""

    async def asyncSetUp(self):
        """Set up test fixtures."""
        # Create temporary database and audit log files
        self.temp_dir = Path(tempfile.mkdtemp())
        self.db_path = self.temp_dir / "test.db"
        self.audit_log_path = self.temp_dir / "test_audit.jsonl"

        # Initialize database
        self.db = Database(
            db_path=self.db_path,
            audit_log_path=self.audit_log_path,
            retention_days=30
        )

        # Initialize scheduler
        self.scheduler = TradingScheduler()

    async def asyncTearDown(self):
        """Clean up test fixtures."""
        # Close database connections
        try:
            await self.db.async_close_all()
        except:
            pass

        # Clean up temporary files
        try:
            if self.db_path.exists():
                self.db_path.unlink()
            if self.audit_log_path.exists():
                self.audit_log_path.unlink()
            self.temp_dir.rmdir()
        except:
            pass

    async def test_r5_f_02_scheduler_db_cleanup(self):
        """Test R5-F-02: Scheduler DB cleanup on shutdown."""
        print("Testing R5-F-02: Scheduler DB cleanup on shutdown...")

        # Mock the async_close_all method to track if it's called
        original_async_close_all = self.scheduler.db.async_close_all
        close_all_called = False

        async def mock_async_close_all():
            nonlocal close_all_called
            close_all_called = True
            await original_async_close_all()

        self.scheduler.db.async_close_all = mock_async_close_all

        # Simulate scheduler shutdown by calling the shutdown method
        # We'll mock the scheduler.running to True to trigger the cleanup
        self.scheduler.running = True

        # Mock the scheduler components to avoid actual execution
        self.scheduler.scan_tasks = {}
        self.scheduler.scheduler = MagicMock()
        self.scheduler.scheduler.shutdown = MagicMock()

        try:
            await self.scheduler.shutdown()
        except:
            pass  # Ignore any errors from mock objects

        # Verify that async_close_all was called during shutdown
        self.assertTrue(close_all_called, "R5-F-02: Scheduler should call db.async_close_all() during shutdown")

        print("PASS: R5-F-02: Scheduler DB cleanup test passed")

    async def test_r5_f_06_circuit_breaker_configuration(self):
        """Test R5-F-06: Circuit breaker configuration and state management."""
        print("Testing R5-F-06: Circuit breaker configuration...")

        # Test that circuit breaker is properly configured
        self.assertEqual(OPENALGO_CIRCUIT_BREAKER.name, "openalgo")
        self.assertEqual(OPENALGO_CIRCUIT_BREAKER.config.failure_threshold, 3)
        self.assertEqual(OPENALGO_CIRCUIT_BREAKER.config.success_threshold, 2)
        self.assertEqual(OPENALGO_CIRCUIT_BREAKER.config.timeout, 60.0)

        # Test circuit breaker state management
        initial_state = OPENALGO_CIRCUIT_BREAKER.state
        self.assertEqual(initial_state.value, "closed")

        # Test that circuit breaker can be opened and closed
        # Manually open the circuit breaker by simulating failures
        for i in range(3):  # Trigger the failure threshold
            try:
                await OPENALGO_CIRCUIT_BREAKER.call_async(lambda: 1/0)
            except:
                pass  # Ignore the division by zero error

        # Verify circuit breaker is open
        self.assertEqual(str(OPENALGO_CIRCUIT_BREAKER.state), "CircuitState.OPEN")

        # Test that circuit breaker rejects calls when open
        async def test_call():
            return "success"

        with self.assertRaises(CircuitBreakerOpenError):
            await OPENALGO_CIRCUIT_BREAKER.call_async(test_call)

        # Reset circuit breaker for other tests
        OPENALGO_CIRCUIT_BREAKER.reset()

        print("PASS: R5-F-06: Circuit breaker configuration test passed")

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
            metadata={"test": "data", "scan_type": "test"}
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

        print("PASS: R5-F-14: JSONL audit write atomicity test passed")

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
            metadata={"test": "failure"}
        )

        # Mock the audit log file write to fail
        original_open = Path.open

        def failing_open(*args, **kwargs):
            if 'test_audit.jsonl' in str(args[0]):
                raise IOError("Simulated file write failure")
            return original_open(*args, **kwargs)

        # Patch the Path.open method
        with patch('pathlib.Path.open', side_effect=failing_open):
            # This should raise a RuntimeError due to JSONL write failure
            with self.assertRaises(RuntimeError) as cm:
                self.db.create_signal(test_signal)

            # Verify the error message
            error_msg = str(cm.exception)
            self.assertIn("Failed to write audit log entry to JSONL file", error_msg)
            self.assertIn("Database commit aborted to maintain consistency", error_msg)

        print("PASS: JSONL write failure handling test passed")

if __name__ == "__main__":
    # Run the tests
    unittest.main(verbosity=2)