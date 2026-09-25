"""F9-L-03 (TODO-12): insert-time signal provenance guard pins.

FR9 F9-L-03: the live store accumulated signal rows with no
``metadata["source"]`` provenance (42 sentiment + 1 combined rows from
14Aug, pre-tagging) plus a STRESS-ORD rehearsal row in
``modification_counts``. The purge script
(``scripts/purge_legacy_signal_rows.py``) removed the existing population
under audit; THIS module pins the root-cause half: no untagged or
unknown-source signal row can ever be inserted again, through either
write path (sync ``create_signal`` or the aiosqlite pool path), while the
documented exemptions (``position_conversion``, ``benchmark``, explicit
test fixtures) keep working.

Store hygiene policy: production-signal fixtures across the test suite
carry a valid ``source`` tag (or the explicit ``test`` provenance key);
``TestStoreFixturesDeclareProvenance`` keeps that policy machine-checked.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from loats.database import Database
from loats.database_async_additions import (
    AIOSQLITE_AVAILABLE,
    extend_database_class,
)
from loats.models import Signal, SignalType
from loats.signal_source_guard import (
    ALLOWED_SIGNAL_SOURCES,
    EXEMPT_SIGNAL_SOURCES,
    TEST_PROVENANCE_KEY,
    InvalidSignalSourceError,
    validate_signal_provenance,
)


def _signal(source: dict[str, object] | None = None) -> Signal:
    return Signal(
        signal_id="f9l03_guard_probe",
        symbol="NIFTY",
        signal_type=SignalType.BUY,
        strength=0.8,
        timestamp=datetime.now(UTC),
        indicators={"rsi": 55.0},
        metadata=dict(source) if source else {},
    )


@pytest.fixture
def temp_db(tmp_path: Path):
    db = Database(
        db_path=tmp_path / "guard.db",
        audit_log_path=tmp_path / "guard_audit.jsonl",
    )
    db._initialize_database()
    extend_database_class()
    yield db
    db.close()


class TestValidateSignalProvenance:
    """Pure validation contract (no database)."""

    def test_enum_tagged_signal_passes(self) -> None:
        validate_signal_provenance(_signal({"source": "ta"}))
        validate_signal_provenance(_signal({"source": "sentiment"}))

    def test_exempt_source_passes(self) -> None:
        for source in sorted(EXEMPT_SIGNAL_SOURCES):
            validate_signal_provenance(_signal({"source": source}))

    def test_explicit_test_provenance_passes_without_source(self) -> None:
        validate_signal_provenance(_signal({TEST_PROVENANCE_KEY: "latency"}))

    @pytest.mark.parametrize(
        "metadata",
        [
            {},
            {"scan_type": "sentiment"},
            {"source": None},
            {"source": ""},
            {"source": "test"},
            {"source": "orchestrator"},
            {"source": 7},
        ],
        ids=[
            "empty_metadata",
            "scan_type_only",
            "source_none",
            "source_empty_string",
            "source_test_is_not_valid",
            "source_orchestrator_is_not_valid",
            "source_non_string",
        ],
    )
    def test_invalid_provenance_raises(self, metadata: dict[str, object]) -> None:
        with pytest.raises(InvalidSignalSourceError):
            validate_signal_provenance(_signal(metadata))

    def test_allow_list_is_enum_union_exemptions(self) -> None:
        from loats.strength import StrengthSource

        assert ALLOWED_SIGNAL_SOURCES == (
            {source.value for source in StrengthSource} | EXEMPT_SIGNAL_SOURCES
        )


class TestSyncInsertGate:
    """The sync ``create_signal`` path enforces the guard before writing."""

    def test_tagged_row_inserts(self, temp_db: Database) -> None:
        signal = _signal({"source": "ta", "scan_type": "ta"})
        assert temp_db.create_signal(signal) is True
        assert temp_db.get_latest_signals("NIFTY", limit=1)[0].signal_id == (
            "f9l03_guard_probe"
        )

    def test_untagged_row_is_rejected_and_not_written(self, temp_db: Database) -> None:
        with pytest.raises(InvalidSignalSourceError):
            temp_db.create_signal(_signal(None))
        assert temp_db.get_latest_signals("NIFTY", limit=1) == []

    def test_unknown_source_is_rejected_and_not_written(
        self, temp_db: Database
    ) -> None:
        with pytest.raises(InvalidSignalSourceError):
            temp_db.create_signal(_signal({"source": "test"}))
        assert temp_db.get_latest_signals("NIFTY", limit=1) == []


class TestAsyncInsertGate:
    """The aiosqlite pool path cannot bypass the guard."""

    @pytest.mark.asyncio
    async def test_untagged_async_row_is_rejected(self, temp_db: Database) -> None:
        if not AIOSQLITE_AVAILABLE:
            pytest.skip("aiosqlite not available")
        await temp_db.async_initialize()
        with pytest.raises(InvalidSignalSourceError):
            await temp_db.async_create_signal(_signal(None))

    @pytest.mark.asyncio
    async def test_untagged_core_async_row_is_rejected(self, temp_db: Database) -> None:
        if not AIOSQLITE_AVAILABLE:
            pytest.skip("aiosqlite not available")
        await temp_db.async_initialize()
        with pytest.raises(InvalidSignalSourceError):
            await temp_db._async_create_signal(_signal({"source": ""}))

    @pytest.mark.asyncio
    async def test_tagged_async_row_inserts(self, temp_db: Database) -> None:
        if not AIOSQLITE_AVAILABLE:
            pytest.skip("aiosqlite not available")
        await temp_db.async_initialize()
        signal = _signal({"source": "volatility", "scan_type": "volatility"})
        assert await temp_db.async_create_signal(signal) is True
        assert temp_db.get_latest_signals("NIFTY", limit=1) != []


class TestStoreFixturesDeclareProvenance:
    """Store-policy net: every suite file exercising signal inserts must
    document how its fixtures satisfy the provenance guard."""

    @pytest.mark.parametrize(
        "test_file",
        [
            "test_database.py",
            "test_database_async_additions.py",
            "test_performance_analyzer.py",
            "test_e2e_cmp_chain.py",
            "test_as_of_date_propagation.py",
            "test_f9h04_as_of_date_wiring.py",
            "test_load_latency_integration.py",
        ],
    )
    def test_module_docstring_declares_fixture_policy(self, test_file: str) -> None:
        path = Path(__file__).parent / test_file
        assert path.exists(), f"{test_file} must exist"
        doc = (path.read_text(encoding="utf-8").split('"""') + [""] * 3)[1]
        assert "provenance" in doc.lower(), (
            f"{test_file} must document its signal-fixture provenance "
            "policy in the module docstring (F9-L-03 store hygiene)"
        )
