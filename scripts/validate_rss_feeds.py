#!/usr/bin/env python
"""CLI wrapper for loats.rss_validation (F8-L-05 feed validator).

Thin entry point over the production module; all logic lives in
src/loats/rss_validation.py so CI, startup, and this CLI exercise one
implementation. See that module's docstring for the F8-L-05 rationale.

Modes:
  (default)  live validation of settings.rss_feeds (requires OPENALGO_API_KEY)
  --offline  recorded-fallback manifest validation (no network; CI/startup)
  --check    offline manifest validation + live drift pass on manifest sources

Exit codes: 0 = all feeds valid; 1 = at least one invalid; 2 = usage error.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from loats.rss_validation import (
    ManifestValidationResult,
    run_offline_manifest_validation,
    validate_feed,
)


def _print_manifest(result: ManifestValidationResult) -> None:
    for r in result.results:
        if r.ok:
            print(f"[PASS] {r.name} -- recorded fixture valid ({r.fixture})")
        else:
            for problem in r.problems:
                print(f"[FAIL] {r.name} -- {problem}")


async def _run_check() -> int:
    result = run_offline_manifest_validation()
    print(f"sources={len(result.results)} (manifest)")
    _print_manifest(result)
    if not result.ok:
        print("FAIL: offline manifest validation failed; skipping live drift pass")
        return 1
    print("-- live drift pass --")
    failures = 0
    for url in result.urls:
        ok, detail = await validate_feed(url)
        print(f"[{'PASS' if ok else 'FAIL'}] {url} -- {detail}")
        failures += 0 if ok else 1
    return 1 if failures else 0


async def _run_settings_live() -> int:
    from loats.config import get_settings

    urls = list(get_settings().rss_feeds)
    print(f"sources={len(urls)} (settings.rss_feeds)")
    if not urls:
        print("FAIL: settings.rss_feeds is empty")
        return 1
    failures = 0
    for url in urls:
        ok, detail = await validate_feed(url)
        print(f"[{'PASS' if ok else 'FAIL'}] {url} -- {detail}")
        failures += 0 if ok else 1
    print(f"TOTAL: {len(urls) - failures}/{len(urls)} feeds valid")
    return 1 if failures else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="RSS feed validator (F8-L-05)")
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--offline",
        action="store_true",
        help="validate the recorded manifest only (no network; CI/startup fallback)",
    )
    group.add_argument(
        "--check",
        action="store_true",
        help="offline manifest validation + live re-validation of manifest sources",
    )
    parser.add_argument(
        "--json-out",
        type=Path,
        default=None,
        help="write a JSON result summary to this path",
    )
    args = parser.parse_args(argv)

    print("RSS FEED VALIDATOR (F8-L-05)")
    mode = "offline" if args.offline else "check" if args.check else "live"
    try:
        if args.offline:
            result = run_offline_manifest_validation()
            print(f"sources={len(result.results)} (manifest)")
            _print_manifest(result)
            total = len(result.results)
            print(f"TOTAL: {total - len(result.failures)}/{total} recorded feeds valid")
            rc = 0 if result.ok else 1
        elif args.check:
            rc = asyncio.run(_run_check())
        else:
            rc = asyncio.run(_run_settings_live())
    except Exception as exc:
        # Manifest structural problems (RssManifestError) and settings
        # failures land here; usage-visible, fail-closed.
        print(f"FAIL: {exc}")
        rc = 2

    if args.json_out is not None:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(
            json.dumps({"mode": mode, "exit_code": rc}, indent=2), encoding="utf-8"
        )
    print(f"RESULT: mode={mode} exit_code={rc}")
    return rc


if __name__ == "__main__":
    sys.exit(main())
