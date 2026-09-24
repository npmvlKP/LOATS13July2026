# F9-M-02 Closure — Branch Protection on `main` (24Sep2026)

- **Issue ID:** F9-M-02 (15Sep2026 FR9 forensic review, item → TODO-7) · **Category:** DevOps / SCM integrity · **Severity:** Medium · **Confidence:** Certain
- **Status:** CLOSED 2026-09-24 (same day as the live re-confirmation; the finding had been open across three consecutive reviews)
- **Delivery:** PR (branch `fix/f9m02-branch-protection`); this record, the `docs/RISK-REGISTER.md` header update and the `CONTRIBUTING.md` drift correction landed in the same wave.

## 1. Evidence (live, 2026-09-24 IST)

| Probe | Result |
|---|---|
| `GET /repos/npmvlKP/LOATS13July2026/branch-protection/main` (before) | **HTTP 404** — authenticated admin token (`permissions.admin=true`), matching the 15Sep FR9 row verbatim |
| `GET .../rulesets` (before) | `[]` — no rulesets existed |
| Collaborators | `npmvlKP` (solo owner) |

## 2. Root cause

Perpetually deferred manual gate at the GitHub server surface: branch protection
lives **server-side only** (no commit represents it), so nothing in the
repository could fail when the setting vanished after the 2026-09-07
verification. `CONTRIBUTING.md` kept asserting "verified via API on
2026-09-07" — documentation drift over a live-ops fact. The 15Sep FR9 review
caught the 404; no remediation landed until today (third consecutive review).

## 3. Remediation (API contract)

`PUT /repos/npmvlKP/LOATS13July2026/branches/main/protection` with the exact
documented end-state (CONTRIBUTING contract):

```json
{"required_status_checks":{"strict":true,"contexts":["deps-sync","ruff-lint","ruff-format","isort","flake8","bandit","commit-lint","mypy","pytest-coverage","pip-audit"]},"enforce_admins":true,"required_pull_request_reviews":{"dismiss_stale_reviews":true,"require_code_owner_reviews":false,"required_approving_review_count":1},"restrictions":null,"required_conversation_resolution":false,"allow_force_pushes":false,"allow_deletions":false}
```

Advisory jobs (`repo-hygiene`, `rss-feeds`, `ruff-repo-scope`, `gitleaks`,
`Docker Build`, `benchmark-perf`) are deliberately NOT required contexts —
per the documented context-list rule; `benchmark-perf` promotion stays bound
to the ADR-0016 / F9-H-02 decision. Linear history deliberately NOT required
(merge-commit flow is the established house pattern).

## 4. Verification (live probes, 2026-09-24)

1. **PUT applied:** response 200 with the full config verbatim (10 contexts,
   `strict:true`, `dismiss_stale_reviews:true`, count 1, `enforce_admins
   {enabled:true}`, `allow_force_pushes/deletions {enabled:false}`,
   `restrictions:null`). Idempotent re-PUT returned the same payload.
2. **Surface quirk (documented, load-bearing):** after both successful PUTs,
   the **classic REST GET kept returning 404** (immediate and at +60 s), and
   `GET /rulesets` stayed `[]` — yet the rule IS live and enforced. Three
   independent surfaces prove the live state:
   - GraphQL `branchProtectionRule`: `BPR_kwDOTXR8vs4E7JrB`, pattern `main`,
     `isAdminEnforced:true`, `requiredApprovingReviewCount:1`, all 10 contexts;
   - `GET /branches/main`: `"protected":true, "protection_enabled":true`;
   - the PUT's own response (ruleset-era fields `block_creations`,
     `lock_branch`, `allow_fork_syncing` present).
   GitHub has migrated classic branch protection onto unified ruleset
   storage for this repo; the legacy REST GET path no longer resolves the
   migrated rule. **The 13Sep session's "404 → relax body derive → collapse"
   scare is now explained by this same surface quirk, not by a vanishing
   rule.** Verification of protection on this repo MUST use the GraphQL BPR
   query (or `/branches/main`) — never the classic REST GET alone.
3. **Enforcement probe (direct push to `main`):** a local commit ahead of
   `origin/main` pushed via `git push origin HEAD:main` was **rejected by the
   remote hook** — `! [remote rejected] main -> main (GH006: Protected branch
   update failed for refs/heads/main)`; `remote: - Required status checks
   must pass`, `remote: - Required pull request reviews must pass`, exit 1.
   `origin/main` unchanged (ls-remote re-read identical). No probe commit
   landed anywhere; the probe delta rode the PR branch only.

## 5. Residual risk and drift detection

- Protection can still be lost server-side without any commit noticing.
  Standing rule (now written into `CONTRIBUTING.md`): re-verify the GraphQL
  BPR query before trusting the doc text; a 404/empty-BPR means re-apply the
  PUT above.
- If the token ever loses admin scope, the PUT fails 404/403 — report to the
  owner (UI path: Settings → Branches → Add classic branch protection rule).

## 6. Same-wave edits

- `CONTRIBUTING.md`: Quality Gates bullet re-dated 2026-09-24 with the
  surface-quirk caveat; Manual Gates item 1 carries the full history
  (enabled 2026-09-07 → 404 at 15Sep review → re-enabled 2026-09-24).
- `docs/RISK-REGISTER.md`: header update only (register table rows and all
  content pins untouched; `tests/test_risk_register_current.py` unaffected).
- `scripts/ratchet_baseline.py`: ceiling re-pin 459→460 (commit 1 of 2,
  headroom-first; this record is the +1 tracked file landing exactly at
  ceiling).
