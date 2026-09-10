# F8-C-02 Residual Disposition - Reachable `.env.test` History Blobs

**Date:** 2026-09-10 (Asia/Calcutta). **Rev 2 (same day):** inventory,
reachability, and commit-count statements corrected by a topology audit;
rotation-ledger fingerprints re-verified byte-exact and unchanged. Rev 1
erroneously listed three blobs, mis-attributed a 02Aug add, and called
the 26Aug blob unreachable. This file is the single record of truth
(amended in place at eb38919 before any push; the rev-1 text was never
published). The amendment trail is disclosed in the commit message.

## Scope that was ALREADY remediated (02Sep wave, commit 34fcaf5)

The P0 roadmap entry predates the 02Sep remediation. Verified against the
live tree, not the roadmap text:

- `loatsNEW/`, `~/AppData/...`, `.env.test`, npm/uv lockfiles,
  `.gitignore` extension, and the CI/pre-commit/HC-26 tree-shape guard
  (`scripts/check_repo_hygiene.py` + `ratchet_baseline.TRACKED_FILE_CEILING=399`):
  all in place on `main` (56919a7).
- **Zero** `loatsNEW/` or `~/AppData/` blobs anywhere in reachable
  history (`git rev-list --all --objects`, 0 hits, re-verified in the
  rev-2 audit); repo pack 4.05 MiB, no filter-repo needed for those
  classes.

## Verified inventory (rev 2 — topology evidence, not narrative)

The complete lifecycle of `.env.test` across **all** refs is:

```
4c82d0f  2026-07-14  ADD    blob 309bdc1a2d3a (185 B, UTF-8-sig, 5 keys)
69f6419  2026-08-02  DELETE (this commit never contained .env.test;
                            `git rev-parse 69f6419:.env.test` -> fatal)
2c93e15  2026-08-26  ADD    blob 04ecefd69686 (80 B, UTF-16, 1 key)
34fcaf5  2026-09-02  DELETE (untrack; current state: .env.test untracked)
```

- `git log --all --diff-filter=A -- .env.test` yields exactly TWO adds:
  `4c82d0f` and `2c93e15`. `69f6419` is a deletion commit (it appears
  under `--diff-filter=D`), not an add — rev 1 mis-inventoried it.
- **Reachability (the rev-1 record was wrong here):** BOTH blobs are
  reachable from `origin/main`. Evidence: `git merge-base --is-ancestor
  <sha> origin/main` -> 0 for both add commits;
  `git rev-list origin/main --objects | grep -c <blob>` -> 1 for both
  blobs. `2c93e15` is contained in 10 refs including `origin/main`.
  There is NO unreachable residue: the reachable surface IS the entire
  residue, and a server-side gc cannot remove either blob while commit
  ancestry reaches them.
- Tag exposure: the repository has ZERO tags today, so no tag reaches
  any `.env.test` blob. Note for the future: blob reachability follows
  commit ANCESTRY, not tree membership — a tag cut anywhere on current
  main would still reach both adds through history. The disposition for
  that exposure is the rotation ledger below; only filter-repo removes
  reachability.

## Rotation ledger (fingerprint audit; values never printed)

Re-verified byte-exact in the rev-2 audit against the live `.env`
(BOM-aware parse; UTF-16 blob decoded before hashing):

| Credential          | Historical value (fingerprint, len)      | Live `.env` (fingerprint, len) | Rotated? |
|---------------------|------------------------------------------|--------------------------------|----------|
| `OPENALGO_API_KEY`  | `5dec7e1c36e8` (12) in 14Jul blob; `ec5b5e9447d3` (20) in 26Aug blob | `e7110ce5d60c` (64) | yes |
| `TELEGRAM_BOT_TOKEN`| `c960bb9d95bd` (14) in 14Jul blob (26Aug blob carries no token key) | `d5eef3d68cb3` (46) | yes |
| `OPENALGO_BASE_URL` | host `test.openalgo.com` (public test endpoint) | host `127.0.0.1` (loopback) | yes |

Both historical credential values differ from the currently deployed
values; the historical base URL pointed at a public TEST endpoint while
the live base URL is loopback. Hosts classified by locality rules only;
URL and key values are not printed anywhere in this record.

### Why gitleaks reports "no leaks" despite real blobs (blind-spot record)

Re-measured in the rev-2 audit: gitleaks 8.30.1 over the full `--all`
history (539 commits per scanner accounting) with the repo config AND
with default rules — zero findings in both JSON reports. The
`.env.test` values sit below the scanner's detection floor (test-length
tokens: 12-20 char API key, 14-char non-canonical Telegram token
spelling). Scanner-green is NOT secret-clean; the rotation ledger above
is the operative evidence. Commit-count surfaces for the record: HEAD
history is 485 commits, the full `--all` ref union is 704; the scanner
accounted 539. Rev 1's "538-commit full history" phrasing is replaced
by these measured numbers.

### filter-repo decision

