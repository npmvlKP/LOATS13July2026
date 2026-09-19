"""P5-OPS-01 span-invariant net: generation-scoped kill-switch proof,
market-data availability evidence, and a PowerShell-safe evidence battery.

Three register items from the 19Sep2026 adversarial review, pinned RED-first:

1. Kill-switch proof is resume-attached, not span-attached (P1, H2/H7).
   Run 20260916_140341 carries exactly one ``kill_switch_verified`` event --
   the fourth writer generation, 2.46 d into the span. Until now an ENDED run
   graded only the top-level ``kill_switch_verified`` field, so "clean under
   PID 19316 since 19Sep" would have passed as "clean since 16Sep". The
   grader now re-derives every writer generation from the ``writer_claimed``
   events (the fresh-start window before the first claim is a generation
   too) and FAIL-closes an ENDED run unless EACH generation carries its own
   verification event.
2. The operator reported the OpenAlgo analyzer surface (``127.0.0.1:5000``,
   Zerodha feeds behind it) serving live market data through market hours.
   LOATS cannot read OpenAlgo's internal logs (separate process, separate
   host surface); the span-visible evidence is cycle activity, the
   orchestrator running state and the per-source breaker fleet, folded each
   sample as ``market_data_availability`` (annotation-only: never graded,
   never fabricated -- a probe failure records an explicit ``unverified``
   shape the CLI surfaces verbatim).
3. The 19Sep gate battery wrote ``$fail += (($LASTEXITCODE -ne 1) * 2)``:
   PowerShell 5.1 defines no ``[bool] * [int]`` operator, the ledger aborted
   with NotADefinedOperationForType, and the summary echoed the placeholder
   instead of a count. ``verify_exit_code_battery`` is the supported
   composition; the pin proves the broken shape can never survive in the
   documented command surface again (direct injection into the canonical
   session lines raises).
"""

from __future__ import annotations

import asyncio
import datetime
import importlib.util
import io
import json
import sys
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[1]
RUNNER = REPO_ROOT / "scripts" / "run_p5_forward_test.py"
VALIDATOR = REPO_ROOT / "scripts" / "verify_p5_forward_test.py"


def _load_runner() -> Any:
    spec = importlib.util.spec_from_file_location("p5_runner_p5ops01", RUNNER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_validator() -> Any:
    spec = importlib.util.spec_from_file_location("p5_validator_p5ops01", VALIDATOR)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class _FakeSystem:
    def __init__(self, running: bool = True) -> None:
        self.running = running


def _eligible_ended_log() -> dict[str, Any]:
    """An otherwise fully-eligible ENDED run (14d span, measured activity)."""
    return {
        "routing": {"enabled_at_start": True},
        "started_at": "2026-08-01T00:00:00+00:00",
        "ended_at": "2026-08-16T00:00:00+00:00",
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
            {
                "timestamp": "2026-08-01T00:00:00+00:00",
                "kind": "writer_claimed",
                "detail": "PID 111",
            },
            {
                "timestamp": "2026-08-01T00:00:11+00:00",
                "kind": "kill_switch_verified",
                "detail": "gen 1 verified",
            },
            {
                "timestamp": "2026-08-08T00:00:00+00:00",
                "kind": "writer_claimed",
                "detail": "PID 222",
            },
            {
                "timestamp": "2026-08-08T00:00:11+00:00",
                "kind": "kill_switch_verified",
                "detail": "gen 2 verified",
            },
        ],
    }


