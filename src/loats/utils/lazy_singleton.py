"""Lazy singleton proxy (F8-C-03, 2026-09-02).

``LazyProxy`` defers constructing a module-level singleton until its
first attribute access. It generalizes the ``LazySettings`` pattern
(TODO-18 / HC-21) from settings to any import-expensive or
settings-dependent object.

Why
---
Several module-level singletons (``db``, ``async_client``,
``sentiment``, ``trade_decision_engine``, ``sizing_engine``) run
``get_settings()`` inside ``__init__``. Settings is deliberately
fail-closed (``openalgo_api_key`` has no default), which is correct at
runtime but crashes ``import loats.*`` — and therefore
``python -m loats.main --help`` — on any fresh checkout without
credentials. The CI fresh-clone boot test requires imports to be
credential-free while runtime stays fail-closed; deferring
construction reconciles both.

Semantics
---------
* Import cost: one small object; the factory does not run.
* First attribute access builds the instance once under a lock
  (thread-safe) and memoizes it; every access then delegates.
* ``patch("loats.<mod>.<singleton>.<attr>")`` keeps working in tests:
  patched attributes land in the proxy's ``__dict__``, which normal
  attribute lookup consults before ``__getattr__`` fires.
* Type checkers see the target type via ``cast`` at the binding site.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any, cast


class LazyProxy[T]:
    """Deferred-construction proxy around a zero-argument factory.

    Note: deliberately NOT ``__slots__``-annotated — the instance
    ``__dict__`` is what lets ``unittest.mock.patch`` setattr patched
    attributes onto the proxy (found by test_patched_attribute_shadows_proxy).
    """

    def __init__(self, factory: Callable[[], T]) -> None:
        self._factory = factory
        # When the factory is a plain class (all current call sites),
        # isinstance() can answer before construction — matching the
        # stdlib Mock __class__ protocol.
        self._target_type: type[Any] | None = (
            factory if isinstance(factory, type) else None
        )
        self._instance: T | None = None
        self._lock = threading.Lock()

    @property  # type: ignore[misc]
    def __class__(self) -> type[Any]:
        # Make isinstance(proxy, TargetClass) true at any time: tests
        # assert isinstance on module singletons (test_enums_and_singleton).
        if self._target_type is not None:
            return self._target_type
        with self._lock:
            return type(self._instance) if self._instance is not None else LazyProxy

    def __getattr__(self, name: str) -> Any:
        # Only reached for attributes absent from __dict__.
        with self._lock:
            if self._instance is None:
                self._instance = self._factory()
        return getattr(self._instance, name)


def lazy_singleton[T](factory: Callable[[], T]) -> T:
    """Return a ``LazyProxy`` typed as ``T`` for a module-level binding.

    Usage::

        db: Database = lazy_singleton(Database)
    """
    return cast(T, LazyProxy(factory))


__all__ = ["LazyProxy", "lazy_singleton"]
