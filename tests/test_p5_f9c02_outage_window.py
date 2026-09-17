"""F9-C-02 follow-up (2026-09-17): documented OUTAGE windows in the P5 grader.

The 17Sep OpenAlgo re-auth outage (broker-session loss after the 05:01 IST
restart) opened a decisional-evidence hole inside the live 14-day span of
run ``20260916_140341``. Forensic read of the live log + DB probe:

- routing provenance stayed CLEAN through the outage (zero
  ``routing_enabled:false`` ROUTE rows; ``routing_divergence_detected: 0``)
  -- the breaker-protected degraded fetch is the system working as
  designed, so the window must NEVER void the span;
- yet the hole is real (zero decisional evidence while it lasted) and the
  outage report itself requires the grader to reflect it in span validity.

Remediation pinned here (mirrors the CONTAMINATION_WINDOWS registry
pattern, with the opposite grading semantics):

1. ``DOCUMENTED_OUTAGE_WINDOWS`` registry on the validator: (start, end,
   why) entries, each bound to a dated audit-history record.
2. ``grade_run_log`` annotates any run whose span overlaps a documented
   outage window -- the note is carried on ``Grade.annotations`` and
   NEVER enters ``reasons``, so it cannot flip a verdict: an otherwise
   eligible run still grades PASS (with disclosure), an ongoing run stays
   INCOMPLETE, a contaminated run still FAILs.
3. VOID semantics for CONTAMINATION_WINDOWS are unchanged -- the new
   window class must not dilute divergence poisoning.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = REPO_ROOT / "scripts" / "verify_p5_forward_test.py"
OUTAGE_RECORD = (
    REPO_ROOT / "docs" / "audit-history" / "17Sep2026-p5-openalgo-auth-outage.md"
)


def _load_validator() -> Any:
    spec = importlib.util.spec_from_file_location(
        "p5_validator_f9c02_outage", VALIDATOR
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _outage_log() -> dict[str, Any]:
    """An otherwise fully-eligible ENDED run spanning the 17Sep outage.

    19-day span (satisfies the 14-day floor), routing enabled, zero
    exceptions, healthy decisional counters, and a proven-clean
    divergence field (the supervisor's DB probe recorded zero
    ``routing_enabled:false`` ROUTE rows through the outage).
    """
    return {
        "routing": {"enabled_at_start": True},
        "started_at": "2026-09-01T00:00:00+00:00",
        "ended_at": "2026-09-20T00:00:00+00:00",
        "unhandled_exceptions": 0,
        "cycles_completed": 40000,
        "counters": {
            "success": 800,
            "disabled": 0,
            "error": 0,
            "routing_divergence_detected": 0,
        },
        "disabled_routes_during_enabled_window": {
            "count": 0,
            "window": {"first_disabled_route_at": None, "last_disabled_route_at": None},
        },
    }


class TestDocumentedOutageWindowRegistry:
    """Registry shape: documented, parseable, record-bound."""

    def test_registry_contains_documented_17sep_outage(self) -> None:
        validator = _load_validator()
        windows = validator.DOCUMENTED_OUTAGE_WINDOWS
        assert len(windows) >= 1
        match = [
            entry
            for entry in windows
            if entry[0] == "2026-09-16T23:31:21+00:00" and entry[1] is None
        ]
        assert match, (
            "the documented 17Sep OpenAlgo auth-outage window (start "
            "2026-09-16T23:31:21Z = 05:01 IST first observed auth failure) "
            "must be registered OPEN-ENDED (end None): the outage was "
            "still live at record time (last observed auth failure "
            "09:31:23Z) -- the closing addendum pins the end after the "
            "operator re-auth is verified"
        )
        assert all(isinstance(entry[2], str) and entry[2] for entry in windows)

    def test_registry_entries_parse_and_are_ordered(self) -> None:
        validator = _load_validator()
        for start_raw, end_raw, _why in validator.DOCUMENTED_OUTAGE_WINDOWS:
            start = validator._parse_ts(start_raw)
            assert start is not None, f"unparseable window start {start_raw!r}"
            if end_raw is None:
                continue  # open-ended: live outage pending its closing addendum
            end = validator._parse_ts(end_raw)
            assert end is not None, f"unparseable window end {end_raw!r}"
            assert start < end

    def test_registry_is_record_bound(self) -> None:
        """Every registered window cites its dated audit-history record."""
        validator = _load_validator()
        assert OUTAGE_RECORD.exists(), (
            "the documented outage window must have its dated "
            "audit-history record on disk"
        )
        for _start, _end, why in validator.DOCUMENTED_OUTAGE_WINDOWS:
            assert why.strip(), "every window needs a non-empty why/documentation"


class TestOutageAnnotationSemantics:
    """Annotations disclose; they never flip a verdict."""

    def test_open_ended_window_annotates_ongoing_and_future_runs(self) -> None:
        """While the outage is unresolved (end None), any run whose span
        started before 'now' and is still ongoing after the window start
        is annotated -- the hole keeps growing until re-auth lands."""
        validator = _load_validator()
        log = {
            "routing": {"enabled_at_start": True},
            "started_at": "2026-09-16T14:03:41+00:00",
            "ended_at": None,
            "unhandled_exceptions": 0,
            "cycles_completed": 26184,
            "counters": {
                "success": 0,
                "disabled": 0,
                "error": 0,
                "routing_divergence_detected": 0,
            },
            "disabled_routes_during_enabled_window": {
                "count": 0,
                "window": {
                    "first_disabled_route_at": None,
                    "last_disabled_route_at": None,
                },
            },
        }
        grade = validator.grade_run_log(log)
        assert grade.verdict == "INCOMPLETE"
        assert any(
            "documented outage window (open)" in note for note in grade.annotations
        )

    def test_eligible_run_spanning_outage_grades_pass_with_annotation(
        self,
    ) -> None:
        """THE acceptance pin: the gate can still PASS, with disclosure."""
        validator = _load_validator()
        grade = validator.grade_run_log(_outage_log())
        assert grade.verdict == "PASS"
        assert any("documented outage window" in note for note in grade.annotations), (
            "the outage overlap must be disclosed in Grade.annotations"
        )
        assert not any("outage" in r.lower() for r in grade.reasons), (
            "the annotation must not enter reasons (it would force "
            "INCOMPLETE and silently downgrade eligible runs)"
        )

    def test_ongoing_run_inside_outage_annotated_not_failed(self) -> None:
        """A live run mid-outage stays INCOMPLETE -- never FAIL."""
        validator = _load_validator()
        log = {
            "routing": {"enabled_at_start": True},
            "started_at": "2026-09-17T02:00:00+00:00",
            "ended_at": None,
            "unhandled_exceptions": 0,
            "cycles_completed": 26184,
            "counters": {
                "success": 0,
                "disabled": 0,
                "error": 0,
                "routing_divergence_detected": 0,
            },
            "disabled_routes_during_enabled_window": {
                "count": 0,
                "window": {
                    "first_disabled_route_at": None,
                    "last_disabled_route_at": None,
                },
            },
        }
        grade = validator.grade_run_log(log)
        assert grade.verdict == "INCOMPLETE"
        assert any("documented outage window" in note for note in grade.annotations)

    def test_partial_overlap_at_start_annotates(self) -> None:
        """Span starts before the window, ends inside it."""
        validator = _load_validator()
        log = _outage_log() | {
            "started_at": "2026-09-10T00:00:00+00:00",
            "ended_at": "2026-09-28T00:00:00+00:00",
        }
        grade = validator.grade_run_log(log)
        assert grade.verdict == "PASS"
        assert any("documented outage window" in note for note in grade.annotations)

    def test_partial_overlap_at_end_annotates(self) -> None:
        """Span starts inside the window, ends after it."""
        validator = _load_validator()
        log = _outage_log() | {
            "started_at": "2026-09-17T00:00:00+00:00",
            "ended_at": "2026-10-05T00:00:00+00:00",
        }
        grade = validator.grade_run_log(log)
        assert grade.verdict == "PASS"
        assert any("documented outage window" in note for note in grade.annotations)

    def test_clean_run_outside_outage_carries_no_annotation(self) -> None:
        """No false positives: untouched spans stay silent."""
        validator = _load_validator()
        log = _outage_log() | {
            "started_at": "2026-07-01T00:00:00+00:00",
            "ended_at": "2026-07-20T00:00:00+00:00",
        }
        grade = validator.grade_run_log(log)
        assert grade.verdict == "PASS"
        assert grade.annotations == ()

    def test_divergence_still_fails_despite_annotation(self) -> None:
        """The annotation never masks proven contamination."""
        validator = _load_validator()
        log = _outage_log()
        log["disabled_routes_during_enabled_window"] = {
            "count": 3,
            "window": {
                "first_disabled_route_at": "2026-09-17T04:00:00+00:00",
                "last_disabled_route_at": "2026-09-17T08:00:00+00:00",
            },
        }
        grade = validator.grade_run_log(log)
        assert grade.verdict == "FAIL"
        assert any("routing divergence" in r.lower() for r in grade.reasons)


class TestContaminationSemanticsUnchanged:
    """VOID semantics survive the new window class."""

    def test_legacy_log_overlapping_contamination_still_fails(self) -> None:
        """The 15Sep poisoning window still voids a legacy log spanning it."""
        validator = _load_validator()
        log = {
            "routing": {"enabled_at_start": True},
            "started_at": "2026-09-01T00:00:00+00:00",
            "ended_at": "2026-09-16T00:00:00+00:00",
            "unhandled_exceptions": 0,
            "cycles_completed": 120,
            "counters": {"success": 3, "disabled": 0, "error": 0},
        }
        grade = validator.grade_run_log(log)
        assert grade.verdict == "FAIL"
        assert any("contamination window" in r for r in grade.reasons)

    def test_contamination_and_outage_coexist(self) -> None:
        """A run spanning BOTH window classes FAILs and still carries the
        outage disclosure (annotations ride on any verdict)."""
        validator = _load_validator()
        log = {
            "routing": {"enabled_at_start": True},
            "started_at": "2026-09-10T00:00:00+00:00",
            "ended_at": "2026-09-25T00:00:00+00:00",
            "unhandled_exceptions": 0,
            "cycles_completed": 120,
            "counters": {"success": 3, "disabled": 0, "error": 0},
        }
        grade = validator.grade_run_log(log)
        assert grade.verdict == "FAIL"
        assert any("contamination window" in r for r in grade.reasons)
        assert any("documented outage window" in note for note in grade.annotations)


class TestGradeCliSurfacesAnnotations:
    """The validator CLI prints annotations -- the 30Sep grading
    checkpoint reads exactly that output."""

    def test_annotations_printed_for_eligible_run(
        self, capsys: pytest.CaptureFixture[str], tmp_path: Path
    ) -> None:
        validator = _load_validator()
        log_path = tmp_path / "p5_forward_test_outage_fixture.json"
        log_path.write_text(json.dumps(_outage_log()), encoding="utf-8")
        argv_backup = sys.argv
        sys.argv = ["verify_p5_forward_test.py", str(log_path)]
        try:
            rc = validator.main()
        finally:
            sys.argv = argv_backup
        captured = capsys.readouterr().out
        assert "documented outage window" in captured
        assert "NOTE" in captured
        assert rc == 0
        # Regression pin: the affected-run summary keeps its PASS signal.
        assert "P5 forward-test conformance: PASS" in captured