Declined, unchanged. Both blobs are reachable (rev 2 correction), and
both are verified-rotated and inert, ~265 bytes combined. Running
filter-repo would rewrite ~485 main-history commits and force-push a
protected main to erase an inert, fingerprint-audited residue — an
availability risk with no security return. The decision and ledger are
recorded here; reachability itself is accepted, not "left to gc".

## Scope that CHANGED in this wave (P0-1 execution)

- Removed `docs/audit-history/tmp_checks.py` (zero-reference junk-slot
  file inside the evidence tree; F8-M-05 class).
- Added this record (+1/-1 → tracked count stays 399 = ceiling).
- Local-only stale branches now dispositioned:
  - `fix/security-yml-schedule`: superseded by 06Sep main (checkout@v7,
    gitleaks-action@v3, runner-proofed pip-audit/SBOM steps). Diff was
    a 07Sep-era attempt at the same repair with v4/v2 + steps main has
    since re-fixed past. Delete without merge.
  - `chore/main-junk-removal` / `fix/f8l04-revert-main-probes`:
    probe-artifact removals already on main (no unique commits / zero
    divergent content vs main). Delete.
  - `fix/fr7-wave`, `production-hardening`, `test-hooks`: pre-07Sep
    legacy branches, fully superseded content-wise by the merged wave
    history (fr7-wave verified ancestor of main).

## Verification state (measured 2026-09-10; rev-2 items marked)

- mypy: `mypy src/ --strict` - Success, no issues in 38 source files.
- pytest (CI-exact flags: --cov=src --cov-branch --cov-fail-under=80,
  xml+term-missing+json, junitxml): **1722 passed**, 0 failed, in
  326.7 s; total coverage **88.09%** (>= 80 gate) with branch coverage.
- Per-module coverage: all 10 floor-mapped modules meet thresholds
  (aggregate 88.1%), `check_per_module_coverage.py` rc 0.
- ruff: `check src/ tests/ scripts/` 0, `check .` 0, `format --check`
  scoped 184 files clean, root sweep 247 files clean.
- isort --check-only (src/ tests/ scripts/): clean. flake8 (src/
  tests/ scripts/): clean.
- bandit (payload gate, not exit code): HIGH 0 / MEDIUM 0 / LOW 0.
- safety 3.8.1 `check --save-json`: 129 packages scanned, 0
  vulnerabilities reported.
- pip-audit (project closure) [rev-2 re-run]: no known
  vulnerabilities, 1 ignored (PYSEC-2026-3740 nltk dev-only, ADR-0010
  waiver); JSON report at %LOCALAPPDATA%\Temp\pip-audit-10Sep-pm.json.
- gitleaks 8.30.1 [rev-2 re-run]: repo config AND default rules, `--all`
  (539 commits per scanner), zero findings in both reports.
- repo hygiene [rev-2 re-run]: working tree clean, 399 tracked = 399
  ceiling (record replaced in place; net count unchanged).
- CI green on main at 56919a7: Pipeline run 34378605315, success,
  2026-09-09T16:44Z; Security Scan run 34367934541, success, on
  a0fe342 (pre-merge head), 2026-09-09T15:05Z.
- [rev-2] Reachability cross-checked in both bash and PowerShell
  (`Select-String`/`Measure-Object` forms): 399 tracked, 0 venv
  objects, adds {2c93e15, 4c82d0f}, both ancestors of origin/main.

## Risk register delta

- RESOLVED (P0-1): reachable `.env.test` history blobs dispositioned
  (rotated, inert, documented). Rev-2 correction: the residue is TWO
  reachable blobs (not three; none unreachable) — disposition
  unchanged, evidence now topologically sound.
- RESOLVED (P0-2): F8-C-01 producer coverage — the 08Sep wave 2 landed
  the OPTIONS_FLOW 5th producer (5/7 = 0.714, single-outage redundancy
  4/7 = 0.571 ≥ 0.5) with production-side count checks (HC-15 pin,
  mutation check in TestMutationSafety) and real-producer e2e drivers.
- RESOLVED (P0-3): F8-H-03 single-engine — ADR-0005 Option B executed
  (scheduler signal jobs removed, zero Signal( sites in scheduler.py,
  enum-valid source invariant net `tests/test_signal_source_invariant
  .py` covering every src/loats Signal( site via AST + resolve_source).
- NEXT (P5 grading ~21Sep): p5_forward_test_20260907_124455.json,
  resumed run — Zerodha token re-login + market-hours window required
  before then so counters show MEASURED routing activity.
- NEXT (defense-in-depth, not required by P0): pre-push gitleaks hook
  with default-rules on the incoming diff surface (the repo-config
  allowlist intentionally excludes .env.test; a default-rules pre-push
  hook would have flagged the 14Jul/26Aug adds at push time).

### Boundary note: zero-headroom ceiling risk (standing, P1)

- Ceiling 399 = tree. Any extra staged file trips the repo-hygiene
  hook (the 09Sep post-merge staged-snapshot failure class). Future
  waves: write evidence to the Temp path, never the repo root, and
  re-pin the ceiling per the ratchet_baseline protocol when the count
  legitimately changes.
