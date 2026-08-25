# Contributing to LOATS13July2026

Thank you for your interest in contributing to LOATS13July2026! This document provides guidelines and standards for contributing to the trading research system.

## Commit Message Standards

### General Requirements

All commit messages must:
- Use clear, descriptive language about what was accomplished
- Follow conventional commit format when appropriate (e.g., `feat:`, `fix:`, `refactor:`)
- Be concise yet informative
- Reference related issues when applicable

### Prohibited Claims

**IMPORTANT:** Commit messages must NOT claim deployment readiness or production status. This is a strict policy to prevent misleading statements that could circumvent quality gates.

The following phrases are **PROHIBITED** in commit messages:
- `ready for deployment`
- `production ready`
- `ready for production`
- `deployment ready`
- `production-ready`
- `deployment-ready`

### Commit Message Enforcement

This repository enforces commit message standards through:

1. **Git Commit-msg Hook**: All commits are validated locally using a git hook that automatically checks for prohibited phrases and rejects violations.

2. **CI Validation**: Commit messages on pull requests are validated through continuous integration to ensure standards are maintained.

### Examples of Acceptable Commit Messages

✅ **Good:**
```
feat: add VIX fail-safe mechanism to buy/sell gating

Implements symmetric VIX threshold check at 15. If VIX data feed
fails, both BUY and SELL operations are blocked to prevent
unintended risk exposure.

Fixes #123
```

```
fix: correct IV-rank threshold from 60 to 30 for BUY operations

Updates the BUY band gate to use the CMP-specified threshold of 30,
preventing buys in IV regimes classified as sell-side.
```

```
refactor: move probe scripts from src/ to scripts/

Relocates cmp.py, utils.py, and probe_rate_limiter.py to improve
project structure and fix mypy pathing issues.
```

❌ **Bad (PROHIBITED):**
```
feat: add VIX fail-safe mechanism - ready for production
```

```
fix: correct IV threshold - production ready commit
```

```
deployment ready: VIX fail-safe implemented
```

## Development Workflow

### Setting Up Your Development Environment

1. **Clone the repository:**
   ```bash
   git clone https://github.com/npmvlKP/LOATS13July2026.git
   cd LOATS13July2026
   ```

2. **Create and activate the virtual environment:**
   ```bash
   python -m venv LOATS13July2026
   LOATS13July2026\Scripts\activate  # On Windows
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   pip install -r requirements-dev.txt
   ```

### Quality Gates

All contributions must pass the following quality checks before being merged:

- **Dependency Synchronization:** `scripts/check_deps_sync.py`
- **Code Formatting:** `ruff check` and `ruff format --check`
- **Import Sorting:** `isort --check-only`
- **Linting:** `flake8`
- **Type Checking:** `mypy --strict`
- **Security:** `bandit`
- **Testing:** `pytest` with coverage requirements
- **Commit Message Validation:** Enforced by git hook and CI

### Running Tests

Run the full test suite:
```bash
.\LOATS13July2026\Scripts\python.exe -m pytest tests\ -q
```

Run a specific test module:
```bash
.\LOATS13July2026\Scripts\python.exe -m pytest tests\test_module.py -q
```

### Health Checks

The repository includes comprehensive health verification scripts:

```bash
# Run all health checks
.\LOATS13July2026\Scripts\python.exe scripts\fr7_health_check.py --fast

# Run specific health checks
.\LOATS13July2026\Scripts\python.exe scripts\fr7_health_check.py --only HC-17 HC-15
```

## Pull Request Process

1. **Create a feature branch:** Use a descriptive branch name (e.g., `fix/vix-fail-safe`)
2. **Make your changes:** Follow commit message standards
3. **Run quality gates locally:** Ensure all checks pass before pushing
4. **Submit a pull request:** Describe your changes clearly
5. **Address feedback:** Respond to review comments promptly
6. **Ensure CI passes:** All required checks must be green before merge

## Code Standards

### Python Code Style

- Follow PEP 8 style guidelines
- Use type hints consistently
- Write docstrings for all public functions and classes
- Maintain test coverage ≥80% aggregate, with per-module minimums

### Domain-Specific Rules

- **Decimal-only calculations:** All financial calculations must use `Decimal` type
- **Timezone-aware datetime:** All datetime operations must be timezone-aware
- **Structured logging:** Use proper logging levels and formats
- **Secure exception handling:** Never expose sensitive information in exceptions
- **SEBI compliance:** Adhere to all regulatory requirements

### Testing Standards

- Write tests first for new features (TDD approach)
- Maintain high test coverage (≥80% aggregate, per-module floors)
- Include both unit and integration tests
- Test edge cases and failure paths
- Mock external dependencies appropriately

## Troubleshooting

### Commit Hook Issues

If you encounter issues with the commit-msg hook:

1. **Verify the hook is accessible:**
   ```bash
   # On Windows, check file exists
   Test-Path .git\hooks\commit-msg
   ```

2. **Test the hook manually:**
   ```bash
   # Create a test commit message file
   echo "test: validate commit message" > .git/COMMIT_EDITMSG
   
   # Run the validation script directly
   .\LOATS13July2026\Scripts\python.exe scripts\commit_message_check.py .git/COMMIT_EDITMSG
   ```

3. **Temporarily bypass the hook (not recommended):**
   ```bash
   git commit --no-verify -m "your message"
   ```

### Common Issues

**Issue:** "Commit message validator not found"
- **Solution:** Ensure you're running from the repository root and the `scripts/commit_message_check.py` file exists.

**Issue:** "ModuleNotFoundError" when running tests
- **Solution:** Activate the virtual environment and ensure dependencies are installed.

**Issue:** "Mypy strict mode fails"
- **Solution:** Address type hints and strict typing issues before committing.

## Getting Help

If you need assistance:

1. Check existing issues and pull requests
2. Review the health check scripts for guidance
3. Consult the FR (Functional Requirements) documentation
4. Ask questions in pull requests or issues

## License

By contributing to this repository, you agree that your contributions will be licensed under the same license as the project.

---

Thank you for following these guidelines and contributing to LOATS13July2026!