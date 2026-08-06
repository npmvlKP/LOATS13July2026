# Ruff configuration to ignore B017 for testing files
# These files intentionally test generic exception handling

[tool.ruff]
extend-exclude = [
    "tests/test_failure_paths.py",
]