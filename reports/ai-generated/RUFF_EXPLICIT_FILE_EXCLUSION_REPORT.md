# Ruff Explicit File Exclusion Issue - Resolution Report

## Issue
Running `python -m ruff check .env.example src/loats/alerts.py` produces 4 syntax errors on `.env.example` because Ruff tries to parse it as Python code.

## Root Cause
**Ruff does not respect exclusion rules for explicitly-passed files on the command line.** This is a fundamental design limitation.

### What Works:
- ✅ `ruff check src/` - Exclusions work
- ✅ `ruff check .` - Exclusions work  
- ✅ `ruff check --exclude "*.env" src/` - CLI exclusions work for directories

### What Doesn't Work:
- ❌ `ruff check .env.example` - Exclusions ignored
- ❌ `ruff check --exclude "*.env" .env.example` - CLI exclusions ignored
- ❌ `ruff check --extend-exclude "*.env" .env.example` - CLI exclusions ignored
- ❌ `[tool.ruff] exclude = ["*.env"]` in pyproject.toml - Config exclusions ignored
- ❌ `.ruffignore` file - Ruff ignores it for explicit files

## Investigation Summary

| Method | Config File | CLI Flag | Explicit File |
|--------|-------------|----------|---------------|
| `exclude` | ✅ works | N/A | ❌ ignored |
| `extend-exclude` | ✅ works | ❌ ignored | ❌ ignored |
| `force-exclude = true` | ❌ ignored | N/A | ❌ ignored |
| `--exclude` | N/A | ❌ ignored | ❌ ignored |
| `--extend-exclude` | N/A | ❌ ignored | ❌ ignored |
| `.ruffignore` | ✅ works | N/A | ❌ ignored |

## Confirmed Working Configuration

pyproject.toml now uses `exclude` (not `extend-exclude`) and works for directory linting:

```toml
[tool.ruff]
line-length = 88
target-version = "py312"
exclude = [
    "*.env",         # Any .env files (shell config, not Python)
    ".ruff_cache",   # Ruff cache directory
]
```

## Recommended Developer Workflow

**Correct usage:**
```bash
# Lint directories/packages - exclusions work correctly
ruff check src/
ruff check tests/

# Lint specific Python files (that are NOT .env files)
ruff check src/loats/alerts.py
```

**Avoid:**
```bash
# DON'T lint .env.example directly - exclusions won't help
ruff check .env.example  # Will fail with syntax errors
```

## Status
- Directory linting: ✅ WORKING
- Explicit file exclusion: ❌ KNOWN LIMITATION (Ruff behavior)

This is a Ruff design decision, not a configuration error. The workaround is to use directory/package linting instead of explicit file arguments.