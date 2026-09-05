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

Use the following format for commit messages (enforced by the
`commit-message-check` pre-commit hook since F8-L-06-R2, 2026-09-05):

```
<type>(<optional scope>)!: <subject>

<body>
```

Where:
- **type**: One of `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `chore`, `build`, `ci`
- **scope**: Optional area, e.g. `fix(p5):`; `!` after the type/scope marks a breaking change
- **subject**: Brief description of the change (the 50-character guidance is a convention, not enforced — wave evidence belongs in reports/ and docs/audit-history/, not the subject line)
- **body**: Detailed explanation of what was changed and why

Merge and revert commits are exempt (git generates their first line).
The hook rejects status-essay subjects (`Update: ...`) — a commit subject
describes the change; the commit body carries the evidence.

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
- ✅ GitHub branch protection rules (verified enforced as of 2026-09-04: pushes to `main` are rejected with GH006 — pull requests and required status checks are mandatory; direct pushes and force-pushes are blocked)

### Manual GitHub Gates (TODO-5 / TODO-6)

The following safeguards are **not** enforceable by this codebase or by an agent; they require a maintainer with repository admin access to verify in the GitHub web UI:

1. **Branch protection for `main`**: Enable "Require a pull request before merging" with at least one reviewer approval.
2. **Status checks**: Enable "Require status checks to pass before merging" and select the CI jobs that run Ruff, MyPy, Pytest, Bandit, and pip-audit.
3. **Pre-commit hooks as client-side guards**: The `.pre-commit-config.yaml` hooks run locally; they are not a server-side substitute for branch protection. Verify each contributor has run `pre-commit install`.
4. **Review dismissal / admin enforcement**: Optionally enable "Dismiss stale pull request approvals when new commits are pushed" and "Include administrators". *(Empirically confirmed enforced as of 2026-09-04: a direct force-push to `main` was rejected with GH006 "Protected branch update failed" — PR-only, 10 required status checks, force-pushes forbidden. The probe commits that prompted TODO-5/TODO-6 landed before protection was enabled.)*

### Frozen Audit Evidence

`docs/audit-history/` and `reports/ai-generated/` are frozen verification
artifacts, preserved verbatim as historical evidence (see the rationale
comment on the per-file-ignores in `pyproject.toml`). They are excluded
from repository-root lint sweeps (`.flake8` exclude, per-file-ignores in
`pyproject.toml`) but remain **lint-enforced everywhere else**: the CI
`ruff-repo-scope` job runs `ruff check .` from the repository root on
every push.

To revive an archived script, **promote it out of the frozen directory**
into `scripts/` (or `src/`/`tests/` as appropriate), repair it to pass
the full root-level lint battery (`ruff check .`, `ruff format`,
`flake8 .`), and account for it in the `TRACKED_FILE_CEILING` ratchet
(`scripts/check_repo_hygiene.py`). Never edit a file in place under the
frozen directories to satisfy lint.

### Gate-Tool Upgrade Procedure (Version Lockstep)

Every gate tool (ruff, mypy, isort, flake8, bandit, pip-audit) is pinned
(`==`) to the version the tree was verified against. A deliberate upgrade
must touch **all surfaces in one commit** and keep `pytest
tests/test_repo_hygiene.py -q` green:

1. Verify the upstream tag exists (e.g. `git ls-remote --tags
   https://github.com/astral-sh/ruff-pre-commit refs/tags/vX.Y.Z`).
2. Bump the `==` pin in `pyproject.toml` `[project.optional-dependencies]
   dev`, install it into the venv, and run the full gate battery locally.
3. Mirror the pin into every `ci.yml` install line for that tool
   (`ruff` ×3; `isort`, `flake8`, `bandit`, `pip-audit` ×1 each; mypy
   rides `.[dev]`).
4. Mirror the pin into `.pre-commit-config.yaml` (`ruff-pre-commit` rev
   = ruff pin, `PyCQA/flake8` rev = flake8 pin; mypy, bandit and
   pip-audit run as `language: system` local hooks and inherit the venv
   pins automatically).
5. Run the battery: `ruff check .`, `ruff format --check src/ tests/
   scripts/`, `flake8 .`, `mypy --strict src`, `pytest
   tests/test_repo_hygiene.py -q`, then the full suite.

`TestLintVersionLockstep` fails if any surface is missed, so a partial
upgrade cannot land.

## Code Review

All changes require review and approval before merging. The QA team will perform final validation and declare production readiness. Branch protection and pre-commit hook configuration are checked manually by maintainers (TODO-5 / TODO-6).

## Reporting Issues

Please report any issues or bugs through the project's issue tracker with detailed reproduction steps.

---

**Note**: This policy is enforced by pre-commit hooks. Any commit message containing prohibited phrases will be automatically rejected.

### pip-audit Time Sensitivity

The `pip-audit` security gate reports **zero vulnerabilities against production dependencies as of today**. Because the vulnerability database is updated continuously, a clean audit today does not guarantee a clean audit tomorrow. Re-run `pip-audit -r requirements-core.txt` before every release and in CI at least daily. Any newly disclosed advisory must be triaged and either remediated or documented as an accepted risk.