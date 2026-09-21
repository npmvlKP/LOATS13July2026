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
- R-02 amendment (ADR-0018, 2026-09-21): generations that OPENED before
  P5-OPS-01 went live disclose via a NON-GRADING annotation instead of
  failing the span; post-guard and unknown-vintage holes still hard-fail;
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


class TestGenerationOpeningStamp:
    """R-02 amendment (ADR-0018): every generation carries its opening stamp."""

    def test_fresh_start_window_opens_at_first_event(self, verifier: Any) -> None:
        # The fresh-start writer's window opens with the FIRST event it
        # recorded (the live 20260916_140341 log: routing_enabled at
        # 14:03:46Z, 9.3 h before the first claim).
        run_log = {
            "events": [
                {"timestamp": "2026-09-16T14:03:46+00:00", "kind": "routing_enabled"},
                {"timestamp": "2026-09-16T23:24:02+00:00", "kind": "writer_claimed"},
                {
                    "timestamp": "2026-09-19T01:07:03+00:00",
                    "kind": "kill_switch_verified",
                },
            ]
        }
        generations = verifier._span_kill_switch_generations(run_log)
        assert generations[0]["opened_at"] == "2026-09-16T14:03:46+00:00"
        assert generations[1]["opened_at"] == "2026-09-16T23:24:02+00:00"

    def test_stampless_events_keep_opened_at_unknown(self, verifier: Any) -> None:
        # A generation whose opening stamp is absent/malformed must NOT
        # look discloseable: unknown vintage grades strictly.
        run_log = {
            "events": [
                {"kind": "routing_enabled"},
                {"kind": "writer_claimed"},
                {"kind": "kill_switch_verified"},
            ]
        }
        generations = verifier._span_kill_switch_generations(run_log)
        assert generations[0]["opened_at"] is None
        assert generations[1]["opened_at"] == ""


