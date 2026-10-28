"""Isolation net for the wall-clock cache benchmarks (28Oct wave).

ADR-0016's sanctioned lever #2 (suite-context isolation, operator-gated
ON 2026-10-28) landed as a three-part contract:

1. The two wall-clock cache benchmark stages carry the
   ``benchmark_wallclock`` marker, registered in pyproject.toml.
2. The local pre-push pytest leg deselects the marker: coverage tracing
   alone compresses the shared trading host below the thresholds (07Oct
   isolation ladder, re-proven 28Oct: 1,586 writes/s traced vs the
   2,000 writes/s threshold; both stages green untraced in the same
   minute).
3. CI grades them anyway: the advisory ``benchmark-wallclock`` job runs
   the marked pair on an isolated runner with NO tracing, and the
   REQUIRED ``pytest-coverage`` job keeps running the FULL suite
   (marker included) -- server-side enforcement of the complete set is
   unchanged.

Every leg is pinned here; narrowing any leg flips this net red. A live
selection leg proves the marker currently selects EXACTLY the two cache
stages and nothing else.
"""

from __future__ import annotations

import re
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = REPO_ROOT / "pyproject.toml"
PRECOMMIT_YML = REPO_ROOT / ".pre-commit-config.yaml"
CI_YML = REPO_ROOT / ".github" / "workflows" / "ci.yml"
BENCH_FILE = REPO_ROOT / "tests" / "test_performance_benchmarks.py"
CONTRIBUTING = REPO_ROOT / "CONTRIBUTING.md"

MARKED_STAGES = (
    ("tests/test_performance_benchmarks.py::TestCachePerformance::test_cache_latency"),
    (
        "tests/test_performance_benchmarks.py::TestConcurrentPerformance::"
        "test_concurrent_cache_operations"
    ),
)


def _ci_job_block(text: str, job: str) -> str | None:
    match = re.search(rf"^  {job}:\n(?:^ {{4,}}.*\n?)*", text, re.M)
    return match.group(0) if match else None


def _precommit_hook_block(text: str, hook_id: str) -> str | None:
    match = re.search(rf"^      - id: {hook_id}\n(?:^ {{8,}}.*\n?)*", text, re.M)
    return match.group(0) if match else None


def _assert_prepush_deselect(block: str) -> None:
    assert "--cov" in block, "pre-push pytest leg lost its coverage scope"
    assert "--cov-fail-under=80" in block, "pre-push coverage floor was narrowed"
    args_match = re.search(r"args: \[(.*)\]", block)
    assert args_match is not None, f"pytest hook carries no args list: {block!r}"
    args = [a.strip() for a in args_match.group(1).split(",")]
    assert "-m" in args, (
        "pre-push pytest leg stopped deselecting the wall-clock marker "
        "(-m is gone); the traced local run deterministically fails the "
        "2,000 writes/s stage on the shared trading host"
    )
    assert '"not benchmark_wallclock"' in args_match.group(1), (
        'the deselect expression must be exactly "not benchmark_wallclock"'
    )


def _assert_wallclock_job(block: str) -> None:
    assert "name: benchmark-wallclock" in block, block[:300]
    assert "pytest tests/ -m benchmark_wallclock" in block, (
        "benchmark-wallclock job lost the marker selection; it would grade nothing"
    )
    assert "--cov" not in block, (
        "benchmark-wallclock must grade the pair WITHOUT coverage "
        "tracing - tracing is the depressant the job exists to isolate "
        "from"
    )
    assert "continue-on-error" not in block, (
        "benchmark-wallclock must gate on pytest's exit code"
    )
    assert 'pip install -e ".[dev]"' in block, (
        "benchmark-wallclock must install the project (the marked stages "
        "import loats and need the dev extra's pytest-asyncio)"
    )


class TestMarkerContract:
    def test_marker_is_registered_in_pyproject(self) -> None:
        data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
        markers = data["tool"]["pytest"]["ini_options"]["markers"]
        registered = [m for m in markers if m.startswith("benchmark_wallclock")]
        assert len(registered) == 1, registered
        assert "ADR-0016 lever #2" in registered[0], registered[0]

    def test_source_marks_exactly_the_two_cache_stages(self) -> None:
        source = BENCH_FILE.read_text(encoding="utf-8")
        assert source.count("@pytest.mark.benchmark_wallclock") == 2, (
            "the marked set drifted from the two wall-clock cache stages; "
            "every added marking changes the local pre-push scope and the "
            "CI benchmark-wallclock selection"
        )
        for fn in ("test_cache_latency", "test_concurrent_cache_operations"):
            pattern = rf"(@pytest\.mark\.\w+\n\s+)+async def {fn}\("
            match = re.search(pattern, source)
            assert match is not None, f"{fn} lost its pytest.mark decorators"
            assert "benchmark_wallclock" in match.group(0), (
                f"{fn} is no longer marked benchmark_wallclock"
            )

    def test_marker_selects_exactly_the_two_stages_live(self) -> None:
        # LIVE selection proof: a no-cov collection run under
        # -m benchmark_wallclock must yield exactly the two cache stages
        # (no drive-by marking, no stale marker on another test). Plain
        # pytest --collect-only requests no coverage lock, so this leg is
        # safe under the parent suite's own --cov run. ``-o addopts=``
        # strips the repo's ``-v`` addopts so the output is plain node-id
        # lines regardless of future addopts changes.
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "tests/",
                "-m",
                "benchmark_wallclock",
                "--collect-only",
                "-q",
                "-o",
                "addopts=",
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=300,
            check=False,
        )
        assert proc.returncode == 0, (
            f"collection failed rc={proc.returncode}\n"
            f"{proc.stdout[-2000:]}\n{proc.stderr[-2000:]}"
        )
        collected = sorted(
            line.replace("\\", "/").strip()
            for line in proc.stdout.splitlines()
            if line.strip().replace("\\", "/").startswith("tests/") and "::" in line
        )
        assert collected == sorted(MARKED_STAGES), collected


