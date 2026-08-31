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
    """

    __slots__ = ()

    def __getattr__(self, name: str) -> Any:
        settings = get_settings()
        return getattr(settings, name)


__all__ = ["LazySettings"]
