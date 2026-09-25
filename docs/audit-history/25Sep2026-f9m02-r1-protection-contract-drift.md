# F9-M-02-R1 — Branch-Protection Contract Drift Reconciliation (25Sep2026)

- **Issue ID:** F9-M-02-R1 (drift follow-up to the F9-M-02 closure of 24Sep2026) · **Category:** DevOps / SCM integrity · **Severity:** Medium · **Confidence:** Certain
- **Status:** CORRECTED 2026-09-25 (server-side PUT + this audited record); paste-reconciliation finding, not a new code defect

## 1. Trigger

The 15Sep FR9 paste (F9-M-02 row) was re-run through the Step-0
reconciliation drill. The finding itself is STALE — protection has been
live since the 24Sep closure — but the live config had silently drifted
from the documented contract:

| Field | Documented contract (24Sep closure §3, CONTRIBUTING L97-99) | Live at 2026-09-25 13:30 IST |
|---|---|---|
| `required_status_checks.strict` | `true` | **`false`** |
| Required contexts | 10 (the merge-gating CI set) | **16** — the 10 plus `Docker Build`, `benchmark-perf (F9-H-02 prerequisite, advisory)`, `gitleaks`, `repo-hygiene`, `rss-feeds (F8-L-05 recorded fallback)`, `ruff-repo-scope (repository root)` |

The six extra contexts are exactly the jobs the closure record §3 says are
"deliberately NOT required contexts — per the documented context-list
rule", and two of their pinned names even carry `advisory` /
`recorded fallback` annotations while gating merges. Protection lives
server-side only: no commit, PR, or workflow run explains the change,
which is the precise silent-drift failure class the 24Sep closure §5
warned about ("protection can still be lost server-side without any
commit noticing").

## 2. Operational risk that forced same-day correction

With `rss-feeds (F8-L-05 recorded fallback)` required, a recorded-fallback
degradation of that job would leave `main` unmergeable (no PR can satisfy
the context), and `strict:false` additionally allows merges onto a stale
integration ref. Both violate the repo's own written gate contract.

## 3. Remediation

Idempotent restore of the documented end-state, byte-identical to the
24Sep closure §3 payload (10 contexts, `strict:true`, 1 approving review,
dismiss-stale, code-owner false, admin-enforced, force-push/delete
forbidden, restrictions null):

```json
{"required_status_checks":{"strict":true,"contexts":["deps-sync","ruff-lint","ruff-format","isort","flake8","bandit","commit-lint","mypy","pytest-coverage","pip-audit"]},"enforce_admins":true,"required_pull_request_reviews":{"dismiss_stale_reviews":true,"require_code_owner_reviews":false,"required_approving_review_count":1},"restrictions":null,"required_conversation_resolution":false,"allow_force_pushes":false,"allow_deletions":false}
```

Drifted live config preserved before the PUT:
16 contexts / `strict:false` (full GET JSON retained in the session
scratch as `protection_before_drift.json`; summary in §1).

## 4. Verification (live probes, 2026-09-25 IST)

1. **PUT response** echoed the contract verbatim: 10 contexts,
   `strict:true`, approvals 1, dismiss-stale true, admin-enforced,
   force-push/delete disabled.
2. **Classic REST GET read-back** resolved the rule directly:
   `{"n_contexts":10,"strict":true}` — the 24Sep "persistent 404"
   surface quirk did NOT reproduce today. Concurrently, the GraphQL
   `branchProtectionRule` field used for the 24Sep read-back is now
   ABSENT from the GraphQL schema (`undefinedField` on Repository).
   **Verification-surface rule for this repo is therefore surface-agnostic
   and time-varying: confirm via whichever of (classic GET, `/branches/main`
   `protected:true`, PUT response echo) resolves today, and re-probe all
   before concluding absence.** The 24Sep register line naming the GraphQL
   BPR query as "the required verification surface" is superseded by this
   record.
3. **Enforcement probe:** an empty probe commit pushed directly at
   `main` (`git push origin HEAD:main --no-verify`) was rejected by the
   remote hook — `GH006: Protected branch update failed for
   refs/heads/main`, `- Changes must be made through a pull request.`,
   `- 10 of 10 required status checks are expected.`; push exit 1;
   `origin/main` byte-identical before/after
   (`2d1e7904…`); the probe commit was reset locally and never landed on
   any remote ref. (Method note: `--no-verify` on the probe commit bypasses
   the CLIENT-side commit-msg/pre-commit hooks — legitimate here because
   the test targets the SERVER-side rule; the 24Sep probe used the same
   bypass.)
4. Local `main` re-synced to `origin/main` (`2d1e7904`, PR #78 merge),
   tree clean, HEAD == origin both sides.

## 5. Same-wave edits

- `CONTRIBUTING.md`: Quality Gates protection bullet re-dated 2026-09-25
  with the R1 drift-and-restore history and the revised verification-
  surface rule; Manual Gates item 1 history extended (24Sep R1 note).
- `docs/RISK-REGISTER.md`: header line recording F9-M-02-R1 (drift
  observed and corrected same day; no new R-row — the standing
  "re-verify before trusting doc text" rule is now corroborated by a
  second instance).
- This record.

## 6. Residual risk (unchanged class, now twice-evidenced)

Server-side protection state can mutate outside git's visibility. The
repo now has two documented instances (15Sep absence, 25Sep contract
drift). Standing rule stays: every review wave MUST live-probe the
protection config against CONTRIBUTING's pinned contract and restore +
record on any divergence; this record is the R1 template for that drill.
