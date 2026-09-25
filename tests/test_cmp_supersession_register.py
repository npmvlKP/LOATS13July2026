"""Content pins for the CMP Supersession Register (ADR-0019 / F9-L-05).

The register (docs/CMP-SUPERSESSION-REGISTER.md) is the single authority
for "where the build deliberately differs from CMP text, and by what
authority?" These pins make silent erosion visible: deleting the register,
gutting its table, dropping the maintenance rule, or losing the authority
references fails CI instead of the next review re-deriving the delta by
hand (the exact cost FR9 F9-L-05 recorded).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
REGISTER = REPO_ROOT / "docs" / "CMP-SUPERSESSION-REGISTER.md"

ROW_PATTERN = re.compile(
    r"^\| S-\d+ \|[^|]+\|[^|]+\|[^|]+\| "
    r"(OPEN|ACCEPTED|RESTORED|SUPERSEDED)[^|]*\|$"
)


@pytest.fixture(scope="module")
def register_text() -> str:
    assert REGISTER.exists(), (
        "docs/CMP-SUPERSESSION-REGISTER.md must be tracked in-tree (ADR-0019)"
    )
    return REGISTER.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def register_rows(register_text: str) -> list[str]:
    return [line for line in register_text.splitlines() if "| S-" in line]


def test_register_exists_with_authority(register_text: str) -> None:
    assert "ADR-0019" in register_text
    assert "Maintenance rule" in register_text
    assert "same PR" in register_text


def test_every_row_is_well_formed_with_a_known_state(
    register_rows: list[str],
) -> None:
    assert register_rows, "register table must not be empty"
    malformed = [row for row in register_rows if not ROW_PATTERN.match(row)]
    assert not malformed, malformed


def test_row_count_floor(register_rows: list[str]) -> None:
    # The inventory landed with 15 rows (S-01..S-15); a row may be
    # retired only with its evidence in the closing PR.
    assert len(register_rows) >= 15, len(register_rows)


def test_minimum_authority_set_is_cited(register_text: str) -> None:
    for authority in (
        "ADR-0003",
        "ADR-0004",
        "ADR-0005",
        "ADR-0006",
        "ADR-0007",
        "ADR-0016",
        "ADR-0017",
        "ADR-0019",
        "ADR-0020",
    ):
        assert authority in register_text, authority


def test_pr_commits_are_cited_for_restored_rows(register_text: str) -> None:
    # Restored/conformed rows carry their merge evidence.
    for citation in ("9f82a21", "7014186", "5f634ba", "633daae"):
        assert citation in register_text, citation


def test_open_rows_name_their_resolution_slot(
    register_rows: list[str],
) -> None:
    open_rows = [row for row in register_rows if "| OPEN" in row]
    assert open_rows, "the landing-state OPEN rows must be present"
    for row in open_rows:
        assert any(
            marker in row for marker in ("30Sep", "wave", "checkpoint", "R-01", "R-04")
        ), row


def test_reconciliation_protocol_is_recorded(register_text: str) -> None:
    assert "Reconciliation protocol" in register_text
    assert "Register-absent deltas are findings" in register_text
