# ADR-0013: Self-healing shebang executable-bit normalizer

## Context

Git records the POSIX executable bit in the index, but the Windows
filesystem has no such concept — `git update-index --chmod=+x` is the
only way a Windows host can produce a 100755 entry. When a shebang'd
script is committed from Windows without that step (as happened to
`scripts/verify_f8m02_m07_external.py` in this wave, fixed by db5957b),
local pre-commit passes — Windows ruff suppresses EXE001 — and the two
Linux CI ruff jobs fail with
`EXE001 Shebang is present but file is not executable`. This is a
recurrence of the platform-gap class documented in ADR-0012; process
memory ("remember to chmod") has now failed twice.

## Decision

1. Add `scripts/ensure_shebang_exec_bit.py` and wire it as a pre-commit
   local hook (`shebang-exec-bit`, `types: [python]`,
   `pass_filenames: true`). For every staged `*.py` whose index mode is
   100644 while its content starts with `#!`, flip the mode to 100755
   via `git update-index --chmod=+x` and exit 0. The hook is
   self-healing rather than blocking: it cannot run on Linux-ci-only
   knowledge, and blocking would merely move CI's failure earlier
   without fixing the root cause. Run with no arguments it normalizes
   the whole tracked Python tree, so it doubles as a manual repair
   entry point. The CI EXE001 gate remains the hard verifier of record.
2. Pin the live-tree invariant in `tests/test_repo_hygiene.py`
   (TestShebangExecBit): every tracked Python file with a shebang must
   sit at index mode 100755, with an end-to-end mutation proof in a
   temporary git repository (100644+shebang flips, no-shebang and
   100755 files untouched).
3. Re-pin `TRACKED_FILE_CEILING` 384 → 386 (+2: this script and the
   ADR) per the ADR-0009 single-source protocol.
4. Record the decision in this ADR; the wiring guard's liveness is
   seeded by the test citation.

## Consequences

* New shebang'd scripts committed from Windows can no longer reach CI
  at 100644 — the commit itself is repaired at hook time.
* The hook is a no-op on hosts that already record exec bits
  (Linux/macOS) and for scripts without shebangs; existing local hooks
  and CI semantics are unchanged.
* One tracked file added; the ratchet history in
  `scripts/ratchet_baseline.py` documents the delta.
