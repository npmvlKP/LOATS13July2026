"""Regression tests for the ``loats.config`` package export surface.

``loats.config.settings`` is a real submodule, so a module-level PEP 562
``__getattr__`` that tries to expose a lazy ``settings`` *instance* on the
package is permanently shadowed by the submodule binding. These tests lock in
the documented contract: the package exports ``Settings`` and ``get_settings``
only, and the lazy instance accessor lives on the top-level ``loats`` package.
"""

from __future__ import annotations

import types

import loats as loats_pkg
import loats.config as config_pkg
from loats.config.settings import Settings


def test_config_package_exports_only_class_and_accessor() -> None:
    """The package advertises the factory, never a shadowed instance."""
    assert config_pkg.__all__ == ["Settings", "get_settings"]
    assert "settings" not in config_pkg.__all__


def test_config_settings_attribute_is_the_submodule() -> None:
    """``config.settings`` resolves to the module, matching runtime reality."""
    assert isinstance(config_pkg.settings, types.ModuleType)
    assert config_pkg.settings.__name__ == "src.loats.config.settings"


def test_get_settings_returns_cached_settings_instance() -> None:
    """``get_settings`` is the supported accessor and is lru_cached."""
    first = config_pkg.get_settings()
    second = config_pkg.get_settings()

    assert isinstance(first, Settings)
    assert first is second


def test_top_level_settings_accessor_is_not_shadowed() -> None:
    """``loats.settings`` stays a live Settings instance (no submodule clash)."""
    settings = loats_pkg.settings

    assert isinstance(settings, Settings)
    assert settings is config_pkg.get_settings()
