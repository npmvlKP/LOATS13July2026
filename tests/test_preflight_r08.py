"""R-08 duplicate-listener pre-flight pins (2026-09-30 ops window).

Pins the bind-or-exit guard decided for R-08
(``docs/audit-history/24Sep2026-degraded-duplicate-recurrence.md``):
a live LOATS identity on the configured OpenAlgo endpoint refuses the
boot BEFORE any resource initialization; a foreign listener, a dead
endpoint, or a timeout is clear; the probe is skipped under
``ENVIRONMENT=test``. The transport is faked -- the suite never probes
a real network.
"""

from __future__ import annotations

import urllib.error
from contextlib import contextmanager
from types import SimpleNamespace
from typing import Any

import pytest

from loats import preflight
from loats.preflight import DuplicateListenerError, check_duplicate_listener


class _FakeResponse:
    def __init__(self, body: bytes) -> None:
        self._body = body

    def read(self, amount: int) -> bytes:
        return self._body[:amount]

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *exc: object) -> None:
        return None


def _install_transport(
    monkeypatch: pytest.MonkeyPatch,
    handler: Any,
) -> list[str]:
    """Swap the module's urllib package for a fake; return probed URLs."""
    probed: list[str] = []

    def urlopen(url: str, timeout: float) -> Any:
        probed.append(url)
        return handler(url, timeout)

    fake_urllib = SimpleNamespace(
        request=SimpleNamespace(urlopen=urlopen), error=urllib.error
    )
    monkeypatch.setattr(preflight, "urllib", fake_urllib)
    return probed


@pytest.fixture(autouse=True)
def _production_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    # conftest pins ENVIRONMENT=test suite-wide; the probe's skip branch
    # would hide every assertion below. These tests exercise the probe
    # itself, so lift the pin for the duration of each test.
    monkeypatch.setenv("ENVIRONMENT", "production")


class TestProbeSemantics:
    def test_live_loats_identity_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        body = (
            b'{"system_status": {"kill_switch_active": false}, '
            b'"cycle_time_stats": {"count": 42}}'
        )

        @contextmanager
        def handler(url: str, timeout: float) -> Any:
            yield _FakeResponse(body)

        _install_transport(monkeypatch, handler)
        with pytest.raises(DuplicateListenerError) as excinfo:
            check_duplicate_listener("http://127.0.0.1:5000")
        assert "R-08" in str(excinfo.value)
        assert "127.0.0.1:5000" in str(excinfo.value)

    def test_foreign_identity_is_clear(self, monkeypatch: pytest.MonkeyPatch) -> None:
        @contextmanager
        def handler(url: str, timeout: float) -> Any:
            yield _FakeResponse(b"<html>OpenAlgo gateway</html>")

        _install_transport(monkeypatch, handler)
        assert check_duplicate_listener("http://127.0.0.1:5000") is None

    def test_dead_endpoint_is_clear(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def handler(url: str, timeout: float) -> Any:
            raise urllib.error.URLError("Connection refused")

        _install_transport(monkeypatch, handler)
        assert check_duplicate_listener("http://127.0.0.1:5000") is None

    def test_timeout_is_clear(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def handler(url: str, timeout: float) -> Any:
            raise TimeoutError("timed out")

        _install_transport(monkeypatch, handler)
        assert check_duplicate_listener("http://127.0.0.1:5000") is None

    def test_probe_hits_metrics_path_with_trailing_slash_normalized(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        @contextmanager
        def handler(url: str, timeout: float) -> Any:
            yield _FakeResponse(b"{}")

        probed = _install_transport(monkeypatch, handler)
        check_duplicate_listener("http://127.0.0.1:5000/")
        assert probed == ["http://127.0.0.1:5000/metrics"]

    def test_test_environment_skips_the_network(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ENVIRONMENT", "test")
        probed = _install_transport(
            monkeypatch, lambda url, timeout: (_ for _ in ()).throw(AssertionError())
        )
        assert check_duplicate_listener("http://127.0.0.1:5000") is None
        assert probed == []


class TestWiring:
    async def test_initialize_refuses_before_any_resource_is_built(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # The guard is the FIRST initialize step: when it refuses,
        # nothing below it (cache, db, alerts, scheduler, metrics,
        # orchestrator) may have been touched.
        from loats import main as main_module

        calls: list[str] = []

        def refusing_guard(base_url: str) -> None:
            calls.append(f"guard:{base_url}")
            raise DuplicateListenerError("R-08: simulated duplicate")

        async def fail_if_called(name: str) -> None:
            raise AssertionError(f"{name} ran after the guard refused")

        monkeypatch.setattr("loats.preflight.check_duplicate_listener", refusing_guard)
        monkeypatch.setattr(
            main_module, "initialize_cache", lambda: fail_if_called("cache")
        )
        monkeypatch.setattr(
            main_module.db, "async_initialize", lambda: fail_if_called("db")
        )
        monkeypatch.setattr(
            main_module.metrics,
            "start_server",
            lambda port: (_ for _ in ()).throw(
                AssertionError("metrics ran after the guard refused")
            ),
        )

        system = main_module.TradingSystem()
        with pytest.raises(DuplicateListenerError):
            await system.initialize()
        assert calls and calls[0].startswith("guard:")
