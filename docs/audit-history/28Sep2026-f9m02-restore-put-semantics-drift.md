# F9-M-02-R2 — Restore-PUT semantics drift: `dismiss_stale_reviews` silently reset (28Sep2026)

- **Issue ID:** F9-M-02-R2 (drift follow-up to the F9-M-02 closure of 24Sep and the R1 contract-drift record of 25Sep) · **Category:** DevOps / SCM integrity · **Severity:** Medium · **Confidence:** Certain
- **Status:** CORRECTED 2026-09-28 (explicit-boolean re-PUT minutes after detection; read-back verified contract-exact on both surfaces)

## 1. Trigger

During the PR #101 solo-owner relax → merge → restore sequence (18:2x IST):
the post-restore GraphQL read-back — the contract per the 24Sep/R1
procedure — returned `dismissesStaleReviews:false`. The morning probe the
same day had read `true`; the PUT exited 0.

## 2. Root cause

GitHub's branch-protection PUT semantics changed for this repo's migrated
ruleset: **omitted keys inside `required_pull_request_reviews` are now
RESET to `false`** (previously the documented behavior was "omit
false-valued review flags — they default to false", i.e. omission was
safe). The 24Sep/R1-era restore body pruned the false-valued review
flags and carried only `required_approving_review_count: 1`, so the
restore applied `dismiss_stale_reviews: false` and
`require_code_owner_reviews: false` silently. Same failure class as the
25Sep R1 drift (server-side state outside git's visibility), but this
time self-inflicted by the operator-side body, not an external actor —
and caught by the read-back contract rather than by a later audit.

## 3. Remediation

1. Re-PUT the restore body with the review flags EXPLICIT
   (`dismiss_stale_reviews: true`, `require_code_owner_reviews: false`,
   count 1). PUT rc=0.
2. Authoritative read-back: full field-by-field REST-GET contract diff —
   10/10 PASS, zero divergences (the exact 10 contexts, strict, count 1,
   dismiss-stale TRUE, code-owner false, admin-enforced, restrictions
   null, conversation-resolution/force-push/deletions false); GraphQL
   cross-check confirms (`dismissesStaleReviews:true`,
   `requiredApprovingReviewCount:1`, `isAdminEnforced:true`).
3. Standing rule updated (session skill copy of the protected-main
   procedure): restore bodies must ALWAYS carry the review flags
   explicitly; when deriving from a GET snapshot, keep its review flags
   verbatim instead of pruning false-valued keys; the post-restore
   read-back — never the PUT exit code — is the contract.

## 4. Exposure window

From the restore PUT to the corrected re-PUT (minutes, same session,
2026-09-28 ~18:3x IST). No push, merge, or PR event occurred in the
window (the merge itself had already completed under the relaxed
window); stale-review dismissal protection was the only relaxed field —
all other contract fields were applied correctly by the first restore.

## 5. Landing evidence (PR #101, same day)

- PR #101 merged 2026-09-28 as `8063380` (merge method: merge;
  relaxed-window scope: review requirement only — contexts stayed
  strict/10, admin-enforced).
- PR CI run `36427811310`: all 16 checks pass (incl. `pytest-coverage`,
  `pip-audit`, `benchmark-perf` advisory; Docker Build ran and passed on
  the docs delta).
- Post-merge Pipeline on `main`: run `36428424685` = success (HEAD
  `8063380`).
- Merged-content verification: `git diff 2ceaadb origin/main -- <wave
  paths>` EMPTY; local `main` ff-synced to `8063380`; PR branch deleted
  remote + local.
- Post-restore (corrected) contract read-back: 10/10 PASS (§3.2).
