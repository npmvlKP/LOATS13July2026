"""Persistence net for signal-outcome instrumentation (30Sep evidence wave).

Covers: sync + async outcome APIs, horizon gating, honest-OPEN semantics,
non-directional handling, terminal-write idempotence (first verdict wins),
audit-trail integrity after outcome writes, and the summary surface.
"""

from __future__ import annotations

import asyncio
import gc
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from loats.config.settings import Settings
from loats.database import Database
from loats.models import HistoricalData, Signal, SignalType
from loats.signal_outcomes import SignalOutcomeState


def _make_db(tmp_path: Path) -> Database:
    """Fresh Database on a scratch store (conftest-shaped settings)."""
    settings = Settings(
        environment="test",
        sqlite_db_path=tmp_path / "outcomes.db",
        audit_log_path=tmp_path / "outcomes.log",
        openalgo_api_key="probe",
        openalgo_base_url="https://test.openalgo.com",
        telegram_bot_token="probe",
        telegram_chat_id="123456789",
    )
    return Database(
        db_path=settings.sqlite_db_path,
        audit_log_path=settings.audit_log_path,
    )


def _signal(
    signal_id: str,
    signal_type: SignalType,
    timestamp: datetime,
    symbol: str = "NIFTY",
    metadata: dict[str, Any] | None = None,
) -> Signal:
    return Signal(
        signal_id=signal_id,
        symbol=symbol,
        signal_type=signal_type,
        strength=0.8,
        timestamp=timestamp,
        indicators={"x": 1.0},
        confidence=0.8,
        metadata=metadata or {"scan_type": "ta", "source": "technical_analysis"},
    )


def _bar(
    symbol: str,
    timestamp: datetime,
    base: float,
    interval: str = "1d",
) -> HistoricalData:
    return HistoricalData(
        symbol=symbol,
        timestamp=timestamp,
        open=base,
        high=base + 2.0,
        low=base - 1.0,
        close=base + 1.0,
        volume=1000,
        interval=interval,
    )


class TestRecordSignalOutcomeOpen:
    def test_open_row_persisted(self, tmp_path: Path) -> None:
        db = _make_db(tmp_path)
        try:
            ts = datetime(2026, 9, 23, 10, 0, tzinfo=UTC)
            db.create_signal(_signal("sig-1", SignalType.BUY, ts))
            assert db.record_signal_outcome_open("sig-1", 60) is True
            summary = db.get_signal_outcome_summary()
            assert summary["counts"] == {SignalOutcomeState.OPEN.value: 1}
        finally:
            db.close()
            gc.collect()

    def test_duplicate_open_is_ignored(self, tmp_path: Path) -> None:
        db = _make_db(tmp_path)
        try:
            ts = datetime(2026, 9, 23, 10, 0, tzinfo=UTC)
            db.create_signal(_signal("sig-1", SignalType.BUY, ts))
            assert db.record_signal_outcome_open("sig-1", 60) is True
            assert db.record_signal_outcome_open("sig-1", 30) is True
            # horizon stays the FIRST value (INSERT OR IGNORE).
            summary = db.get_signal_outcome_summary()
            assert summary["counts"] == {SignalOutcomeState.OPEN.value: 1}
        finally:
            db.close()
            gc.collect()


