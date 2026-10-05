"""Pin the tracked risk register (docs/RISK-REGISTER.md) to its current,
evidence-backed state.

Why this exists: the register previously lived only in the chat/paste
transcript, and pasted records lagged the repository twice (F9-C-02: the
pasted context was already closed at HEAD; F9-H-03: the pasted open-High
finding was already closed by PR #65). Landing the register in-tree with
content pins turns a status drift into a visible, testable change instead
of a silent contradiction between transcript and repository.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
REGISTER = REPO_ROOT / "docs" / "RISK-REGISTER.md"


@pytest.fixture(scope="module")
def register_text() -> str:
    assert REGISTER.exists(), "docs/RISK-REGISTER.md must be tracked in-tree"
    return REGISTER.read_text(encoding="utf-8")


def test_p1_items_carry_the_checkpoint_due_date(register_text: str) -> None:
    # R-01 was the only P1 OPEN at the 2026-09-30 checkpoint and is now
    # CLOSED by ADR-0021 (decision (b), the checkpoint wave). R-02
    # (kill-switch span proof) closed same-day earlier (ADR-0018,
    # 2026-09-21). Both P1 rows pin their closures.
    p1_rows = [
        line
        for line in register_text.splitlines()
        if line.startswith("| R-") and "| P1 |" in line
    ]
    assert len(p1_rows) == 2, p1_rows
    r01 = next(row for row in p1_rows if row.startswith("| R-01 "))
    r02 = next(row for row in p1_rows if row.startswith("| R-02 "))
    assert "CLOSED by ADR-0021" in r01, r01
    assert "CLOSED by ADR-0018" in r02, r02


def test_r01_cites_the_measured_cycle_population(register_text: str) -> None:
    # The live :8001/metrics scrape at the register's snapshot.
    assert "count=2183" in register_text
    assert "target_compliance_count=0" in register_text


def test_r01_closure_names_the_decision_and_its_evidence(
    register_text: str,
) -> None:
    # ADR-0021 (30Sep checkpoint): the register names the amended
    # budget, the compliance populations the decision cited, and the
    # same-wave enforcement deliverable.
    assert "ADR-0021" in register_text
    assert "0/26,413" in register_text
    assert "0/1,278" in register_text
    assert "latency_budget.py" in register_text


def test_r02_closure_names_the_disclosure_and_its_bound(
    register_text: str,
) -> None:
    # Closed by ADR-0018 (2026-09-21): the register still names the
    # verifier's exact pre-guard hole naming ("generation(s) 1..3"),
    # the ADR that closed it, and the fail-closed bound that keeps the
    # disclosure honest (post-guard/unknown holes still FAIL-closed).
    assert "generation(s) 1..3" in register_text
    assert "ADR-0018" in register_text
    assert "FAIL-closed" in register_text


def test_closed_references_cite_the_merge_commits(register_text: str) -> None:
    assert "07ab8ae" in register_text  # PR #65 (F9-H-03 BG-1 close-out)
    assert "633daae" in register_text  # PR #66 (F9-H-05 CMP P3)


def test_snapshot_identity_is_recorded(register_text: str) -> None:
    # Snapshot discipline: the register names the HEAD sha and the
    # post-merge CI run its statuses were reconciled against.
    assert "633daae" in register_text
    assert "35571352961" in register_text


def test_r19_closure_gates_every_support_job(register_text: str) -> None:
    # R-19 (H-02) closed 05Oct2026: the row must name the gating call in
    # all four public job-entry methods and the RED-proven test net —
    # a row that claims the fix without naming the mechanism drifts
    # silently the next time scheduler.py is refactored.
    r19 = next(
        line for line in register_text.splitlines() if line.startswith("| R-19 ")
    )
    assert "| P2-fixed |" in r19, r19
    assert "_check_kill_switch()" in r19, r19
    for method in (
        "check_market_status",
        "run_market_activation",
        "run_data_cleanup",
        "run_backtest_sanity_check",
    ):
        assert method in r19, (method, r19)
    assert "tests/test_scheduler_kill_switch_gate.py" in r19, r19
    assert "fix/r19-scheduler-halt-gate-05oct" in r19, r19