def _multi_generation_ongoing_log(tmp_path: Path) -> Path:
    """An ongoing log shaped like live run 20260916_140341: the fresh-start
    window plus three claimed writer generations, only the LAST carrying the
    kill-switch verification event."""
    run_log = tmp_path / "run.json"
    run_log.write_text(
        json.dumps(
            {
                "routing": {"enabled_at_start": True},
                "started_at": "2026-09-16T14:03:41+00:00",
                "ended_at": None,
                "unhandled_exceptions": 0,
                "restarts": 2,
                "supervisor_pid": 424242,
                "cycles_completed": 0,
                "counters": {"success": 0, "disabled": 0, "error": 0},
                "events": [
                    {
                        "timestamp": "2026-09-16T14:03:46+00:00",
                        "kind": "routing_enabled",
                        "detail": "live supervised run",
                    },
                    {
                        "timestamp": "2026-09-16T23:24:02+00:00",
                        "kind": "writer_claimed",
                        "detail": "PID 1111",
                    },
                    {
                        "timestamp": "2026-09-16T23:24:12+00:00",
                        "kind": "routing_enabled",
                        "detail": "live supervised run (resumed)",
                    },
                    {
                        "timestamp": "2026-09-17T23:05:08+00:00",
                        "kind": "writer_claimed",
                        "detail": "PID 2222",
                    },
                    {
                        "timestamp": "2026-09-17T23:05:19+00:00",
                        "kind": "routing_enabled",
                        "detail": "live supervised run (resumed)",
                    },
                    {
                        "timestamp": "2026-09-19T01:06:52+00:00",
                        "kind": "writer_claimed",
                        "detail": "PID 3333",
                    },
                    {
                        "timestamp": "2026-09-19T01:07:03+00:00",
                        "kind": "kill_switch_verified",
                        "detail": "gen 4 verified",
                    },
                    {
                        "timestamp": "2026-09-19T01:07:03+00:00",
                        "kind": "routing_enabled",
                        "detail": "live supervised run (resumed)",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    return run_log


# ---------------------------------------------------------------------------
# 1. Supervisor: generation model + span-level kill-switch proof
# ---------------------------------------------------------------------------


class TestSpanKillSwitchGenerations:
    """Every writer generation's proof state, re-derived from the events."""

    def test_generations_without_proof_are_listed(self, tmp_path: Path) -> None:
        runner = _load_runner()
        data = json.loads(
            _multi_generation_ongoing_log(tmp_path).read_text(encoding="utf-8")
        )
        generations = runner._span_kill_switch_generations(data)
        # Four generations: the fresh-start window (routing_enabled before
        # any writer_claimed) plus the three claimed resumes.
        assert len(generations) == 4
        assert [g["generation"] for g in generations] == [1, 2, 3, 4]
        assert [g["writer_claimed_at"] for g in generations] == [
            None,
            "2026-09-16T23:24:02+00:00",
            "2026-09-17T23:05:08+00:00",
            "2026-09-19T01:06:52+00:00",
        ]
        assert [g["has_proof"] for g in generations] == [False, False, False, True]
        assert [g["verified"] for g in generations] == [None, None, None, True]
        assert runner._unproven_generations(generations) == [1, 2, 3]

    def test_two_proven_generations_are_clean(self) -> None:
        runner = _load_runner()
        data: dict[str, Any] = dict(_eligible_ended_log())
        data["ended_at"] = None  # two proven generations, run still ongoing
        data["supervisor_pid"] = None
        # The log starts with a ``writer_claimed`` (no fresh-start
        # window): each claim closes its own generation and carries its
        # verification event.
        generations = runner._span_kill_switch_generations(data)
        assert [g["has_proof"] for g in generations] == [True, True]
        assert [g["verified"] for g in generations] == [True, True]
        assert runner._unproven_generations(generations) == []

    def test_latest_generation_verified_hole_confined_to_retired(
        self, tmp_path: Path
    ) -> None:
        runner = _load_runner()
        data = json.loads(
            _multi_generation_ongoing_log(tmp_path).read_text(encoding="utf-8")
        )
        generations = runner._span_kill_switch_generations(data)
        # The CURRENT (latest) writer generation is verified; the hole is
        # confined to the retired generations.
        assert generations[-1]["verified"] is True
        assert runner._unproven_generations(generations) == [1, 2, 3]
        # Without the verification event even the live generation is dark.
        data["events"] = [
            e for e in data["events"] if e["kind"] != "kill_switch_verified"
        ]
        generations = runner._span_kill_switch_generations(data)
        assert runner._unproven_generations(generations) == [1, 2, 3, 4]
        assert generations[-1]["verified"] is not True

    def test_alarm_event_records_verified_false_generation(self) -> None:
        runner = _load_runner()
        data = {
            "events": [
                {
                    "timestamp": "2026-09-16T14:03:46+00:00",
                    "kind": "writer_claimed",
                    "detail": "PID 1",
                },
                {
                    "timestamp": "2026-09-16T14:03:50+00:00",
                    "kind": "kill_switch_alarm",
                    "detail": "probe FAILED",
                },
                {
                    "timestamp": "2026-09-16T14:03:51+00:00",
                    "kind": "routing_enabled",
                    "detail": "live supervised run",
                },
            ]
        }
        generations = runner._span_kill_switch_generations(data)
        assert len(generations) == 1
        # The log STARTS with the claim (no fresh-start window): the
        # alarm lands in the claimed generation.
        assert generations[0]["verified"] is False
        # An alarm is evidence the probe RAN -- but verified False, so the
        # generation stays unproven (an unverifiable halt proves nothing).
        assert runner._unproven_generations(generations) == [1]

    def test_single_fresh_run_without_resumes_is_one_generation(self) -> None:
        runner = _load_runner()
        data: dict[str, Any] = dict(_eligible_ended_log())
        data["events"] = [
            {
                "timestamp": "2026-08-01T00:00:11+00:00",
                "kind": "kill_switch_verified",
                "detail": "verified at start",
            },
        ]
        generations = runner._span_kill_switch_generations(data)
        assert len(generations) == 1
        assert generations[0]["writer_claimed_at"] is None
        assert generations[0]["verified"] is True
        assert runner._unproven_generations(generations) == []

    def test_events_missing_degrades_to_empty_model(self) -> None:
        runner = _load_runner()
        assert runner._span_kill_switch_generations({"events": "garbage"}) == []
        assert runner._span_kill_switch_generations({}) == []


def _ongoing_log_for_sampling(tmp_path: Path) -> Path:
    run_log = tmp_path / "sample.json"
    run_log.write_text(
        json.dumps(
            {
                "routing": {"enabled_at_start": True},
                "started_at": (
                    datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=15)
                ).isoformat(),
                "ended_at": None,
                "unhandled_exceptions": 0,
                "restarts": 1,
                "cycles_completed": 0,
                "counters": {"success": 0, "disabled": 0, "error": 0},
                "events": [],
            }
        ),
        encoding="utf-8",
    )
    return run_log


_ZERO_BASELINE_KEYS = ("success", "disabled", "error")


def _sampling_baseline(run_log: Path) -> dict[str, Any]:
    return {
        "cycles_completed": 0,
        "counters": dict.fromkeys(_ZERO_BASELINE_KEYS, 0),
        "trade_decision_engine_identity": "pid=x;start=y;engine=0x1",
        "run_log_path": str(run_log),
    }


class TestMarketDataAvailabilityFold:
    """Each sample folds span-visible market-data liveness (never graded)."""

    def test_sample_records_market_data_availability(self, tmp_path: Path) -> None:
        runner = _load_runner()
        run_log = _ongoing_log_for_sampling(tmp_path)
        sources = {"technical_analysis": {"state": "closed"}}
        with (
            patch("loats.orchestrator.orchestrator", SimpleNamespace(cycle_count=3)),
            patch(
                "loats.trade_decision.trade_decision_engine",
                SimpleNamespace(
                    get_routing_stats=lambda: dict.fromkeys(_ZERO_BASELINE_KEYS, 0)
                ),
            ),
            patch(
                "loats.alerts.alerts",
                SimpleNamespace(is_kill_switch_active=lambda: False),
            ),
            patch(
                "loats.utils.per_source_breakers.get_source_breaker_status",
                lambda: sources,
            ),
            patch(
                f"{runner.__name__}.collect_disabled_route_rows",
                create=True,
                return_value=[],
            ),
        ):
            runner._sample_live_activity(
                _FakeSystem(running=True), run_log, _sampling_baseline(run_log)
            )
        data = json.loads(run_log.read_text(encoding="utf-8"))
        availability = data["market_data_availability"]
        assert availability["cycle_activity_observed"] is True
        assert availability["orchestrator_running"] is True
        # The fold records each source's real breaker-status dict.
        assert availability["sources"] == {"technical_analysis": {"state": "closed"}}

    def test_zero_activity_is_not_fabricated_into_availability(
        self, tmp_path: Path
    ) -> None:
        runner = _load_runner()
        run_log = _ongoing_log_for_sampling(tmp_path)
        quiet = {
            name: {"state": "closed"}
            for name in (
                "options_flow",
                "price_action",
                "sentiment",
                "technical_analysis",
                "volatility",
            )
        }
        with (
            patch("loats.orchestrator.orchestrator", SimpleNamespace(cycle_count=0)),
            patch(
                "loats.trade_decision.trade_decision_engine",
                SimpleNamespace(
                    get_routing_stats=lambda: dict.fromkeys(_ZERO_BASELINE_KEYS, 0)
                ),
            ),
            patch(
                "loats.alerts.alerts",
                SimpleNamespace(is_kill_switch_active=lambda: False),
            ),
            patch(
                "loats.utils.per_source_breakers.get_source_breaker_status",
                lambda: quiet,
            ),
            patch(
                f"{runner.__name__}.collect_disabled_route_rows",
                create=True,
                return_value=[],
            ),
        ):
            runner._sample_live_activity(
                _FakeSystem(running=True), run_log, _sampling_baseline(run_log)
            )
        data = json.loads(run_log.read_text(encoding="utf-8"))
        # Honest zero: a healthy fleet with no observed cycle delta is
        # recorded AS zero activity, never as evidence of market data.
        assert data["market_data_availability"] == {
            "cycle_activity_observed": False,
            "orchestrator_running": True,
            "sources": {name: {"state": "closed"} for name in quiet},
        }

    def test_breaker_probe_failure_records_unverified(self, tmp_path: Path) -> None:
        runner = _load_runner()
        run_log = _ongoing_log_for_sampling(tmp_path)
        with (
            patch("loats.orchestrator.orchestrator", SimpleNamespace(cycle_count=0)),
            patch(
                "loats.trade_decision.trade_decision_engine",
                SimpleNamespace(
                    get_routing_stats=lambda: dict.fromkeys(_ZERO_BASELINE_KEYS, 0)
                ),
            ),
            patch(
                "loats.alerts.alerts",
                SimpleNamespace(is_kill_switch_active=lambda: False),
            ),
            patch(
                "loats.utils.per_source_breakers.get_source_breaker_status",
                side_effect=RuntimeError("registry down"),
            ),
            patch(
                f"{runner.__name__}.collect_disabled_route_rows",
                create=True,
                return_value=[],
            ),
        ):
            runner._sample_live_activity(
                _FakeSystem(running=True), run_log, _sampling_baseline(run_log)
            )
        data = json.loads(run_log.read_text(encoding="utf-8"))
        availability = data["market_data_availability"]
        assert availability["status"] == "unverified"
        assert "RuntimeError: registry down" in availability["reason"]
        # A probe failure must not leave a fake clean shape behind.
        assert "cycle_activity_observed" not in availability

    def test_fold_failure_never_kills_the_sample(self, tmp_path: Path) -> None:
        """The fold is evidence, not a liveness hazard: any exception inside
        it must degrade to the unverified shape, never abort the sample."""
        runner = _load_runner()
        run_log = _ongoing_log_for_sampling(tmp_path)
        with (
            patch("loats.orchestrator.orchestrator", SimpleNamespace(cycle_count=2)),
            patch(
                "loats.trade_decision.trade_decision_engine",
                SimpleNamespace(
                    get_routing_stats=lambda: dict.fromkeys(_ZERO_BASELINE_KEYS, 0)
                ),
            ),
            patch(
                "loats.alerts.alerts",
                SimpleNamespace(is_kill_switch_active=lambda: False),
            ),
            patch(
                "loats.utils.per_source_breakers.get_source_breaker_status",
                lambda: (_ for _ in ()).throw(OSError(10048, "boom")),
            ),
            patch(
                f"{runner.__name__}.collect_disabled_route_rows",
                create=True,
                return_value=[],
            ),
        ):
            runner._sample_live_activity(
                _FakeSystem(), run_log, _sampling_baseline(run_log)
            )
        data = json.loads(run_log.read_text(encoding="utf-8"))
        # The sample landed (counters folded) with availability degraded.
        assert data["cycles_completed"] == 2
        assert data["market_data_availability"]["status"] == "unverified"


# ---------------------------------------------------------------------------
# 3. Grader: kill-switch proof is span-attached (fail-closed on ENDED runs)
# ---------------------------------------------------------------------------


class TestGraderSpanAttachedKillSwitch:
    """An ENDED run needs proof in EVERY writer generation, not just the last."""

    def test_ended_run_with_unproven_generations_fails(self) -> None:
        validator = _load_validator()
        log = _eligible_ended_log()
        # Degrade to the live 20260916_140341 shape: only the LAST
        # generation carries the verification event.
        log["events"] = [
            {
                "timestamp": "2026-08-01T00:00:00+00:00",
                "kind": "writer_claimed",
                "detail": "PID 111",
            },
            {
                "timestamp": "2026-08-01T00:00:05+00:00",
                "kind": "routing_enabled",
                "detail": "gen 1 (no proof)",
            },
            {
                "timestamp": "2026-08-08T00:00:00+00:00",
                "kind": "writer_claimed",
                "detail": "PID 222",
            },
            {
                "timestamp": "2026-08-08T00:00:11+00:00",
                "kind": "kill_switch_verified",
                "detail": "gen 2 verified",
            },
        ]
        grade = validator.grade_run_log(log)
        assert grade.verdict == "FAIL"
        assert any("KILL-SWITCH PROOF" in r for r in grade.reasons)
        assert any("generation(s) 1" in r for r in grade.reasons)

    def test_ended_run_all_generations_proven_passes(self) -> None:
        validator = _load_validator()
        grade = validator.grade_run_log(_eligible_ended_log())
        assert grade.verdict == "PASS", grade.reasons

    def test_ongoing_run_with_unproven_generations_stays_incomplete(self) -> None:
        validator = _load_validator()
        log = _eligible_ended_log() | {"ended_at": None}
        log["events"] = [
            {
                "timestamp": "2026-08-01T00:00:00+00:00",
                "kind": "writer_claimed",
                "detail": "PID 111",
            },
            {
                "timestamp": "2026-08-01T00:00:05+00:00",
                "kind": "routing_enabled",
                "detail": "gen 1 (no proof)",
            },
        ]
        grade = validator.grade_run_log(log)
        assert grade.verdict == "INCOMPLETE"
        assert any("KILL-SWITCH PROOF" in r for r in grade.reasons)

    def test_grader_message_carries_market_data_verdict(self) -> None:
        validator = _load_validator()
        log = _eligible_ended_log() | {
            "market_data_availability": {
                "status": "unverified",
                "reason": "RuntimeError: registry down",
            }
        }
        grade = validator.grade_run_log(log)
        # Annotation-only: the verdict never flips on availability.
        assert grade.verdict == "PASS"
        assert any(
            "market-data availability: unverified" in note for note in grade.annotations
        )
        zero = _eligible_ended_log() | {
            "market_data_availability": {
                "cycle_activity_observed": False,
                "orchestrator_running": True,
                "sources": {"technical_analysis": "closed"},
            }
        }
        grade_zero = validator.grade_run_log(zero)
        assert grade_zero.verdict == "PASS"
        assert any(
            "market-data availability: zero" in note for note in grade_zero.annotations
        )
        observed = _eligible_ended_log() | {
            "market_data_availability": {
                "cycle_activity_observed": True,
                "orchestrator_running": True,
                "sources": {"technical_analysis": "closed"},
            }
        }
        grade_observed = validator.grade_run_log(observed)
        assert grade_observed.verdict == "PASS"
        assert grade_observed.annotations == ()


# ---------------------------------------------------------------------------
# 4. CLI + evidence-battery ergonomics
# ---------------------------------------------------------------------------


class TestStatusAndBattery:
    """The operator surface announces span invariants; the battery composes
    exit codes without PowerShell boolean arithmetic."""

    def test_status_output_announces_invariants(self, tmp_path: Path) -> None:
        runner = _load_runner()
        run_log = _multi_generation_ongoing_log(tmp_path)
        data = json.loads(run_log.read_text(encoding="utf-8"))
        data["last_sampled_at"] = datetime.datetime.now(datetime.UTC).isoformat()
        data["supervisor_pid"] = None
        data["market_data_availability"] = {
            "status": "unverified",
            "reason": "RuntimeError: registry down",
        }
        run_log.write_text(json.dumps(data), encoding="utf-8")
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            rc = runner._status(run_log)
        out = buffer.getvalue()
        assert rc == 0
        assert "kill-switch span proof:" in out
        assert "generation(s) 1..3 lack the verification event" in out
        assert "verdict will be INCOMPLETE" in out
        assert "market-data availability: unverified" in out

    def test_status_reports_live_verified_span(self, tmp_path: Path) -> None:
        runner = _load_runner()
        data: dict[str, Any] = dict(_eligible_ended_log())
        data["ended_at"] = None
        data["supervisor_pid"] = None
        data["last_sampled_at"] = datetime.datetime.now(datetime.UTC).isoformat()
        run_log = tmp_path / "clean.json"
        run_log.write_text(json.dumps(data), encoding="utf-8")
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            rc = runner._status(run_log)
        out = buffer.getvalue()
        assert rc == 0
        assert "all writer generations verified" in out

    def test_battery_blocks_ps1_boolean_multiplication(self) -> None:
        runner = _load_runner()
        # The exact 19Sep session lines (quality-gate battery): driving
        # them through the documented composition helper must raise
        # instead of aborting a PowerShell session mid-ledger.
        snapshot_leg = (
            "    & $PY scripts\\verify_p5_forward_test.py "
            "tests\\fixtures\\p5_run_log_20260912_150243_snapshot.json; "
            "$fail += (($LASTEXITCODE -ne 1) * 2)"
        )
        try:
            runner.verify_exit_code_battery(snapshot_leg)
        except RuntimeError as exc:
            assert "$LASTEXITCODE" in str(exc)
            assert "verify_exit_code_battery" in str(exc)
        else:
            raise AssertionError("RuntimeError not raised for the poisoned leg")
        summary_leg = '    "QUALITY_GATES_FAILURES=$fail"  # expected: 0'
        try:
            runner.verify_exit_code_battery(summary_leg)
        except RuntimeError as exc:
            assert "$LASTEXITCODE" in str(exc)
        else:
            raise AssertionError("RuntimeError not raised for the summary leg")

    def test_battery_failure_ledger_is_powershell_safe(self) -> None:
        runner = _load_runner()
        # Failed gates: the returned value is BOTH the failure count for
        # the summary echo AND a nonzero process exit code -- no
        # [bool]*[int] multiplication anywhere.
        assert runner.verify_exit_code_battery(0, 1) == 1
        assert runner.verify_exit_code_battery(1, 0, 1) == 2
        assert runner.verify_exit_code_battery(0, 0) == 0
        assert runner.verify_exit_code_battery() == 0


# ---------------------------------------------------------------------------
# 5. Supervisor continuity: the supervised window ends with ended_at marked
# ---------------------------------------------------------------------------


class TestSupervisedWindowCloses:
    """_supervise_live marks ended_at on every exit (recovery-loop proof)."""

    def test_supervise_exit_marks_ended_at_on_demand(self, tmp_path: Path) -> None:
        runner = _load_runner()
        run_log = _ongoing_log_for_sampling(tmp_path)
        with (
            patch("loats.orchestrator.orchestrator", SimpleNamespace(cycle_count=0)),
            patch(
                "loats.trade_decision.trade_decision_engine",
                SimpleNamespace(
                    get_routing_stats=lambda: dict.fromkeys(_ZERO_BASELINE_KEYS, 0)
                ),
            ),
            patch(
                "loats.alerts.alerts",
                SimpleNamespace(is_kill_switch_active=lambda: False),
            ),
            patch(
                f"{runner.__name__}.collect_disabled_route_rows",
                create=True,
                return_value=[],
            ),
        ):
            unhandled = asyncio.run(
                runner._supervise_live(
                    _FakeSystem(),
                    run_log,
                    _sampling_baseline(run_log),
                    duration=0.05,
                    task=None,
                )
            )
        assert unhandled == 0
        data = json.loads(run_log.read_text(encoding="utf-8"))
        assert data["ended_at"] is not None
