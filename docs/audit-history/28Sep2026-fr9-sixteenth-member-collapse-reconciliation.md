# 28Sep2026 — FR9 re-slice family: sixteenth member (tails-postdate-targets collapse)

## 1. Member identification

Sixteenth member of the 27Sep FR9 paste family, arriving 2026-09-28 12:04 IST
as a fresh composition (consecutive-paste diff vs the 07:50 member: disjoint,
no shared text). Three blocks:

1. Five PowerShell 5.1 failure tails whose inline comments cite the s16
   wave's OWN commands and SHAs (ratchet index check, `d0bfaf0` commit,
   `gh pr create --head docs/sep28-s16-module-table`, GraphQL protection
   read-back, `git diff 54e5306 origin/main`).
2. A 9-row Prioritized Remaining Risks table (session-composed, not archive
   text) matching the post-#100 pool state.
3. A verbatim §16 Module-by-Module Review re-slice (16 lines incl. heading)
   followed by a verbatim §15 Production Readiness Assessment repeat.

Timestamp arithmetic: the paste (12:04 IST) predates the #100 merge
(11:19:38Z = 16:49 IST) — the tails are mid-wave transcripts of commands
that were subsequently completed by other routes, not evidence of failures
in landed work.

## 2. Tail probes (parse-death class → intended operation re-proved live)

Per PS 5.1 semantics a `<placeholder>` token or bash-ism dies at PARSE time:
nothing in the line executed, so the tail proves nothing about the intended
operation. Each intended operation was re-executed or read back live:

| Tail | Parse-death cause | Intended operation, live result | Verdict |
|---|---|---|---|
| `git show :scripts/ratchet_baseline.py \| tail -1` (index verified = 500) | `tail` is a bash-ism pipe target — CommandNotFound | Ceiling read three ways: blob `TRACKED_FILE_CEILING = 500`; venv import read-back `500`; `git ls-files \| wc -l` = 500 | GREEN |
| `git commit -F <scratch>/s16_commit_msg.txt` (# d0bfaf0) | literal `<scratch>` token — parser error | `d0bfaf0` in main history: `chore(ratchet): re-pin ceiling 499->500 for the s16 module-table wave` — subject matches the cited message file's intent | GREEN |
| `gh pr create --head docs/sep28-s16-module-table` | literal `<scratch>` token — parser error | Branch merged via PR #100 (11:19:38Z) and purged: `git ls-remote --heads origin docs/sep28-s16-module-table` empty | GREEN |
| `gh api graphql ... branchProtectionRule{...}` | mangled `...` elision — `unknown shorthand flag: 'e'` | Protection read back green on EVERY contract field (approving=1, dismiss_stale=true, enforce_admins=true, strict=true, 10 contexts, force-push/deletions denied) | GREEN |
| `git diff 54e5306 origin/main -- <changed paths>` (EMPTY = content verified) | literal `<paths>` token — parser error | Diff executed for real: EMPTY output; `37d9ad7^2 == 54e5306` (trivial merge, zero content beyond the wave branch) | GREEN |

No tail indicts landed work. The stalest possible reading (tails as current
failures) is also structurally impossible: every cited target predates the
paste and is complete on the remote.

## 3. Risk-table verification (row by row, against live state)

| Row | Claim | Live evidence | Verdict |
|---|---|---|---|
| 1 | R-14 starvation, fix-shape decision, 30Sep | Register R-14 row OPEN P2-watch, due 2026-09-30; mechanism root-caused 28Sep | CONSISTENT |
| 2 | R-01 latency decision + benchmark-perf promotion, 30Sep | Register R-01 OPEN, due 2026-09-30 | CONSISTENT |
| 3 | R-13 hardening (6 occurrences), 30Sep | Register R-13 row pins SIX occurrences incl. the 28Sep midday sixth | CONSISTENT |
| 4 | R-08 bind-or-exit pre-flight, 30Sep | Register R-08 OPEN, due 2026-09-30, bind-or-exit recommended | CONSISTENT |
| 5 | Kill-switch /kill→/resume exercise inside the live span | Span live since 24Sep 08:02:08Z; `kill_switch_verified: true` in the newest snapshot = STATE verification, not the exercise; rotation-mapped log scan (coverage 25Sep 08:42Z→present) finds ZERO kill-switch events in-span — the exercise is genuinely still outstanding (operator action) | CONSISTENT |
| 6 | R-05 shared-venv rebuild, 01Oct | Register R-05 OPEN, due 2026-10-01 | CONSISTENT |
| 7 | R-12 earliest valid close 08Oct 08:02Z | Register R-12 row; span `started_at` 2026-09-24T08:02:08Z + 14 days = 08Oct 08:02Z | CONSISTENT |
| 8 | NOT-READY stands; gate chain unchanged | §15 dispositions (#96) carry over; zero code-state deltas since | CONSISTENT |
| 9 | Pool post-#100 = §1-8, §17-21, Appendix | Register paragraph from PR #100 pins exactly this pool | CONSISTENT |

## 4. Containment probe (normalized per-line)

Normalization per protocol: `*`/`_`/`|`/tabs → spaces, ordered-list markers
stripped, whitespace runs collapsed, per-LINE comparison only.

| Paste block | Lines | Contained | Archive scope |
|---|---|---|---|
| §16 Module-by-Module Review | 15 | **15/15** | 15Sep source §16 (lines 273-290); the bare heading line misses on scaffolding only (archive renders it as a `##` title) |
| §15 Production Readiness Assessment | 12 | **12/12** | 15Sep source lines 255-271 (via the #96 record's per-claim dispositions) |

The §16 half is normalization-identical to the slice the #100 record
dispositioned per-claim (8 CONFIRMED / 1 PARTIAL / 4 restored-upstream / 1
superseded). The §15 half carries the #96 dispositions. Code-state delta
`e4e110e..37d9ad7` is docs and ratchet re-pins only (PRs #97-#100), so all
dispositions carry over untouched. The NOT-READY verdict STANDS.

## 5. Operational note — `gh run list` stale pages

Post-merge CI verification hit the pinned stale-page pitfall twice in one
session: `gh run list --branch main` first served a PR-#22-era page, then an
`80c68d9`-era page; `gh run list --commit 37d9ad7` returned EMPTY. The
check-runs API at the merge SHA bypassed the stale list index: 16/16
completed, 15 success + 1 by-design skip (Docker Build on a docs merge),
`benchmark-perf` advisory included. Lesson: when both `--branch` and
`--commit` list reads disagree or come back stale/empty, go straight to
`commits/<sha>/check-runs`.

## 6. Pool arithmetic

Unre-sliced pool UNCHANGED by this member: **§1-8, §17-21, Appendix**. A
further member carrying only §13/§14/§15/§16 repeats collapses whole under
the #95-#100 chain plus this record. §17-21 remain unre-sliced: a member
carrying any of them needs fresh per-claim verdicts on arrival.
