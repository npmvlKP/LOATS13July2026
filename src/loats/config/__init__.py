"""Configuration package for LOATS13July2026."""

from __future__ import annotations

from .settings import Settings, get_settings

# ``settings`` is deliberately NOT re-exported from this package.
#
# ``loats.config.settings`` is a real submodule. Importing it binds the
# *module object* as an attribute of this package, and Python only consults a
# module-level ``__getattr__`` when normal attribute lookup fails. A lazy
# ``settings`` accessor defined here is therefore permanently shadowed:
# ``from loats.config import settings`` yields the module, not a ``Settings``
# instance, while a ``TYPE_CHECKING`` declaration would make mypy believe the
# opposite - a silent type/runtime divergence.
#
# Use one of the following instead:
#   * ``from loats.config import get_settings`` - the lru_cached accessor
#     used throughout ``src/loats`` (lazy, single shared instance).
#   * ``from loats import settings`` - the top-level lazy accessor, which is
#     not shadowed because there is no ``loats/settings.py`` submodule.
__all__ = ["Settings", "get_settings"]