class TestLocalGateContract:
    def test_prepush_pytest_leg_deselects_the_marker(self) -> None:
        text = PRECOMMIT_YML.read_text(encoding="utf-8")
        block = _precommit_hook_block(text, "pytest")
        assert block is not None, "pre-commit config lost the pytest hook"
        _assert_prepush_deselect(block)

    def test_net_flags_a_hook_that_stopped_deselecting(self) -> None:
        text = PRECOMMIT_YML.read_text(encoding="utf-8")
        block = _precommit_hook_block(text, "pytest")
        assert block is not None
        mutated = block.replace(', -m, "not benchmark_wallclock"]', "]")
        assert mutated != block, "mutation did not apply"
        with pytest.raises(AssertionError, match="stopped deselecting"):
            _assert_prepush_deselect(mutated)


class TestCIContract:
    def test_dedicated_job_runs_the_marker_untraced(self) -> None:
        text = CI_YML.read_text(encoding="utf-8")
        block = _ci_job_block(text, "benchmark-wallclock")
        assert block is not None, (
            "ci.yml lost the benchmark-wallclock job; the local pre-push "
            "deselect is only honest while CI grades the marked pair "
            "(ADR-0016 lever #2) -- restore the job or re-open the wave"
        )
        _assert_wallclock_job(block)

    def test_net_flags_a_job_that_swallowed_the_exit_code(self) -> None:
        text = CI_YML.read_text(encoding="utf-8")
        block = _ci_job_block(text, "benchmark-wallclock")
        assert block is not None
        mutated = block.replace(
            "    runs-on: ubuntu-latest",
            "    runs-on: ubuntu-latest\n    continue-on-error: true",
        )
        with pytest.raises(AssertionError, match="exit code"):
            _assert_wallclock_job(mutated)

    def test_net_flags_a_job_that_started_tracing(self) -> None:
        text = CI_YML.read_text(encoding="utf-8")
        block = _ci_job_block(text, "benchmark-wallclock")
        assert block is not None
        mutated = block.replace(
            "            --junitxml=pytest-benchmark-report.xml",
            "            --cov=src --junitxml=pytest-benchmark-report.xml",
        )
        with pytest.raises(AssertionError, match="WITHOUT coverage"):
            _assert_wallclock_job(mutated)

    def test_required_coverage_job_keeps_the_full_suite(self) -> None:
        # The no-downgrade pin: the local pre-push may deselect the
        # marker ONLY while the REQUIRED pytest-coverage context keeps
        # grading it server-side. Excluding it there too would leave the
        # class enforced solely by the advisory job - a silent
        # enforcement downgrade of the F9-H-02 posture.
        text = CI_YML.read_text(encoding="utf-8")
        block = _ci_job_block(text, "pytest-coverage")
        assert block is not None, "ci.yml lost the pytest-coverage job"
        assert "pytest tests/" in block, "pytest-coverage no longer runs the test suite"
        assert "not benchmark_wallclock" not in block, (
            "pytest-coverage (REQUIRED context) must keep running the "
            "wall-clock benchmarks server-side"
        )

    def test_net_flags_a_required_job_that_deselected_the_marker(self) -> None:
        text = CI_YML.read_text(encoding="utf-8")
        block = _ci_job_block(text, "pytest-coverage")
        assert block is not None
        mutated = block.replace(
            "          pytest tests/ \\",
            '          pytest tests/ -m "not benchmark_wallclock" \\',
        )
        with pytest.raises(AssertionError, match="server-side"):
            self._assert_full_suite(mutated)

    @staticmethod
    def _assert_full_suite(block: str) -> None:
        assert "pytest tests/" in block
        assert "not benchmark_wallclock" not in block, (
            "pytest-coverage (REQUIRED context) must keep running the "
            "wall-clock benchmarks server-side"
        )


def test_contributing_documents_the_isolation() -> None:
    doc = CONTRIBUTING.read_text(encoding="utf-8")
    assert "benchmark-wallclock" in doc, (
        "CONTRIBUTING no longer documents the advisory job; the "
        "advisory/required split is the load-bearing contract"
    )
    assert "keeps running the full suite including the marker" in doc, (
        "CONTRIBUTING lost the no-downgrade clause"
    )
