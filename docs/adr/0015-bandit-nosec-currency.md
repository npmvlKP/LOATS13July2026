# ADR-0015: Bandit nosec currency - zero dead tokens, zero scan noise

## Context

Bandit 1.9.4 emitted, on every `src/` scan, four `nosec encountered
(B110), but no failed test` warnings against `src/loats/database.py`
(the Rule-7 rollback fallbacks at the former lines 1727/1793/1829/1855)
-- flagged cosmetic-only by the 13Sep2026 verification session and
queued for "a future no-op-scan cleanup wave".

Probe evidence before any edit:

- A bare `try/except/pass` fires B110 on bandit 1.9.4 (synthetic
  probe) -- so `# nosec B110` tokens CAN bind.
- A file-scoped scan of `database.py` reported "No issues identified"
  while still emitting the four notes -- the tokens were consuming
  real findings, but bandit's used-token accounting missed them.
- The A/B strip experiment initially "proved" the tokens inert; that
  experiment was void: its strip regex (`B1[01]1`) never matched the
  literal `B110`. The corrected experiment (run by the new
  `test_src_scan_has_zero_findings` assertion on the stripped tree)
  produced four real B110 findings -- the tokens were LOAD-BEARING.

Root cause: bandit attributes B110 to the `try:` statement line while
the token sits on the `except` line; its note is a line-attribution
quirk, not proof of a dead token. The removable debt was the noisy
`try: rollback() / except: pass` shape itself.

## Decision

1. Refactor the four Rule-7 rollback fallbacks in
   `src/loats/database.py` to `with contextlib.suppress(Exception):
   conn.rollback()` -- behaviorally identical (the outer handler
   already logs; fail-closed raises unchanged), and the B110 pattern,
   its token, and the quirk-note all cease to exist. No other `src/`
   file touched.
2. Pin the currency contract with
   `tests/test_bandit_nosec_currency.py` (3 tests, born RED with
   exactly the four note lines): zero `nosec encountered` notes on
   the `src/` scan, zero findings on the `src/` scan, and the
   proven-load-bearing `# nosec: B311` in `utils/retry.py` must stay.
3. Deliberately keep every load-bearing token: `retry.py` B311
   (probe: bare `random.uniform` fires B311), the eight remaining
   B110 tokens (`metrics.py` x6, `config/settings.py`,
   `options_math.py`; all consuming real findings, zero notes
   attributed to those files), and
   `scripts/stress_rule7_concurrency.py` B110 (A/B-verified
   load-bearing; outside CI's `src/`-scoped bandit surface).
4. Ceiling re-pin per the ADR-0009 single-source protocol, split
   across the wave's two commits: 414 -> 415 with the test net
   (commit 1), 415 -> 417 with this ADR and the wave record
   (commit 2, +2).

## Consequences

* `bandit -r src/ ...` stderr is silent: any future note fails the
  currency test and must be resolved (token removed as dead, or the
  pattern refactored, or a deliberate re-pin via this ADR's trail).
* A future bandit bump that changes B110 attribution flips the
  currency test -- the pin forces conscious re-triage, exactly like
  the safety-pin and waiver-currency monitors.
* Zero behavior change for any caller; the CI JSON-metrics gate
  contract is unchanged (findings stayed 0 throughout).
