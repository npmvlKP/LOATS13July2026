# F9-C-02 Discharge (2026-09-18): run `20260912_150243` marked **INVALID-EVIDENCE**

**Date:** 2026-09-18 (Asia/Calcutta) · **Finding:** FR9 F9-C-02 (Critical,
TODO-2) · **Status:** evidence VOID — never citable for any P5 gate ·
**Artifact of record:** `reports/p5_forward_test_20260912_150243.json`
(kept in place, unmodified; this record supplements it, it does not
replace it)

## Declaration

The P5 forward-test run log `p5_forward_test_20260912_150243.json`
(started 2026-09-12T15:02:43Z, honestly ended 2026-09-16T14:01:53Z) is
hereby marked **INVALID-EVIDENCE**. Its span overlaps the documented F9-C-02
routing-divergence contamination window: while the supervisor claimed
routing enabled, the shared audit stream accumulated **15 ROUTE rows with
`routing_enabled:false`** (2026-09-13T04:02:18Z .. 2026-09-15T02:04:58Z)
written by a second, default-OFF LOATS process — the divergence signature
that voids the span regardless of every other criterion. The 14-day gate
cannot be graded from this stream; citing it would repeat the chain's
false-readiness pattern.

## Official grader verdict (executed live, this record's session)

`scripts/verify_p5_forward_test.py reports/p5_forward_test_20260912_150243.json`
→ **rc=1** (verify_p5_forward_test exit 1), output verbatim:

```
[FAIL] p5_forward_test_20260912_150243.json: FAIL
    - data freshness: last sample 0s before end
    - ROUTING DIVERGENCE (F9-C-02): 15 ROUTE row(s) with routing_enabled:false inside the claimed-enabled span (2026-09-13T04:02:18.342000+00:00 .. 2026-09-15T02:04:58.099000+00:00) -- evidence for this run is VOID
    - span 3.96d < required 14d

P5 forward-test conformance: NOT-YET-PASSING
```

The divergence evidence (`disabled_routes_during_enabled_window`,
count 15) was folded into the artifact by the supervisor's own DB probe —
the self-verifying evidence mechanism demanded by the finding, working
against the poisoned run itself.

## Why the artifact stays in `reports/` instead of moving here

The finding suggested moving the run logs into `docs/audit-history/`;
that would (a) violate the repo hygiene rules for machine-local report
artifacts (F8-M-05 / ADR-0011: root-level `reports/*.json` are never
tracked) and (b) remove the artifact from the evidence stream the
official grader and route-watch tooling glob. Discharge is therefore
record-based: the artifact stays, this record marks it, the grader's
divergence hard-FAIL enforces the verdict on every future invocation,
and the 15Sep contamination window (`CONTAMINATION_WINDOWS`) voids any
legacy log overlapping it even if the folded field were absent.

## Evidence chain (why the divergence is Certain)

| Stamp (Z) | Supervisor claimed | Shared log / DB recorded |
| --- | --- | --- |
| 09-15 01:52:55 | `routing_enabled` event | `Enabled Analyzer routing` 01:52:55.934 |
| 09-15 02:04:58 | (no disable event) | ROUTE row `analyzer_routing_disabled`, `routing_enabled:false`; `Analyzer routing disabled for decision …` 02:04:58.002 |
| 09-15 04:14:19 | `routing_enabled` event (resume) | counters still 0/0/0 |

Counters 0/0/0 across 570 in-log cycles vs 15 DB ROUTE rows and `:8001`
816 cycles — impossible for one process, deterministic for two. Root
cause and full remediation: `docs/audit-history/15Sep2026-F9C02-TODO2-resolution.md`.

## Disposition

- **Superseded by:** `p5_forward_test_20260916_140341.json` — the fresh
  14-day span started 2026-09-16T14:03:41Z under the runbook
  (`docs/audit-history/16Sep2026-p5-restart-execution.md`), graded by the
  post-F9-C-02 verifier.
- **Citation rule:** this run log must never appear as supporting
  evidence in any P5, CMP, or readiness artifact; any citation is a
  finding-worthy violation.

## Closure wave (2026-09-18, same record)

The finding's two remaining open items are closed in this wave and pinned
by `tests/test_p5_f9c02_kill_switch_and_archive.py` (16 pins, RED-first
proven: 13 failed before the fix for the right reasons — probe absent,
fields absent, verdicts PASS-instead-of-FAIL, record absent):

1. **Kill-switch verification event (finding item 6, CMP P5 gate).**
   `scripts/run_p5_forward_test.py` now probes
   `alerts.is_kill_switch_active()` once at supervision start (fresh,
   resumed, AND dry-run) via `_probe_kill_switch()` and
   `_record_kill_switch_verification()`, stamping
   `kill_switch_verified` / `kill_switch_active_at_start` and a
   `kill_switch_verified` (or `kill_switch_alarm`) run-log event.
   `scripts/verify_p5_forward_test.py` grades the proof fail-closed via
   `_grade_kill_switch_evidence`: an ENDED run without disengagement
   proof hard-FAILs; an engaged switch FAILs even when verified; an
   ongoing run carries the gap as a visible reason (INCOMPLETE). No
   legacy grace — `routing.enabled_at_start` has none either; gate
   evidence standards are current, not historical. Enforcement surface
   (already landed, unchanged): `_check_kill_switch` /
   `_async_check_kill_switch` raise `KillSwitchError` on BOTH order
   paths (sync + async) and audit a `BLOCK` row — the `/kill` Telegram
   command activates the same singleton (`alerts.py`), and the finding's
   "blocks the next order and is logged" contract is pinned by
   `tests/test_openalgo.py` + `tests/test_kill_switch_simple.py`.
2. **INVALID-EVIDENCE archival (finding item 1, deferred 15Sep as
   operator action).** Discharged by this record: the artifact stays in
   `reports/` (hygiene rules for machine-local artifacts; the grader and
   route-watch glob the evidence stream), the dated record marks it, and
   the official grader's rc=1 divergence hard-FAIL re-proven in-suite
   enforces the verdict on every future invocation.

Live reconciliation at wave time: DB ROUTE rows since the 16Sep span
start = **628, all `routing_enabled:true`, zero disabled** — exactly
matching the live run-log counters (success 628 / disabled 0 / divergence
0). The F9-C-02 signature (counters vs DB contradiction) is closed on the
live system; the resumed supervisor stamps the kill-switch proof on its
next resume, completing the 30Sep-gradeable shape.
