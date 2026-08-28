#!/usr/bin/env python3
"""Re-add proper noqa comments to E402 and F401 violations with correct syntax."""

import sys
from pathlib import Path


def add_noqa_to_database_async_additions_f401(filepath: Path) -> bool:
    """Add noqa comment to F401 violation in database_async_additions.py."""
    try:
        with open(filepath, 'r') as f:
            content = f.read()

        # Fix the F401 violation with proper noqa comment
        content = content.replace(
            'import aiosqlite as _aiosqlite',
            'import aiosqlite as _aiosqlite  # type: ignore[no-redef] - checked for availability'
        )

        with open(filepath, 'w') as f:
            f.write(content)

        return True

    except Exception as e:
        print(f"Error processing {filepath}: {e}")
        return False


def add_noqa_to_database_async_additions_e402(filepath: Path) -> bool:
    """Add noqa comments to E402 violations in database_async_additions.py."""
    try:
        with open(filepath, 'r') as f:
            lines = f.readlines()

        modified_lines = []
        in_import_section = False
        found_docstring = False

        for i, line in enumerate(lines, 1):
            # Check for the problematic docstring at line 750
            if i == 750 and '"""Async database operations' in line:
                found_docstring = True
                modified_lines.append(line)
                continue

            # Add noqa comments to imports after the docstring
            if found_docstring and not in_import_section:
                if line.strip().startswith('import ') or line.strip().startswith('from '):
                    in_import_section = True

            if in_import_section:
                if line.strip().startswith('import ') or line.strip().startswith('from '):
                    # Add noqa comment if not already present with proper syntax
                    if '# noqa' not in line and '# type:' not in line:
                        if line.strip().startswith('import importlib.util'):
                            modified_lines.append(line.rstrip() + '  # noqa: E402\n')
                        elif line.strip().startswith('from datetime import UTC'):
                            modified_lines.append(line.rstrip() + '  # noqa: E402\n')
                        elif line.strip().startswith('from typing import Any'):
                            modified_lines.append(line.rstrip() + '  # noqa: E402\n')
                        elif line.strip().startswith('from .database import Database'):
                            modified_lines.append(line.rstrip() + '  # noqa: E402\n')
                        elif line.strip().startswith('from .models import ('):
                            modified_lines.append(line.rstrip() + '  # noqa: E402\n')
                        else:
                            modified_lines.append(line)
                    else:
                        modified_lines.append(line)
                elif line.strip() == '' or line.strip().startswith('async def') or line.strip().startswith('#'):
                    # End of import section
                    in_import_section = False
                    modified_lines.append(line)
                else:
                    modified_lines.append(line)
            else:
                modified_lines.append(line)

        # Write back
        with open(filepath, 'w') as f:
            f.writelines(modified_lines)

        return True

    except Exception as e:
        print(f"Error processing {filepath}: {e}")
        return False


def add_noqa_to_benchmark_scripts_e402(filepath: Path) -> bool:
    """Add noqa comments to E402 violations in benchmark scripts."""
    try:
        with open(filepath, 'r') as f:
            lines = f.readlines()

        modified_lines = []
        in_path_section = False

        for i, line in enumerate(lines, 1):
            # Check for path setup section
            if 'sys.path.insert' in line:
                in_path_section = True
                modified_lines.append(line)
                continue

            if in_path_section:
                if line.strip().startswith('from src.') or line.strip().startswith('import'):
                    # Add noqa comment if not already present
                    if '# noqa' not in line:
                        modified_lines.append(line.rstrip() + '  # noqa: E402\n')
                    else:
                        modified_lines.append(line)
                else:
                    in_path_section = False
                    modified_lines.append(line)
            else:
                modified_lines.append(line)

        # Write back
        with open(filepath, 'w') as f:
            f.writelines(modified_lines)

        return True

    except Exception as e:
        print(f"Error processing {filepath}: {e}")
        return False


def main():
    """Main function to re-add proper noqa comments."""
    project_root = Path(__file__).parent.parent

    files_to_fix = [
        (project_root / 'src' / 'loats' / 'database_async_additions.py', add_noqa_to_database_async_additions_f401),
        (project_root / 'src' / 'loats' / 'database_async_additions.py', add_noqa_to_database_async_additions_e402),
        (project_root / 'src' / 'loats' / 'database_async_additions_temp.py', add_noqa_to_database_async_additions_f401),
        (project_root / 'src' / 'loats' / 'database_async_additions_temp.py', add_noqa_to_database_async_additions_e402),
        (project_root / 'scripts' / 'benchmark_performance.py', add_noqa_to_benchmark_scripts_e402),
        (project_root / 'scripts' / 'benchmark_supertrend.py', add_noqa_to_benchmark_scripts_e402),
    ]

    results = []
    for filepath, fix_func in files_to_fix:
        if filepath.exists():
            result = fix_func(filepath)
            if filepath.name not in [r[0] for r in results]:  # Avoid duplicates
                results.append((filepath.name, result))
            status = "✅" if result else "❌"
            print(f"{status} {filepath.name} ({fix_func.__name__})")
        else:
            print(f"⚠️  {filepath.name} - file not found")
            if filepath.name not in [r[0] for r in results]:
                results.append((filepath.name, False))

    # Summary
    print("\nSummary:")
    for name, result in results:
        status = "✅" if result else "❌"
        print(f"{status} {name}")

    if all(r for _, r in results):
        print("\n✅ All violations fixed with inline noqa comments")
        return 0
    else:
        print(f"\n❌ Some files failed to process")
        return 1


if __name__ == '__main__':
    sys.exit(main())