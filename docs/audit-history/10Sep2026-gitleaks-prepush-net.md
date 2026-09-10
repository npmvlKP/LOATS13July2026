# Defense-in-Depth Gitleaks Pre-Push Net (F8-C-02 NEXT item)

**Date:** 2026-09-10 (Asia/Calcutta). Lands the NEXT item from
`10Sep2026-f8c02-residual-disposition.md`: a pre-push secret net that
scans each push's introduced commits under **pure default gitleaks
rules** — no repo allowlist — and fails the push closed on a leak or a
missing gitleaks binary.

## Why the push-time net was missing (root cause)

- `.gitleaks.toml` allowlists `.env.test` **on purpose** (values
  rotated; class dispositioned). Any gitleaks run that loads it — the
  security.yml job via `GITLEAKS_CONFIG`, and any bare local run — can
  never re-flag that class.
- ci.yml's own `gitleaks` job (PR-time) picks the same repo config up
  automatically, with the identical blindness.
- Live-verified (gitleaks 8.30.1): `detect`/`protect` are removed
  (rc=126); the supported surface is `gitleaks git --log-opts=<range>`
  with an explicit `--config`.
- Live-verified: `.git/hooks` held no pre-push shim — the entire
  pre-push inventory silently never fired on this host. Fixed at the
  root by `default_install_hook_types: [pre-commit, commit-msg,
  pre-push]` in `.pre-commit-config.yaml`.

## What landed

- `scripts/gitleaks_prepush.py` — stdin-independent runner (pre-commit
  consumes pre-push stdin itself, verified in installed 4.6.2
  `hook_impl.py`); scans `git rev-list --branches --not --remotes`
  (same range semantics as pre-commit's own fallback); fail-closed on
  missing binary and nonzero rc; rc=126 gets a dedicated actionable
  message; `GITLEAKS_BINARY` override. Injected config: 3 lines,
  `[extend] useDefault = true` — pure default rules, no allowlist.
- `.pre-commit-config.yaml` — `gitleaks-prepush` local hook at
  `stages: [pre-push]` + the install-types pin above.
- `scripts/ratchet_baseline.py` — documented re-pin 399 -> 401
  (+2: runner + this record).
- `tests/test_repo_hygiene.py` — `TestGitleaksPrepushNet` (appended).
- CONTRIBUTING.md — hook-installation instructions note the pre-push
  shim and the net.

## Live evidence (all executed 2026-09-10)

- Red **counter-proof** (honest result): default-rules scans of the
  14Jul (4c82d0f) and 26Aug (2c93e15) `.env.test` add-commits return
  **rc=0 — no finding**, in the repo and in a hermetic clone. Root
  cause, verified: `.env.test` was binary on disk (UTF-8-sig 14Jul is
  text, but its values are low-entropy 12-14 char placeholders; 26Aug
  is UTF-16, binary to scanners). The NEXT-item premise that a
  default-rules hook "would have flagged" those adds is therefore
  **corrected**: gitleaks-class detection cannot see that residue; the
  nets that caught it were rotation plus the HC-26 tracked-path guard.
- Positive controls (default rules): generic high-entropy API-key
  assignment and a Slack-token-shaped string both fire rc=1 — the net
  fails closed on the classes gitleaks exists for.
- Whole-history default-rules sweep (`--log-opts=--all`, 539 commits):
  rc=1 with 1776 findings, **all** confined to the committed
  gitleaks-report artifact class (gitleaks_report*.json et al., the
  26049046 feedback-loop residue dispositioned under F8-M-02; their
  contents are example RFC 6750/6749 tokens). No source, env, test, or
  config file is implicated. Reading: default rules DO catch that
  artifact class — which the repo allowlist deliberately suppresses —
  so the net fires exactly when such files are re-introduced, while
  the historical residue (already on the remote, outside the
  introduced range) never spams the hook.
- Pre-commit-schema validation of the config: `pre-commit validate-config`
  exit 0 (run during the wave).
