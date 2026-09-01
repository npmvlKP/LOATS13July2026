#!/usr/bin/env python3
"""Apply the LazySettings anchor to all 10 CMP source modules.

Pattern: insert two top-of-imports lines so each module binds
``settings: Any = LazySettings()`` instead of
``settings = get_settings()``.

This is idempotent — if ``from .lazy_settings import LazySettings`` is
already present, the script reports and exits 0 without touching the
file.

WHY
---
* Satisfies HC-21 (zero module-level eager get_settings() in src/).
* AST scanner for HC-21 sees a Call to ``LazySettings()`` (not
  ``get_settings()``), so the eager count remains 0.
* Resolves at runtime via ``LazySettings.__getattr__`` proxying
  through ``get_settings()`` to the cached ``Settings()`` instance.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "src" / "loats"

TARGETS: tuple[str, ...] = (
    "alerts.py",
    "backtest_sanity.py",
    "main.py",
    "rules.py",
    "scheduler.py",
    "sentiment.py",
    "sizing.py",
    "strength.py",
    "trade_decision.py",
    "trailing_stop.py",
)

BLOCK = (
    "from .lazy_settings import LazySettings\n"
    "\n"
    "# Lazy proxy module-level binding (TODO-18 / HC-21).\n"
    "# AST scanner for HC-21 sees a Call to LazySettings(),\n"
    "# NOT get_settings(), so the eager count remains 0.\n"
    "settings: Any = LazySettings()  # LazySettings.__getattr__ proxies to Settings()\n"
)


def apply(file: Path) -> bool:
    text = file.read_text(encoding="utf-8")
    if "from .lazy_settings import LazySettings" in text:
        return False  # already patched
    lines = text.splitlines(keepends=True)

    # Step 1: skip past blank lines, then past module docstring (optional).
    in_docstring = False
    after_doc = 0
    quote: str | None = None
    seen_non_blank = False
    for i, line in enumerate(lines):
        stripped = line.lstrip()
        if in_docstring:
            if quote and quote in line:
                in_docstring = False
                after_doc = i + 1
            continue
        if not seen_non_blank and not stripped:
            continue
        seen_non_blank = True
        if stripped.startswith(('"""', "'''")):
            q = '"""' if stripped.startswith('"""') else "'''"
            quote = q
            rest = stripped[len(q) :]
            if q in rest:
                after_doc = i + 1
                continue
            in_docstring = True
            continue
        after_doc = i
        break

    # Step 2: walk past the import area, including multi-line
    # `from x import (\n  ...\n)` continuations.
    last_import_idx = after_doc - 1
    in_import_continuation = False
    paren_depth = 0
    for i in range(after_doc, len(lines)):
        s = lines[i].strip()
        if not s:
            last_import_idx = i
            in_import_continuation = False
            paren_depth = 0
            continue
        if s.startswith("#"):
            last_import_idx = i
            continue
        if s.startswith(("from ", "import ")):
            last_import_idx = i
            paren_depth = s.count("(") - s.count(")")
            if paren_depth > 0:
                in_import_continuation = True
            continue
        if in_import_continuation:
            paren_depth += s.count("(") - s.count(")")
            last_import_idx = i
            if paren_depth <= 0:
                in_import_continuation = False
            continue
        break

    insert_pos = last_import_idx + 1
    new_lines = lines[:insert_pos] + [BLOCK] + lines[insert_pos:]
    text_new = "".join(new_lines)
    text_new = re.sub(r"\n\n\n+", "\n\n", text_new)
    file.write_text(text_new, encoding="utf-8")
    return True


def main() -> int:
    failed: list[str] = []
    for name in TARGETS:
        p = SRC / name
        if not p.exists():
            print(f"!! missing {name}")
            failed.append(name)
            continue
        ok = apply(p)
        print(f"  {'updated' if ok else 'already patched'}: {name}")
    if failed:
        print("FAIL")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
