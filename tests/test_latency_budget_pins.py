"""ADR-0021 latency-budget enforcement pins (R-01 decision (b) wave).

Pins, per the S-14 rider work order
(``docs/audit-history/25Sep2026-s14-s15-rider-work-orders.md``):

1. The single enforcement source carries exactly the ADR-derived values
   (cycle budget 1.0 s; producer warning 80 ms = the TA stage budget).
2. EVERY producer/cycle enforcement surface in ``orchestrator.py`` and
   the compliance counter in ``metrics.py`` derives from the module --
   read via AST, never string-grepping the source. A re-appearing
   hardcoded budget literal reds this net.
3. The derivation is RED-proven in-process: a mutated pin must
   propagate to both consumers through the import machinery.
"""

from __future__ import annotations

import ast
import importlib.util
import sys
from pathlib import Path
from types import ModuleType

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "src" / "loats"

EXPECTED_CYCLE_TARGET = 1.0
EXPECTED_PRODUCER_WARNING = 0.080

# The S-14 census at the 30Sep wave: five producer finally-blocks (all
# in orchestrator.py) plus the per-cycle warning and the metrics
# compliance counter. get_cycle_stats is pinned separately via a live
# call (it must report "pass" under the 1 s budget).
EXPECTED_PRODUCER_SURFACES = 5

PRODUCER_FUNCTIONS = {
    "_execute_ta_analysis",
    "_execute_sentiment_analysis",
    "_execute_volatility_analysis",
    "_execute_price_action_analysis",
    "_execute_options_flow_analysis",
}


def _load_source_module(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class TestSingleSourceValues:
    def test_cycle_target_is_the_amended_budget(self) -> None:
        from loats.latency_budget import CYCLE_COMPLIANCE_TARGET_SECONDS

        assert CYCLE_COMPLIANCE_TARGET_SECONDS == EXPECTED_CYCLE_TARGET

    def test_producer_warning_is_the_ta_stage_budget(self) -> None:
        from loats.latency_budget import PRODUCER_BUDGET_WARNING_SECONDS

        assert PRODUCER_BUDGET_WARNING_SECONDS == EXPECTED_PRODUCER_WARNING

    def test_no_hardcoded_budget_literals_reappear(self) -> None:
        # AST scan (no string-grepping): the legacy literals must not
        # reappear as COMPARE constants in the two enforcement modules
        # (strategy-math operands like `min(0.1 * x, ...)` are out of
        # scope -- only enforcement comparisons count). The collector's
        # stage budgets (TA 80 / DB 20 / round trip 100 ms) and the
        # strike 5 ms trail are out of scope too -- ADR-0021 leaves them
        # enforced where they are.
        banned = {
            "metrics.py": ("0.1",),
            "orchestrator.py": ("0.1", "0.03", "0.04"),
        }
        for filename, literals in banned.items():
            tree = ast.parse((SRC / filename).read_text(encoding="utf-8"))
            compares = [n for n in ast.walk(tree) if isinstance(n, ast.Compare)]
            values = set()
            for node in compares:
                for operand in [node.left, *node.comparators]:
                    if isinstance(operand, ast.Constant) and isinstance(
                        operand.value, float
                    ):
                        values.add(repr(operand.value))
            overlap = values.intersection(literals)
            assert not overlap, (
                f"{filename}: hardcoded budget literal(s) {sorted(overlap)} "
                "re-appeared in a comparison -- derive from "
                "loats.latency_budget (ADR-0021)"
            )


class TestDerivedSurfaces:
    def test_all_producer_surfaces_reference_the_pin(self) -> None:
        tree = ast.parse((SRC / "orchestrator.py").read_text(encoding="utf-8"))
        functions = {
            n.name
            for n in ast.walk(tree)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        assert PRODUCER_FUNCTIONS <= functions, PRODUCER_FUNCTIONS - functions
        uses = [
            n
            for n in ast.walk(tree)
            if isinstance(n, ast.Name) and n.id == "PRODUCER_BUDGET_WARNING_SECONDS"
        ]
        assert len(uses) == EXPECTED_PRODUCER_SURFACES, len(uses)

    def test_cycle_compliance_counter_references_the_pin(self) -> None:
        metrics_tree = ast.parse((SRC / "metrics.py").read_text(encoding="utf-8"))
        record = [
            n
            for n in ast.walk(metrics_tree)
            if isinstance(n, ast.FunctionDef) and n.name == "record_cycle_time"
        ]
        assert len(record) == 1
        names = {n.id for n in ast.walk(record[0]) if isinstance(n, ast.Name)}
        assert "CYCLE_COMPLIANCE_TARGET_SECONDS" in names

    def test_cycle_warning_derives_from_the_pin(self) -> None:
        tree = ast.parse((SRC / "orchestrator.py").read_text(encoding="utf-8"))
        record = [
            n
            for n in ast.walk(tree)
            if isinstance(n, ast.FunctionDef) and n.name == "_record_cycle_time"
        ]
        assert len(record) == 1
        names = {n.id for n in ast.walk(record[0]) if isinstance(n, ast.Name)}
        assert "CYCLE_COMPLIANCE_TARGET_SECONDS" in names

    def test_get_cycle_stats_grades_against_the_pin(self) -> None:
        # Live call: a fresh orchestrator averages 0 s -> compliant.
        from loats.latency_budget import CYCLE_COMPLIANCE_TARGET_SECONDS
        from loats.orchestrator import TradingOrchestrator

        orchestrator = TradingOrchestrator()
        stats = orchestrator.get_cycle_stats()
        assert stats["target_compliance"] == "pass"
        assert CYCLE_COMPLIANCE_TARGET_SECONDS >= 0

    def test_derivation_is_real_mutated_pin_propagates(self) -> None:
        # RED-proof of the derivation chain: mutate the pin module, then
        # re-execute BOTH consumers through the import machinery — each
        # must observe the mutated value (import, not a copied literal).
        # SINGLETON HYGIENE: the consumers carry module-level singletons
        # (metrics, db, orchestrator state) that other tests share, so
        # the original module objects are snapshotted and RESTORED in
        # the same order — sys.modules never loses the live entries.
        names = ("loats.orchestrator", "loats.metrics", "loats.latency_budget")
        saved = {name: sys.modules.get(name) for name in names}
        try:
            pin = _load_source_module("loats.latency_budget", SRC / "latency_budget.py")
            assert pin.CYCLE_COMPLIANCE_TARGET_SECONDS == 1.0
            pin.CYCLE_COMPLIANCE_TARGET_SECONDS = 2.0
            metrics = _load_source_module("loats.metrics", SRC / "metrics.py")
            assert metrics.CYCLE_COMPLIANCE_TARGET_SECONDS == 2.0, (
                "metrics.py does not import the pin — it holds a copy"
            )
            orch = _load_source_module("loats.orchestrator", SRC / "orchestrator.py")
            assert orch.CYCLE_COMPLIANCE_TARGET_SECONDS == 2.0, (
                "orchestrator.py does not import the pin — it holds a copy"
            )
        finally:
            for name, module in saved.items():
                if module is not None:
                    sys.modules[name] = module
                else:
                    sys.modules.pop(name, None)
