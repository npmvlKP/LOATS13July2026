import os

files = [
    "src/loats/alerts.py",
    "src/loats/database.py",
    "src/loats/initialization.py",
    "src/loats/main.py",
    "src/loats/metrics.py",
    "src/loats/openalgo.py",
    "src/loats/options.py",
    "src/loats/scheduler.py",
    "src/loats/sentiment.py",
    "src/loats/ta.py",
    "src/loats/__init__.py",
    "src/loats/utils/cache.py",
    "src/loats/utils/circuit_breaker.py",
    "src/loats/utils/retry.py",
]
for file_path in files:
    if os.path.exists(file_path):
        with open(file_path, encoding="utf-8") as f:
            content = f.read()
        new_content = content.replace("from .logging", "from .loats_logging")
        new_content = new_content.replace("from ..logging", "from ..loats_logging")
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(new_content)
        print(f"Updated: {file_path}")
    else:
        print(f"File not found: {file_path}")
