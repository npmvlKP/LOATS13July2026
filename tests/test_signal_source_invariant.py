"""Signal source-tagging invariant (F8-H-03).

Every ``Signal(...)`` constructor call in ``src/loats/`` must pass a
``metadata`` dict that contains a ``source`` key whose value resolves via
``strength.resolve_source`` to a canonical ``StrengthSource`` enum member.

The database row-hydration sites in ``database.py`` and
``database_async_additions.py`` are exempt: they reconstruct a model from a
stored row and do not create a new signal.  The ``performance_analyzer.py``
latency probes are also exempt because they create test-only fixtures that are
not persisted and do not participate in the CMP chain.
"""

import ast
import pathlib

from loats.strength import StrengthSource, resolve_source

SRC_ROOT = pathlib.Path(__file__).resolve().parents[2] / "src" / "loats"

EXEMPT_FILES = {
    "database.py",
    "database_async_additions.py",
    "performance_analyzer.py",
    "lazy_singleton.py",
}


def _is_signal_call(node: ast.AST) -> bool:
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if isinstance(func, ast.Name) and func.id == "Signal":
        return True
    if isinstance(func, ast.Attribute) and func.attr == "Signal":
        return True
    return False


def _get_keyword(node: ast.Call, name: str) -> ast.keyword | None:
    for kw in node.keywords:
        if kw.arg == name:
            return kw
    return None


def _is_string_literal(node: ast.AST | None) -> bool:
    return isinstance(node, ast.Constant) and isinstance(node.value, str)


def _extract_string_literal(node: ast.AST | None) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _extract_strengthsource_value(node: ast.AST | None) -> str | None:
    """Resolve ``StrengthSource.X.value`` to the enum member's value."""
    from loats.strength import StrengthSource

    if (
        isinstance(node, ast.Attribute)
        and node.attr == "value"
        and isinstance(node.value, ast.Attribute)
        and isinstance(node.value.value, ast.Name)
        and node.value.value.id == "StrengthSource"
    ):
        member = node.value.attr
        try:
            return StrengthSource[member].value
        except KeyError:
            return None
    return None


def _metadata_has_source(node: ast.Call) -> tuple[bool, str | None]:
    """Return (has_source_key, source_value_or_none) for a Signal call."""
    metadata_kw = _get_keyword(node, "metadata")
    if metadata_kw is None or not isinstance(metadata_kw.value, ast.Dict):
        return False, None
    d = metadata_kw.value
    for key, value in zip(d.keys, d.values, strict=False):
        if _is_string_literal(key) and _extract_string_literal(key) == "source":
            return True, _extract_string_literal(
                value
            ) or _extract_strengthsource_value(value)
    return False, None


def _find_signal_construction_sites() -> list[tuple[str, int, bool, str | None]]:
    sites: list[tuple[str, int, bool, str | None]] = []
    for py in SRC_ROOT.rglob("*.py"):
        if py.name in EXEMPT_FILES or "__pycache__" in py.parts:
            continue
        try:
            tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if _is_signal_call(node):
                assert isinstance(node, ast.Call)
                has_source, source_value = _metadata_has_source(node)
                sites.append(
                    (
                        str(py.relative_to(SRC_ROOT.parent.parent)),
                        node.lineno,
                        has_source,
                        source_value,
                    )
                )
    return sites


class TestSignalSourceInvariant:
    """AST-level invariant: every Signal constructor in src/ carries a source tag."""

    def test_every_signal_construction_has_source_key(self) -> None:
        sites = _find_signal_construction_sites()
        offenders = [s for s in sites if not s[2]]
        assert not offenders, (
            "Signal constructors without metadata.source:\n"
            + "\n".join(f"  {path}:{line}" for path, line, _, _ in offenders)
        )

    def test_every_signal_source_is_enum_valid(self) -> None:
        sites = _find_signal_construction_sites()
        offenders: list[tuple[str, int, str | None]] = []
        for path, line, has_source, source_value in sites:
            if not has_source or source_value is None:
                offenders.append((path, line, source_value))
                continue
            try:
                resolve_source(source_value)
            except ValueError:
                offenders.append((path, line, source_value))
        assert not offenders, (
            "Signal constructors with non-canonical source values:\n"
            + "\n".join(
                f"  {path}:{line} source={value!r}" for path, line, value in offenders
            )
        )

    def test_resolve_source_accepts_all_orchestrator_sources(self) -> None:
        for src in ("ta", "sentiment", "price_action", "volatility"):
            assert resolve_source(src) in StrengthSource
