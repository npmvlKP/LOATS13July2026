# ADR-0014: ASCII gate contract - reachable green state, then wire it

## Context

`scripts/check_src_ascii.py` was born red and stayed unwired. Its
original contract demanded byte-pure ASCII across all of `src/`, but
`src/loats/alerts.py` deliberately embeds emoji in Telegram notification
payloads - behavior pinned since 2026-07-14 by `tests/test_alerts.py`
(and `test_html_escaping_final.py`, `test_per_source_breakers.py`).
Meanwhile 13 other source files carried typographic characters in
comments, docstrings, and log strings (em-dashes, arrows, comparison
signs) - prose the same author writes as ASCII in `tests/` and
`scripts/`, where the repo's lint stack (ruff/flake8 config) enforces no
such rule and CI is green with them.

The result was a gate that could never exit 0 on the tree it guarded.
It is wired nowhere - not in `.github/workflows/ci.yml`, not in
`.pre-commit-config.yaml` - so nothing failed while 67 non-ASCII
characters accumulated. A permanently-red gate is a decorative gate:
the same erosion class F8-M-03 condemns (checks that verify idioms,
not outcomes) and the reason unwired guards rot silently. The
`TestSrcAsciiGate` suite documented the born-red state instead of
pinning a contract, because no contract was pinnable.

## Decision

1. Normalize all typographic prose characters in `src/` to ASCII
   (em-dash to `--`, arrow to `->`, `>=`/`<=` for comparison signs) -
   66 replacements across 14 files, comments/docstrings/log strings
   only; no decision logic touched. The alert emoji payloads remain
   byte-identical.
2. Narrow the gate contract to a wirable one: non-ASCII characters in
   `src/loats/*.py` fail closed EXCEPT those enumerated per file in
   `ALLOWED_NON_ASCII` (currently only `alerts.py`). The allowlist is
   justified entry-by-entry by a test asserting the exact glyph in a
   rendered payload; comments and docstrings never qualify. The green
   state is now reachable, the red direction stays proven.
3. Wire the gate on both enforcement surfaces: a step in the CI
   `repo-hygiene` job and a `src-ascii` pre-commit local hook
   (`files: ^src/.*\.py$`).
4. Re-pin the evidence: `TestSrcAsciiGate` now asserts the live tree
   passes (rc=0), a non-ASCII addition still flips rc=1, and a
   non-allowlisted character inside `alerts.py` itself fails - the
   allowlist is an enumeration, not an exemption for the whole file.
5. Bump `TRACKED_FILE_CEILING` 389 -> 390 (+1: this ADR) per the
   ADR-0009 single-source protocol.

## Consequences

* The next non-ASCII source addition fails at commit time locally and
  in the CI `repo-hygiene` job - the gate enforces instead of
  decorating.
* The gate's green state is reachable, so it can never again sit
  unwired without being an explicit decision visible in CI.
* Alert notification payloads are unchanged; their emoji remain pinned
  by the existing behavioral tests and enumerated in the allowlist.
* One tracked file added; the ratchet history in
  `scripts/ratchet_baseline.py` documents the delta.
