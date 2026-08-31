#!/usr/bin/env python3
"""Inspect Database async method signatures and pool type."""
import inspect
import sys
import textwrap
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from loats.database import Database

print("async_initialize source:")
print(textwrap.dedent(inspect.getsource(Database.async_initialize)))
print("\nasync_get_historical_data source:")
print(textwrap.dedent(inspect.getsource(Database.async_get_historical_data)))
print("\nasync_store_quote source:")
print(textwrap.dedent(inspect.getsource(Database.async_store_quote)))
print("\nasync_get_trade source:")
print(textwrap.dedent(inspect.getsource(Database.async_get_trade)))
