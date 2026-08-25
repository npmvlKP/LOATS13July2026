# LOATS13July2026 — Agent Rules

## Mode-Routed Mandatory Behaviour (every task, every session)

Two operating modes. Both are DEFAULT MANDATORY — apply automatically per current mode, invocation NOT required:

| Mode | opencode agent | Behaviour file (source of truth) | Manual activation |
|---|---|---|---|
| ACT/BUILD (implement, fix, refactor, optimize, test, gates) | build | `G:\.OA\LOATS-13July2026\loats-EV.txt` | `/loatsEV` |
| PLAN/REVIEW (forensic review, audit, planning, findings) | plan | `G:\.OA\LOATS-13July2026\SrErDRMode.txt` | `/SEDRM` |

Rules:
1. Task start: read the behaviour file for the active mode (do not rely on memory of it) and obey it for the entire task.
   - ACT/BUILD → LOATS-EV: Principal Engineering Team persona, repository-evidence-only, zero assumptions/placeholders, root-cause fixes, full quality gates, no git add/commit/push until all validation passes, final report with PowerShell execution evidence.
   - PLAN/REVIEW → SEDRM: Senior Engineering Review Board persona, STRICTLY REVIEW ONLY — no file modifications, no patches, no refactors; every finding carries Issue ID/Category/Severity/Confidence/Evidence/Root Cause/Risk/Resolution; state "Not enough evidence." rather than speculate; report in the mandated 21-section order.
2. Mixed task: any repo edit = ACT/BUILD rules govern the edit portion; review findings preceding it follow SEDRM.
3. `/loatsEV` and `/SEDRM` are explicit re-activations/refreshers of the same mandatory behaviour, not opt-ins.

## Mandatory Post-Task Context Compression (every task)

After completing each task (and after each major sub-task / checkpoint):
- Perform aggressive, meaningful context compression: run `ctx_reduce` marking every spent tool output as discardable — file reads already acted on, search results already used, build/test output already analyzed, intermediate diagnostics no longer needed.
- Keep only: user messages, active requirements/constraints, unresolved errors, files under active edit.
- Meaningful compression only — never drop a user directive or unresolved error. Never skip; compression is part of task completion.
