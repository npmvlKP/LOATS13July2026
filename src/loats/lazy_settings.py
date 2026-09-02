"""Lazy settings proxy (TODO-18 / HC-21).

``LazySettings`` defers constructing the cached ``Settings`` instance
until first attribute access. Importing this module does NOT trigger
``Settings()`` — so a fresh checkout with no API keys can still
``import loats.*`` without raising.

Rationale
---------
* HC-21 forbids ``settings = get_settings()`` at module top-level
  (eager), yet every CMP module needs a ``settings`` reference inside
  class bodies.
* PEP 562 ``__getattr__`` was tried first but only fires for explicit
  module attribute access (``module.settings``); class bodies fall
  through the bytecode LOAD_GLOBAL fast path without triggering it.

Implementation
--------------
* The proxy is a class with a single ``__getattr__``.
* Each attribute access invokes the lru_cache-backed
  ``get_settings()`` and proxies through ``getattr``.
* Therefore cost at import time == single class instantiation, and
  cost at first use == single ``Settings()`` build (cached forever).
"""

from __future__ import annotations

from typing import Any

from .config import get_settings


class LazySettings:
    """Lazy proxy for module-level ``settings``.

    Constructed exactly once per importing module via
    ``settings: LazySettings = LazySettings()``. Every attribute access
    invokes ``get_settings()`` which returns the cached ``Settings``
    instance after the first build.

    Implemented as a patchable proxy: ``patch("module.settings.X", value)``
    stores the override in the proxy instance and shadows the underlying
    frozen ``Settings`` attribute. This preserves the no-eager-build
    guarantee while giving tests a reliable seam.
    """

    __slots__ = ("_overrides", "_target")

    def __init__(self, target: Any | None = None) -> None:
        super().__setattr__("_target", target)
        super().__setattr__("_overrides", {})

    def __getattr__(self, name: str) -> Any:
        overrides = super().__getattribute__("_overrides")
        if name in overrides:
            return overrides[name]
        settings = super().__getattribute__("_target")
        if settings is None:
            settings = get_settings()
        return getattr(settings, name)

    def __setattr__(self, name: str, value: Any) -> None:
        # Allow instance attribute assignment (for __slots__) and support
        # patch() setting attributes on the proxy itself as a test seam.
        if name in ("_target", "_overrides"):
            super().__setattr__(name, value)
            return
        super().__getattribute__("_overrides")[name] = value


__all__ = ["LazySettings"]
