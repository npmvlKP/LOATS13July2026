"""Regression tests for HC-03 empty-package-shell scan (verify_hc_all.py).

Root cause covered: a stray tool cache (``src/loats/.mypy_cache``) — an
untracked, git-ignored directory with no ``*.py``/``*.pyi`` files — was
counted as an "empty package shell", tripping HC-03 and cascading 13
blanket FAILs through the HC registry delegation. The scan must skip
dot-prefixed tooling exhaust just like ``__pycache__``.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
VERIFY_PATH = REPO_ROOT / "scripts" / "verify_hc_all.py"


def _load_verify_hc_all():
    spec = importlib.util.spec_from_file_location("verify_hc_all", VERIFY_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestHc03ToolCacheExhaust:
    def test_mypy_cache_not_an_empty_shell(self, tmp_path, monkeypatch, capsys):
        module = _load_verify_hc_all()
        loats = tmp_path / "src" / "loats"
        (loats / "utils").mkdir(parents=True)
        (loats / "utils" / "__init__.py").write_text("", encoding="utf-8")
        (loats / ".mypy_cache" / "3.12").mkdir(parents=True)
        (loats / ".mypy_cache" / "3.12" / "abc.meta.json").write_text(
            "{}", encoding="utf-8"
        )
        monkeypatch.setattr(module, "REPO_ROOT", tmp_path)
        assert module.check_hc03() is True
        out = capsys.readouterr().out
        assert "count=0" in out

    def test_pycache_still_skipped(self, tmp_path, monkeypatch):
        module = _load_verify_hc_all()
        loats = tmp_path / "src" / "loats"
        (loats / "real_pkg").mkdir(parents=True)
        (loats / "real_pkg" / "mod.py").write_text("x = 1\n", encoding="utf-8")
        (loats / "__pycache__").mkdir()
        (loats / "__pycache__" / "mod.cpython-312.pyc").write_bytes(b"\x00")
        monkeypatch.setattr(module, "REPO_ROOT", tmp_path)
        assert module.check_hc03() is True

    def test_genuine_empty_shell_still_flagged(self, tmp_path, monkeypatch):
        module = _load_verify_hc_all()
        loats = tmp_path / "src" / "loats"
        (loats / "ghost_pkg").mkdir(parents=True)  # no .py/.pyi inside
        monkeypatch.setattr(module, "REPO_ROOT", tmp_path)
        assert module.check_hc03() is False

    def test_live_repo_scan_passes(self, capsys):
        module = _load_verify_hc_all()
        assert module.check_hc03() is True
        assert "count=0" in capsys.readouterr().out
