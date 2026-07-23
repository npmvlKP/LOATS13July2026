"""Configuration package for LOATS13July2026."""

from __future__ import annotations

from ._settings import Settings, get_settings

__all__ = ["Settings", "get_settings", "settings"]


# Lazy-loaded ``settings`` accessor for the ``loats.config`` package.
#
# ``Settings()`` is **not** instantiated at module import. It is deferred to
# first access through a module-level ``__getattr__``, so the
# ``@lru_cache(maxsize=1)`` declared in ``_settings.get_settings`` actually
# governs when the first (and only) ``Settings`` instance is constructed.
#
# Why lazy?
#   * Avoids import-time validation failures on fresh checkouts (e.g. the
#     mandatory ``OPENALGO_API_KEY`` validator would otherwise run before the
#     operator had a chance to export their secret).
#   * Avoids eagerly initialising ``Path`` objects, log directories, or any
#     other field that probes the filesystem before the application is ready.
#   * Keeps ``from loats.config import settings`` working without forcing
#     eager ``Settings()`` construction (Python's import machinery invokes
#     this very ``__getattr__`` to resolve the binding).
#
# The class ``Settings`` and the function ``get_settings`` remain eagerly
# available on the package — only the resolved instance is lazy. This mirrors
# the lazy-accessor pattern already in use at the top-level ``loats``
# package (``src/loats/__init__.py``).
_LAZY_SENTINEL = object()


def __getattr__(name: str) -> object:
    """Resolve ``settings`` lazily on first access."""
    if name == "settings":
        # Delegate to ``get_settings`` so the ``lru_cache`` ensures a single,
        # shared ``Settings`` instance across the process.
        return get_settings()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    """Expose ``settings`` to IDEs/introspection alongside ``__all__``."""
    return sorted({*globals().keys(), *__all__})