class TestPreGuardDisclosureAmendment:
    """R-02 amendment (ADR-0018): pre-guard holes disclose, post-guard fail.

    Parity contract from the register: a generation whose writer ran
    BEFORE the P5-OPS-01 probe existed cannot emit the verification
    event -- demanding it demands the logically impossible. Those
    generations become a named NON-GRADING disclosure; every generation
    that opened at-or-after the guard cutoff is graded exactly as
    before (unknown vintage included).
    """

    def test_pre_guard_generations_disclose_not_fail(self, verifier: Any) -> None:
        # The live 20260916_140341 shape: fresh-start window plus two
        # pre-guard claims, all unproven; the post-guard generation proves.
        run_log = {
            "events": [
                {"timestamp": "2026-09-16T14:03:46+00:00", "kind": "routing_enabled"},
                {"timestamp": "2026-09-16T23:24:02+00:00", "kind": "writer_claimed"},
                {"timestamp": "2026-09-17T23:05:08+00:00", "kind": "writer_claimed"},
                {"timestamp": "2026-09-19T01:06:52+00:00", "kind": "writer_claimed"},
                {
                    "timestamp": "2026-09-19T01:07:03+00:00",
                    "kind": "kill_switch_verified",
                },
            ]
        }
        generations = verifier._span_kill_switch_generations(run_log)
        assert verifier._pre_guard_kill_switch_generations(generations) == [1, 2, 3]
        reasons: list[str] = []
        annotations: list[str] = []
        hard = verifier._grade_span_kill_switch_proof(
            run_log, reasons, _ended(), annotations
        )
        assert hard is False  # was True before the amendment
        assert reasons == []  # the disclosed hole never enters grading reasons
        assert len(annotations) == 1
        assert "generation(s) 1..3" in annotations[0]
        assert "before the verification probe existed" in annotations[0]
        assert "2026-09-19T00:00:00+00:00" in annotations[0]

    def test_mixed_holes_disclose_preguard_and_fail_postguard(
        self, verifier: Any
    ) -> None:
        run_log = {
            "events": [
                {"timestamp": "2026-09-16T14:03:46+00:00", "kind": "routing_enabled"},
                {"timestamp": "2026-09-16T23:24:02+00:00", "kind": "writer_claimed"},
                {"timestamp": "2026-09-19T01:06:52+00:00", "kind": "writer_claimed"},
            ]
        }
        generations = verifier._span_kill_switch_generations(run_log)
        # Generations 1 (fresh-start window) and 2 (16Sep claim) opened
        # before the cutoff; generation 3 (19Sep claim) opened after it.
        assert verifier._pre_guard_kill_switch_generations(generations) == [1, 2]
        reasons: list[str] = []
        annotations: list[str] = []
        hard = verifier._grade_span_kill_switch_proof(
            run_log, reasons, _ended(), annotations
        )
        assert hard is True
        assert any("generation(s) 3" in r for r in reasons)  # post-guard only
        assert any("generation(s) 1..2" in a for a in annotations)  # disclosure rides

    def test_cutoff_boundary_generation_is_strictly_graded(self, verifier: Any) -> None:
        # A writer that opened EXACTLY at the cutoff is post-guard (the
        # probe was live from that instant): no disclosure, hole hard-fails.
        run_log = {
            "events": [
                {"timestamp": "2026-09-19T00:00:00+00:00", "kind": "writer_claimed"},
            ]
        }
        generations = verifier._span_kill_switch_generations(run_log)
        assert verifier._pre_guard_kill_switch_generations(generations) == []
        reasons: list[str] = []
        hard = verifier._grade_span_kill_switch_proof(run_log, reasons, _ended(), [])
        assert hard is True
        assert any("generation(s) 1" in r for r in reasons)

    def test_unknown_vintage_stays_strictly_graded(self, verifier: Any) -> None:
        # Synthetic/unparseable stamps cannot earn the disclosure: the
        # gate-weakening mutation net keeps its exact meaning.
        run_log = {
            "events": [
                {"timestamp": "t1", "kind": "writer_claimed"},
            ]
        }
        generations = verifier._span_kill_switch_generations(run_log)
        assert verifier._pre_guard_kill_switch_generations(generations) == []
        reasons: list[str] = []
        hard = verifier._grade_span_kill_switch_proof(run_log, reasons, _ended(), [])
        assert hard is True

    def test_ended_pre_guard_run_grades_pass_with_disclosure(
        self, verifier: Any
    ) -> None:
        # End-to-end: an otherwise fully eligible ENDED run carrying ONLY
        # pre-guard holes grades PASS with the disclosure riding as a
        # NOTE -- the 30Sep checkpoint reads disclosures from the CLI.
        run_log = {
            "routing": {"enabled_at_start": True},
            "started_at": "2026-09-05T14:03:41+00:00",
            "ended_at": "2026-09-21T04:38:09+00:00",
            "unhandled_exceptions": 0,
            "cycles_completed": 5000,
            "counters": {
                "success": 400,
                "disabled": 0,
                "error": 0,
                "routed_decisions": 400,
                "routing_divergence_detected": 0,
            },
            "disabled_routes_during_enabled_window": {
                "count": 0,
                "window": {
                    "first_disabled_route_at": None,
                    "last_disabled_route_at": None,
                },
            },
            "kill_switch_verified": True,
            "kill_switch_active_at_start": False,
            "events": [
                {"timestamp": "2026-09-16T14:03:46+00:00", "kind": "routing_enabled"},
                {"timestamp": "2026-09-16T23:24:02+00:00", "kind": "writer_claimed"},
                {"timestamp": "2026-09-17T23:05:08+00:00", "kind": "writer_claimed"},
                {"timestamp": "2026-09-19T01:06:52+00:00", "kind": "writer_claimed"},
                {
                    "timestamp": "2026-09-19T01:07:03+00:00",
                    "kind": "kill_switch_verified",
                },
            ],
        }
        grade = verifier.grade_run_log(run_log)
        assert grade.verdict == "PASS", grade.reasons
        assert any("pre-guard" in note for note in grade.annotations)


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
