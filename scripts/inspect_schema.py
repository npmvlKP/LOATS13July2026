#!/usr/bin/env python3
"""Inspect current database schema."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from loats.database import Database  # noqa: E402


def main() -> int:
    db = Database(
        db_path=Path("tmp_schema.db"),
        audit_log_path=Path("tmp_audit.jsonl"),
    )
    conn = db._get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT name, sql FROM sqlite_master WHERE type='table'")
    for name, sql in cursor.fetchall():
        print(f"TABLE: {name}")
        print(sql)
        print("---")
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
