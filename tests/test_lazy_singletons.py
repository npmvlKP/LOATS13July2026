"""Tests for lazy module-level singletons (F8-C-03).

Background: ``db`` / ``async_client`` / ``sentiment`` /
``trade_decision_engine`` / ``sizing_engine`` previously ran
``get_settings()`` at import time, crashing ``import loats.*`` (and
``python -m loats.main --help``) on fresh checkouts without
OPENALGO_API_KEY. The LazyProxy defers construction to first
attribute access while keeping runtime fail-closed.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from loats.utils.lazy_singleton import LazyProxy

REPO_ROOT = Path(__file__).resolve().parent.parent


class Widget:
    """Cheap stand-in for a settings-dependent singleton."""

    calls: int = 0

    def __init__(self) -> None:
        type(self).calls += 1
        self.name = "widget"


@pytest.fixture(autouse=True)
def _reset_calls() -> None:
    Widget.calls = 0


class TestLazyProxy:
    def test_factory_not_called_at_construction(self) -> None:
        LazyProxy(Widget)
        assert Widget.calls == 0

    def test_deferred_construction_on_first_access(self) -> None:
        proxy = LazyProxy(Widget)
        assert proxy.name == "widget"
        assert Widget.calls == 1

    def test_memoized_single_instance(self) -> None:
        proxy = LazyProxy(Widget)
        assert proxy.name == "widget"
        assert proxy.name == "widget"
        assert Widget.calls == 1

    def test_patched_attribute_shadows_proxy(self) -> None:
        # Simulates unittest.mock.patch on a module-level singleton:
        # the patched attribute lands in the proxy __dict__ and normal
        # lookup finds it before __getattr__ fires.
        proxy: LazyProxy[Widget] = LazyProxy(Widget)
        proxy.__dict__["name"] = "patched"
        assert proxy.name == "patched"
        assert Widget.calls == 0  # factory never ran

    def test_lazy_singleton_returns_delegate(self) -> None:
        from loats.utils.lazy_singleton import lazy_singleton

        w = lazy_singleton(Widget)
        assert w.name == "widget"
        assert Widget.calls == 1


class TestImportTimeSafety:
    def test_singletons_are_lazy_proxies(self) -> None:
        import loats.database as database
        import loats.openalgo as openalgo
        import loats.sizing as sizing
        import loats.trade_decision as trade_decision

        assert type(database.db).__name__ == "LazyProxy"
        assert type(openalgo.async_client).__name__ == "LazyProxy"
        assert type(sizing.sizing_engine).__name__ == "LazyProxy"
        assert type(trade_decision.trade_decision_engine).__name__ == "LazyProxy"

    def test_boot_help_without_credentials(self) -> None:
        """CI fresh-clone boot contract: --help works with no secrets.

        Runs ``python -m loats.main --help`` in a subprocess with
        OPENALGO_API_KEY removed from the environment.
        """
        import os

        env = {
            k: v
            for k, v in os.environ.items()
            if k != "OPENALGO_API_KEY" and not k.startswith("PYTHON")
        }
        env["PYTHONIOENCODING"] = "utf-8"
        proc = subprocess.run(
            [sys.executable, "-m", "loats.main", "--help"],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
            env=env,
            timeout=120,
        )
        assert proc.returncode == 0, proc.stderr[-2000:]
        assert "usage" in proc.stdout.lower()

    def test_runtime_still_fail_closed(self) -> None:
        """Fail-closed preserved: real settings use without key raises.

        Runs in a temp cwd so the repo's untracked ``.env`` (present on
        dev machines) cannot satisfy the required key; only the cleaned
        subprocess environment is visible.
        """
        import os
        import tempfile

        code = (
            "from loats.config import get_settings; "
            "get_settings.cache_clear(); get_settings()"
        )
        with tempfile.TemporaryDirectory() as tmp:
            env = {
                k: v
                for k, v in os.environ.items()
                if k != "OPENALGO_API_KEY" and not k.startswith("PYTHON")
            }
            env["PYTHONIOENCODING"] = "utf-8"
            proc = subprocess.run(
                [sys.executable, "-c", code],
                capture_output=True,
                text=True,
                cwd=tmp,
                env=env,
                timeout=120,
            )
        assert proc.returncode != 0
        assert "openalgo_api_key" in proc.stderr
