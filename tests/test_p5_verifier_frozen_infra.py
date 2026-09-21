"""Frozen-infrastructure pins for scripts/verify_p5_forward_test.py.

The 30Sep CMP P5 grading checkpoint must read the SAME gate semantics the
span was produced under: these tests pin the verifier's grading behavior by
direct invocation (the module is loaded from scripts/ exactly the way the
official grader runs it), so any mid-stream change to the gate is a visible,
RED-proven test change instead of a silent drift.

Pinned behaviors (P5-OPS-01 and the disclosure contract):

- writer-generation derivation from the event stream (fresh-start window is
  generation 1; ``writer_claimed`` opens a generation; only
  ``kill_switch_verified`` proves its generation; ``kill_switch_alarm``
  proves the probe RAN and failed -- the generation stays unproven);
- span-attached grading (an ENDED run with any unproven generation
  hard-fails; an ongoing run stays INCOMPLETE with the hole named;
  a fully proven span produces no reason);
- documented-outage / market-data availability annotations are
  NON-GRADING and fail closed to honest disclosure on unknown shapes.
"""

from __future__ import annotations

import datetime
import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
VERIFIER = REPO_ROOT / "scripts" / "verify_p5_forward_test.py"


def _load_verifier() -> Any:
    spec = importlib.util.spec_from_file_location("_p5_verifier_frozen", VERIFIER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # Register before exec: the verifier's dataclasses resolve postponed
    # annotations through sys.modules[cls.__module__] at import time.
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(spec.name, None)
        raise
    return module


@pytest.fixture(scope="module")
def verifier() -> Any:
    return _load_verifier()


def _ended() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC)


class TestSpanGenerationDerivation:
    def test_fresh_start_window_is_generation_1(self, verifier: Any) -> None:
        # Events BEFORE the first writer_claimed form the fresh-start
        # writer's generation; it closes unproven unless an event proves it.
        run_log = {
            "events": [
                {"timestamp": "t0", "kind": "routing_enabled"},
                {"timestamp": "t1", "kind": "writer_claimed"},
                {"timestamp": "t2", "kind": "kill_switch_verified"},
            ]
        }
        generations = verifier._span_kill_switch_generations(run_log)
        assert [g["generation"] for g in generations] == [1, 2]
        assert generations[0]["verified"] is None
        assert generations[1]["verified"] is True
        assert verifier._unproven_kill_switch_generations(generations) == [1]

    def test_log_starting_with_claim_has_no_fresh_start_window(
        self, verifier: Any
    ) -> None:
        run_log = {
            "events": [
                {"timestamp": "t1", "kind": "writer_claimed"},
                {"timestamp": "t2", "kind": "kill_switch_verified"},
            ]
        }
        generations = verifier._span_kill_switch_generations(run_log)
        assert [g["generation"] for g in generations] == [1]
        assert generations[0]["verified"] is True
        assert verifier._unproven_kill_switch_generations(generations) == []

    def test_alarm_leaves_generation_unproven(self, verifier: Any) -> None:
        # An alarm is evidence the probe RAN and failed: has_proof True,
        # verified False -- an unverifiable halt proves nothing.
        run_log = {
            "events": [
                {"timestamp": "t1", "kind": "writer_claimed"},
                {"timestamp": "t2", "kind": "kill_switch_alarm"},
            ]
        }
        generations = verifier._span_kill_switch_generations(run_log)
        assert generations[0]["verified"] is False
        assert generations[0]["has_proof"] is True
        assert verifier._unproven_kill_switch_generations(generations) == [1]


class TestSpanAttachedGrading:
    def test_ended_run_with_unproven_generation_hard_fails(self, verifier: Any) -> None:
        run_log = {
            "events": [
                {"timestamp": "t0", "kind": "routing_enabled"},
                {"timestamp": "t1", "kind": "writer_claimed"},
                {"timestamp": "t2", "kind": "kill_switch_verified"},
            ]
        }
        reasons: list[str] = []
        hard = verifier._grade_span_kill_switch_proof(run_log, reasons, _ended())
        assert hard is True
        assert any("generation(s)" in r for r in reasons)

    def test_ongoing_run_stays_incomplete_with_named_hole(self, verifier: Any) -> None:
        run_log = {
            "events": [
                {"timestamp": "t0", "kind": "routing_enabled"},
                {"timestamp": "t1", "kind": "writer_claimed"},
                {"timestamp": "t2", "kind": "kill_switch_verified"},
            ]
        }
        reasons: list[str] = []
        hard = verifier._grade_span_kill_switch_proof(run_log, reasons, None)
        assert hard is False
        assert any("KILL-SWITCH PROOF IS NOT SPAN-ATTACHED" in r for r in reasons)

    def test_fully_proven_span_produces_no_reason(self, verifier: Any) -> None:
        run_log = {
            "events": [
                {"timestamp": "t1", "kind": "writer_claimed"},
                {"timestamp": "t2", "kind": "kill_switch_verified"},
            ]
        }
        reasons: list[str] = []
        hard = verifier._grade_span_kill_switch_proof(run_log, reasons, _ended())
        assert hard is False
        assert reasons == []


class TestGateWeakeningMutations:
    """Mutation legs: weakening a pinned behavior must flip the net red."""

    def test_post_guard_generation_without_proof_is_still_a_hole(
        self, verifier: Any
    ) -> None:
        # A post-guard resume that skips its probe must NOT grade proven.
        run_log = {
            "events": [
                {"timestamp": "t1", "kind": "writer_claimed"},
                {"timestamp": "t2", "kind": "kill_switch_verified"},
                {"timestamp": "t3", "kind": "writer_claimed"},
            ]
        }
        generations = verifier._span_kill_switch_generations(run_log)
        assert verifier._unproven_kill_switch_generations(generations) == [2]
        reasons: list[str] = []
        assert (
            verifier._grade_span_kill_switch_proof(run_log, reasons, _ended()) is True
        )

    def test_alarm_cannot_substitute_for_verified(self, verifier: Any) -> None:
        run_log = {
            "events": [
                {"timestamp": "t1", "kind": "writer_claimed"},
                {"timestamp": "t2", "kind": "kill_switch_alarm"},
            ]
        }
        generations = verifier._span_kill_switch_generations(run_log)
        assert verifier._unproven_kill_switch_generations(generations) == [1]


class TestDisclosureAnnotationsNeverGrade:
    def test_observed_activity_discloses_nothing(self, verifier: Any) -> None:
        assert (
            verifier._collect_market_data_annotations({"cycle_activity_observed": True})
            == []
        )

    def test_unverified_probe_failure_discloses_verbatim_reason(
        self, verifier: Any
    ) -> None:
        notes = verifier._collect_market_data_annotations(
            {"status": "unverified", "reason": "boom"}
        )
        assert len(notes) == 1
        assert "boom" in notes[0]

    def test_malformed_shape_fails_closed_to_unverified(self, verifier: Any) -> None:
        notes = verifier._collect_market_data_annotations(
            {"cycle_activity": "not-a-known-shape"}
        )
        assert notes
        assert "malformed" in notes[0]

    def test_explicit_zero_activity_is_disclosed(self, verifier: Any) -> None:
        notes = verifier._collect_market_data_annotations(
            {"cycle_activity_observed": False}
        )
        assert notes
        assert "zero cycle activity" in notes[0]

    def test_non_dict_availability_discloses_nothing(self, verifier: Any) -> None:
        assert verifier._collect_market_data_annotations(None) == []
