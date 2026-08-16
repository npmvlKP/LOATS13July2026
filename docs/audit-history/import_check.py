"""Import smoke-test for loats modules."""

import sys

sys.path.insert(0, "src")
results = []
modules = [
    "loats",
    "loats.alerts",
    "loats.database",
    "loats.main",
    "loats.metrics",
    "loats.models",
    "loats.openalgo",
    "loats.options",
    "loats.scheduler",
    "loats.sentiment",
    "loats.config",
    "loats.config.settings",
    "loats.ta",
    "loats.utils.cache",
    "loats.utils.rate_limiter",
    "loats.utils.circuit_breaker",
]
for m in modules:
    try:
        __import__(m)
        results.append((m, "OK"))
    except Exception as e:
        results.append((m, f"FAIL: {type(e).__name__}: {e}"))
for m, s in results:
    print(f"{m:35s} {s}")
print()
print(f"PASS: {sum(1 for _, s in results if s == 'OK')}/{len(results)}")
