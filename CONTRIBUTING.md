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
- ✅ GitHub branch protection rules — verified via API on 2026-09-24
  (F9-M-02 closure wave: re-enabled via REST after the silent 404
  regression recorded in
  `docs/audit-history/24Sep2026-F9M02-branch-protection-closure.md`;
  `GET /repos/npmvlKP/LOATS13July2026/branches/main/protection`):
  `required_status_checks.strict=true` with 10 required contexts
  (`deps-sync`, `ruff-lint`, `ruff-format`, `isort`, `flake8`, `bandit`,
  `commit-lint`, `mypy`, `pytest-coverage`, `pip-audit`),
  `required_pull_request_reviews.required_approving_review_count=1`,
  `enforce_admins=true`, `allow_force_pushes=false`,
  `allow_deletions=false`. Direct pushes are rejected (GH006); PRs and
  required status checks are mandatory. The repo-hygiene, rss-feeds,
  ruff-repo-scope, gitleaks, docker and benchmark-perf jobs run on
  every push/PR but are intentionally NOT in the required-context list
  — they remain advisory signals on main; add a context there only when
  a job must gate merges. benchmark-perf (ADR-0016) is promoted to a
  required context in the same wave as the deferred F9-H-02
  latency-budget decision.

### Manual GitHub Gates (TODO-5 / TODO-6)

The following safeguards are **not** enforceable by this codebase or by an agent; they require a maintainer with repository admin access to verify in the GitHub web UI:

1. **Branch protection for `main`**: Enable "Require a pull request before merging" with at least one reviewer approval. *(RE-VERIFIED via API 2026-09-24 (F9-M-02 closure): enabled, 1 approval, dismiss-stale, admin-enforced — see Quality Gates above. History: enabled 2026-09-07; found silently absent — 404 — at the 2026-09-15 FR9 review and re-confirmed live 2026-09-24; re-enabled via the REST API 2026-09-24. The setting lives server-side only and can be lost without any commit touching this file: re-verify the GET before trusting this text. No UI check outstanding.)*
2. **Status checks**: Enable "Require status checks to pass before merging" and select the CI jobs that run Ruff, MyPy, Pytest, Bandit, and pip-audit. *(VERIFIED via API 2026-09-07: 10 required contexts, strict — see Quality Gates above.)*
3. **Pre-commit hooks as client-side guards**: The `.pre-commit-config.yaml` hooks run locally; they are not a server-side substitute for branch protection. Verify each contributor has run `pre-commit install` — since the ADR-0014 gitleaks pre-push net (2026-09-10), the config pins `default_install_hook_types: [pre-commit, commit-msg, pre-push]`, so a bare install also creates the pre-push shim; without it the pre-push inventory (pytest, per-module coverage, pip-audit, the gitleaks default-rules secret net) silently never fires. The secret net requires the gitleaks binary on PATH (or `GITLEAKS_BINARY` set) and **fails closed** when it is missing.
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
(`scripts/ratchet_baseline.py` — the single pinned value; re-pin there
and append its history line in the same commit). Never edit a file in
place under the frozen directories to satisfy lint.

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

#### Which environment does pip-audit audit? (dual-venv pinning)

`pip-audit` environment mode audits the interpreter **embedded in the launcher that was executed**, not the prompt's active environment. With two local venvs (`.venv/`, `loatsNEW/`) a prompt activated on `loatsNEW` can silently execute `.venv\Scripts\pip-audit.exe`; the tool then warns:

```text
WARNING:pip_audit._dependency_source.pip:pip-audit will run pip against <repo>\.venv\Scripts\python.exe,
but you have a virtual environment loaded at <repo>\loatsNEW. This may result in unintuitive audits,
since your local environment will not be audited. You can forcefully override this behavior by
setting PIPAPI_PYTHON_LOCATION to the location of your virtual environment's Python interpreter.
```

Treat that WARNING as a hard stop, not noise: the verdict belongs to the first path, never to the activated prompt. Pin the audited interpreter explicitly (PowerShell 5.1; require exit code 0):

```powershell
$env:PIPAPI_PYTHON_LOCATION = "G:\.OA\LOATS-13July2026\LOATS13July2026\.venv\Scripts\python.exe"
& "G:\.OA\LOATS-13July2026\LOATS13July2026\.venv\Scripts\pip-audit.exe" --ignore-vuln PYSEC-2026-3740 --progress-spinner off
Remove-Item Env:PIPAPI_PYTHON_LOCATION
```

Environment roles (verified 2026-09-18): `.venv/` is uv-managed from `uv.lock` and mirrors the CI `pip install .` audit job — it is the **canonical audit target**. `loatsNEW/` is the `python -m venv` environment hosting the pre-commit hooks; it is not authoritative for dependency state (dev residue such as the pre-ADR-0003/0004 `ta`/`vollib` cluster may persist there) and is scheduled for rebuild.
