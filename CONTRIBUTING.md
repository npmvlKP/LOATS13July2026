# Contributing to LOATS13July2026

Thank you for your interest in contributing to this project! Please read these guidelines carefully before submitting any changes.

## Commit Message Guidelines

### Prohibited Phrases

To maintain transparency and prevent misleading claims, the following phrases are **strictly prohibited** in commit messages:

- `READY FOR DEPLOYMENT`
- `PRODUCTION READY`
- `READY FOR PRODUCTION`
- `DEPLOYMENT READY`
- `PRODUCTION-READY`
- `DEPLOYMENT-READY`

### Rationale

Commit messages that claim deployment readiness create false confidence and can mask regressions. Only the QA gate may declare production readiness after comprehensive testing and validation.

### Acceptable Alternatives

Instead of claiming deployment readiness, use descriptive language about what was accomplished:

- ✅ "Implemented rate limiter per-call functionality"
- ✅ "Fixed circuit breaker exception handling"
- ✅ "Added comprehensive test coverage for cache operations"
- ✅ "Resolved HTML injection vulnerability"
- ✅ "All quality gates passing: Ruff, MyPy, Pytest"

### Commit Message Format

Use the following format for commit messages:

```
<type>: <subject>

<body>
```

Where:
- **type**: One of `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `chore`
- **subject**: Brief description of changes (50 characters or less)
- **body**: Detailed explanation of what was changed and why

### Examples

**Good:**
```
fix: rate limiter per-call implementation

- Fixed F-CONC-3 rate limiter to properly enforce SEBI OPS limits
- Added singleton behavior for identical parameter calls
- Maintained backward compatibility
- All existing tests continue to pass
```

**Bad:**
```
Update: Rate limiter functionality remains unchanged

- No regressions introduced
- READY FOR DEPLOYMENT
- 100% tests passed
```

## Development Process

1. **Create a branch**: Use a descriptive branch name (e.g., `fix/rate-limiter-concurrency`)
2. **Make changes**: Follow the existing code style and architecture
3. **Write tests**: Ensure comprehensive test coverage
4. **Run quality gates**: All checks must pass before committing
5. **Commit**: Use descriptive, accurate commit messages
6. **Push**: Submit for review

## Quality Gates

All commits must pass the following quality gates:

- ✅ Ruff (linting)
- ✅ MyPy (type checking)
- ✅ Pytest (testing)
- ✅ Bandit (security scanning)
- ✅ Pre-commit hooks (client-side; must be verified locally)
- ✅ GitHub branch protection rules (must be verified in repository settings by a maintainer; an agent cannot mechanically enforce them)

### Manual GitHub Gates (TODO-5 / TODO-6)

The following safeguards are **not** enforceable by this codebase or by an agent; they require a maintainer with repository admin access to verify in the GitHub web UI:

1. **Branch protection for `main`**: Enable "Require a pull request before merging" with at least one reviewer approval.
2. **Status checks**: Enable "Require status checks to pass before merging" and select the CI jobs that run Ruff, MyPy, Pytest, Bandit, and pip-audit.
3. **Pre-commit hooks as client-side guards**: The `.pre-commit-config.yaml` hooks run locally; they are not a server-side substitute for branch protection. Verify each contributor has run `pre-commit install`.
4. **Review dismissal / admin enforcement**: Optionally enable "Dismiss stale pull request approvals when new commits are pushed" and "Include administrators".

## Code Review

All changes require review and approval before merging. The QA team will perform final validation and declare production readiness. Branch protection and pre-commit hook configuration are checked manually by maintainers (TODO-5 / TODO-6).

## Reporting Issues

Please report any issues or bugs through the project's issue tracker with detailed reproduction steps.

---

**Note**: This policy is enforced by pre-commit hooks. Any commit message containing prohibited phrases will be automatically rejected.

### pip-audit Time Sensitivity

The `pip-audit` security gate reports **zero vulnerabilities against production dependencies as of today**. Because the vulnerability database is updated continuously, a clean audit today does not guarantee a clean audit tomorrow. Re-run `pip-audit -r requirements-core.txt` before every release and in CI at least daily. Any newly disclosed advisory must be triaged and either remediated or documented as an accepted risk.