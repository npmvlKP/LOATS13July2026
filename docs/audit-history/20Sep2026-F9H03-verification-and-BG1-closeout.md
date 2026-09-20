# F9-H-03 — Full Verification + BG-1 Close-Out (per-entry TTL / degraded reachability)

**Date:** 2026-09-20 · **Scope:** verification of the 17Sep F9-H-03
remediation (PR #53, addd856), fresh adversarial audit, and the defect
that audit surfaced (BG-1).

## 1. Verification of the original remediation

The 15 RED-first pins (`tests/test_sentiment_f9h03_producer.py`) pass,
all four TODO-4 parts are present in code, and the settings contract
(`sentiment_liveness_max_age_minutes` / `SENTIMENT_LIVENESS_MAX_AGE_MINUTES=15.0`)
holds end to end (`check_env_settings_sync.py` 50/50). Full-tree runs:
2077 passed / 1 skipped, branch coverage 89.37% (floors gate PASSED);
FR7 health 32 PASS / 0 FAIL; HC registry 27/27; ruff / ruff-format /
isort / flake8 / mypy --strict / bandit / pip-audit / safety / gitleaks
all clean. Live RSS validation 3/3 PASS.

An independent adversarial audit (fresh subagent, static-only) returned
**CONDITIONAL_PASS** with one blocking gap.

## 2. BG-1 — CacheManager silently ignored per-entry TTL

**Root cause (verified in source):** `CacheManager.set(key, value, ttl=)`
accepted `ttl` but never used it (cache.py legacy lines 129–186). The
single `TTLCache` (cache-wide `ttl_seconds=300`, cache.py:76–79/349–356)
applies one TTL to every entry at insertion, so per-call horizons were
impossible. Consequences:

1. The sentiment LKG entry written with `ttl=LKG_TTL_SECONDS` (900 s)
   actually lived 300 s — the spec's 3x-longer LKG horizon did not exist.
2. `degraded=True` (age > LKG_TTL_SECONDS) was unreachable dead code: an
   entry retrieved from a 300 s cache can never be older than ~300 s, so
   no persisted sentiment signal could ever carry the `degraded` audit
   tag. The 15 green pins missed both because they stub `cache_manager`.

**Second defect underneath (found while fixing):** even with honored
TTLs, the original horizon choice (threshold == retention == 900 s) is
self-defeating — an entry older than its retention is evicted and can
never be served, so the tag could never fire. The reachable contract is
**freshness < degraded-threshold < retention**.

## 3. Fix (root cause, both layers)

- `src/loats/utils/cache.py`: per-TTL **tier stores**. The default-TTL
  store remains `_cache` (public contract — the suite introspects it);
  each distinct non-default TTL lazily gets its own `TTLCache` tier;
  `set` re-tiers on TTL change (stale copy evicted from the old tier);
  `get` / `get_or_set` / `delete` / `clear` / `get_cache_stats` / `close`
  span all tiers. Non-positive TTL clamps to the default.
- `src/loats/sentiment.py`: explicit horizon constants —
  `RESULT_TTL_SECONDS = 300` (freshness), `LKG_TTL_SECONDS = 900`
  (retention), **`DEGRADED_THRESHOLD_SECONDS = 600`** (degraded fires
  strictly inside the served window: fresh ≤ 300 s, silently-fresh LKG
  ≤ 600 s, `degraded=True` for 600–900 s, true cold start after 900 s).
  All cache writes now use the named constants; the degraded condition
  uses `DEGRADED_THRESHOLD_SECONDS`.

## 4. TDD evidence

- RED-first: `tests/test_cache_tiered_ttl_f9h03.py` (12 pins) — before
  the fix, exactly the 3 behavioral pins failed on the real CacheManager
  (long-entry survival past the cache-wide window, strict per-entry
  expiry, re-tiering on TTL change); the constants-contract pins failed
  at import (`RESULT_TTL_SECONDS`, `DEGRADED_THRESHOLD_SECONDS` absent).
- GREEN: 12/12 new pins; cache battery 77 passed
  (`test_cache`, `test_cache_additional`, `test_cache_concurrency`,
  `test_cache_concurrency_stress`, `test_cache_threading_issue`);
  sentiment surface 128 passed (producer pins, sentiment, coverage,
  orchestrator, orchestrator_extra).
- Three legacy `test_cache.py` set-tests asserted internals — they
  expected a `ttl=60` entry inside the default-tier `_cache`, i.e. they
  pinned the defective placement. Corrected to the public read path
  (`await cache_manager.get(...)`), which is the stronger contract;
  citation in-line (BG-1 close-out).
- Full-tree re-run after the fix: see the run stamp in the PR body for
  this wave (branch coverage ≥ 80% with floors gate PASSED).

## 5. Latent test-infra defect exposed by the fix (fixed in the same wave)

`tests/conftest.py::clear_cache_before_each_test` gated the per-test
cache clear on ``if cache_manager._cache:`` — a truthiness check that
only worked because the historical single-store cache put every entry in
``_cache``. After tiering, an entry written with a non-default TTL (the
openalgo position-book cache, ``ttl=30``) lives solely in its tier store
while ``_cache`` stays empty/falsy, so the gate skipped the clear and
cached broker responses leaked across tests
(``TestPositionBookFieldVocabulary`` polluted itself: test 2 read test
1's cached 101.25). Root cause of the *test* bug is the same as BG-1's:
assumptions about single-store internals. The gate is removed — the
clear is unconditional and ``clear()`` no-ops safely when the cache was
never initialized. A repo-wide sweep found no other consumer of the
truthiness idiom (strike_selection and sentiment article caches use
their own stores directly).

## 6. Corrections to the 17Sep resolution doc

Its claims "LKG TTL 900 s (`LKG_TTL_SECONDS`)" (line 40) and the implied
reachability of `degraded=True` were false under the then-real cache
semantics (entries expired at the cache-wide 300 s; the degraded
condition used the retention constant). This doc supersedes those two
claims; a pointer note has been added to the 17Sep document.

## 7. Deliberate behavior change (release-note material, from audit 2)

Entries written with a ttl SHORTER than the cache-wide default (the
openalgo position-book cache, ``ttl=30``, funds ``ttl=30``, quotes
``ttl=60``) previously lived the full 300 s — the ttl parameter was
ignored — and now expire at their requested horizon. This is the
spec-correct semantics and matches every call site's documented intent,
but it does produce more cache misses for these short-horizon entries in
production. No call site passed a ttl it did not intend.

## 8. Residual risk (accepted, documented)

- After ≥ 900 s without any successful sentiment computation (full cold
  start: article cache + both entries expired), the first recovery cycle
  can still time out once and self-heal in the next cycle (bounded, vs.
  the original permanent death loop). ADR-0016 territory.
- Detached refresh tasks carry no strong reference and are not
  deduplicated (benign: idempotent cache writes, contained exceptions,
  shared article cache prevents duplicate downloads).
- Liveness check remains fail-open by design (never break the cycle).

## 9. Gate remediation on the commit path (same day, this close-out)

The first full-tree gate run of this wave failed on two repo-level gates —
both repository-hygiene phenomena, neither inside the BG-1 diff:

1. **The bare-flake8 gate split persisted past 54ef203.** 54ef203 added
   `.kilo/` to `.gitignore`, which covers the git-aware surfaces (ruff
   honors `.gitignore`; the pre-commit flake8 hook passes explicit tracked
   filenames, and flake8 applies neither `.gitignore` nor `exclude` to
   those). A BARE `python -m flake8` sweep recurses untracked directories
   and flake8 honors only its own `exclude` there — and `.kilo` was not in
   it — so bare runs still reported 284 phantom findings from
   `.kilo\worktrees\burly-tilapia\` while hook and CI runs stayed green.
   Fix: `.kilo` added to the `.flake8` `exclude` block; the bare sweep now
   reports zero findings, restoring bare == hook == CI surface equivalence.
2. **Ratchet ceiling 447 -> 450.** The wave legitimately adds 3 tracked
   files (the two BG-1 pin modules + this close-out record) on top of the
   447 baseline, breaching `TRACKED_FILE_CEILING`: the repo-hygiene hook
   FAILed, F8-C-02 checks 1+10 FAILed, TODO-21 check 4 FAILed — these are
   the two ratchet-lockstep test failures in the 17:44 run of record.
   Re-pinned per the documented single-source protocol (the constant lives
   only in `scripts/ratchet_baseline.py`; the guard and both verifiers
   import it), with a dated changelog entry. Both lockstep test classes
   re-run green.

Post-fix evidence: `verify_f8c02_external.py` 12/12 PASS,
`verify_todo21_root_cleanup.py` 5/5 PASS, `check_repo_hygiene.py` PASS
(450 @ ceiling 450), bare flake8 0 findings, `pre-commit run --all-files`
17/17 PASS (mypy strict, flake8, bandit included).