class TestResolveSignalOutcomes:
    def test_full_positive_flow_end_to_end(self, tmp_path: Path) -> None:
        db = _make_db(tmp_path)
        try:
            ts = datetime(2026, 9, 23, 10, 0, tzinfo=UTC)
            db.create_signal(_signal("sig-1", SignalType.BUY, ts))
            db.record_signal_outcome_open("sig-1", 60)
            db.store_historical_data(
                [
                    _bar("NIFTY", ts, 100.0),
                    _bar("NIFTY", ts + timedelta(minutes=30), 104.0),
                ]
            )
            resolved = db.resolve_signal_outcomes(now=ts + timedelta(hours=2))
            assert len(resolved) == 1
            assert resolved[0]["outcome_state"] == "positive"
        finally:
            db.close()
            gc.collect()

    def test_horizon_not_elapsed_stays_open(self, tmp_path: Path) -> None:
        db = _make_db(tmp_path)
        try:
            ts = datetime(2026, 9, 23, 10, 0, tzinfo=UTC)
            db.create_signal(_signal("sig-1", SignalType.BUY, ts))
            db.record_signal_outcome_open("sig-1", 60)
            db.store_historical_data([_bar("NIFTY", ts, 100.0)])
            resolved = db.resolve_signal_outcomes(now=ts + timedelta(minutes=30))
            assert resolved == []
        finally:
            db.close()
            gc.collect()

    def test_no_bars_stays_open_honest_hole(self, tmp_path: Path) -> None:
        db = _make_db(tmp_path)
        try:
            ts = datetime(2026, 9, 23, 10, 0, tzinfo=UTC)
            db.create_signal(_signal("sig-1", SignalType.BUY, ts, symbol="NOBARS"))
            db.record_signal_outcome_open("sig-1", 60)
            resolved = db.resolve_signal_outcomes(now=ts + timedelta(hours=2))
            assert resolved == []
        finally:
            db.close()
            gc.collect()

    def test_non_directional_and_unresolvable_fail_closed(self, tmp_path: Path) -> None:
        db = _make_db(tmp_path)
        try:
            ts = datetime(2026, 9, 23, 10, 0, tzinfo=UTC)
            db.create_signal(_signal("sig-hold", SignalType.HOLD, ts))
            db.record_signal_outcome_open("sig-hold", 60)
            resolved = db.resolve_signal_outcomes(now=ts + timedelta(hours=2))
            assert [row["outcome_state"] for row in resolved] == ["non_directional"]
        finally:
            db.close()
            gc.collect()

    def test_invalid_signal_type_unresolvable(self, tmp_path: Path) -> None:
        db = _make_db(tmp_path)
        try:
            ts = datetime(2026, 9, 23, 10, 0, tzinfo=UTC)
            # Insert a corrupt signal_type directly at the storage layer
            # (the guarded API can no longer produce this state) --
            # mirrors the F8-M-01 corruption-probe discipline.
            db.create_signal(_signal("sig-x", SignalType.BUY, ts))
            conn = db._get_connection()
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE signals SET signal_type = 'CORRUPT' WHERE signal_id = 'sig-x'"
            )
            conn.commit()
            db.record_signal_outcome_open("sig-x", 60)
            resolved = db.resolve_signal_outcomes(now=ts + timedelta(hours=2))
            assert [row["outcome_state"] for row in resolved] == ["unresolvable"]
        finally:
            db.close()
            gc.collect()

    def test_first_verdict_wins_reresolve_is_noop(self, tmp_path: Path) -> None:
        db = _make_db(tmp_path)
        try:
            ts = datetime(2026, 9, 23, 10, 0, tzinfo=UTC)
            db.create_signal(_signal("sig-1", SignalType.BUY, ts))
            db.record_signal_outcome_open("sig-1", 60)
            db.store_historical_data(
                [
                    _bar("NIFTY", ts, 100.0),
                    _bar("NIFTY", ts + timedelta(minutes=30), 104.0),
                ]
            )
            first = db.resolve_signal_outcomes(now=ts + timedelta(hours=2))
            assert [row["outcome_state"] for row in first] == ["positive"]
            # Re-run: zero rows returned (already terminal), verdict intact.
            second = db.resolve_signal_outcomes(now=ts + timedelta(hours=3))
            assert second == []
            summary = db.get_signal_outcome_summary()
            assert summary["positive"] == 1
        finally:
            db.close()
            gc.collect()

    def test_denominator_excludes_non_directional(self, tmp_path: Path) -> None:
        db = _make_db(tmp_path)
        try:
            ts = datetime(2026, 9, 23, 10, 0, tzinfo=UTC)
            db.create_signal(_signal("buy", SignalType.BUY, ts))
            db.record_signal_outcome_open("buy", 60)
            db.create_signal(
                _signal("hold", SignalType.HOLD, ts + timedelta(minutes=1))
            )
            db.record_signal_outcome_open("hold", 60)
            db.store_historical_data([_bar("NIFTY", ts, 100.0)])
            db.resolve_signal_outcomes(now=ts + timedelta(hours=2))
            summary = db.get_signal_outcome_summary()
            assert summary["positive"] == 1
            assert summary["counts"].get("non_directional") == 1
            assert summary["directional"] == 1
            assert summary["positive_rate"] == pytest.approx(1.0)
        finally:
            db.close()
            gc.collect()

    def test_audit_chain_intact_after_outcome_writes(self, tmp_path: Path) -> None:
        db = _make_db(tmp_path)
        try:
            ts = datetime(2026, 9, 23, 10, 0, tzinfo=UTC)
            db.create_signal(_signal("sig-1", SignalType.BUY, ts))
            db.record_signal_outcome_open("sig-1", 60)
            db.store_historical_data([_bar("NIFTY", ts, 100.0)])
            db.resolve_signal_outcomes(now=ts + timedelta(hours=2))
            assert db.verify_audit_log_integrity() is True
        finally:
            db.close()
            gc.collect()


class TestAsyncResultMethods:
    def test_async_wrappers_match_sync_semantics(self, tmp_path: Path) -> None:
        db = _make_db(tmp_path)
        try:
            ts = datetime(2026, 9, 23, 10, 0, tzinfo=UTC)
            db.create_signal(_signal("sig-1", SignalType.BUY, ts))
            db.record_signal_outcome_open("sig-1", 60)
            db.store_historical_data([_bar("NIFTY", ts, 100.0)])

            async def main() -> tuple[bool, list[dict[str, Any]], dict[str, Any]]:
                opened = await db.async_record_signal_outcome_open(
                    "sig-2", 30, {"scan_type": "ta"}
                )
                resolved = await db.async_resolve_signal_outcomes(
                    now=ts + timedelta(hours=2)
                )
                summary = await db.async_get_signal_outcome_summary()
                return opened, resolved, summary

            opened, resolved, summary = asyncio.run(main())
            assert opened is True
            assert [row["outcome_state"] for row in resolved] == ["positive"]
            assert summary["directional"] >= 1
        finally:
            db.close()
            gc.collect()


class TestSettingsKnob:
    def test_horizon_knob_exists_and_defaults(self) -> None:
        settings = Settings(
            environment="test",
            openalgo_api_key="probe",
            openalgo_base_url="https://t.example",
            telegram_bot_token="probe",
            telegram_chat_id="1",
        )
        assert settings.signal_outcome_horizon_minutes == 60

    def test_env_example_documented(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        env_example = repo_root / ".env.example"
        text = env_example.read_text(encoding="utf-8")
        assert "SIGNAL_OUTCOME_HORIZON_MINUTES=" in text
