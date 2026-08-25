# 00 - MODE ROUTER (loads first - MANDATORY DEFAULT BEHAVIOR FOR EVERY TASK)

This file binds the two engineering personas to Cline's Plan/Act modes and enforces the context-compression protocol. Slash commands `/loatsEV` and `/SEDRM` activate the same personas manually on demand.

## Mode binding (automatic - no command needed)

- **ACT mode (build / implement / fix / refactor tasks):** the FULL `loatsEV.md` persona (Principal Engineering Team Extended Version) is MANDATORY for every task. If its text is not already in context, READ `.clinerules/loatsEV.md` BEFORE acting. `/loatsEV` = manual activation/refresh.
- **PLAN mode (plan / review / audit tasks):** the FULL `SEDRM.md` persona (Senior Engineering Deep Review Mode - STRICTLY REVIEW ONLY, no file modification) is MANDATORY for every task. If not in context, READ `.clinerules/SEDRM.md` BEFORE planning. `/SEDRM` = manual activation/refresh.
- **Mode ambiguous:** wording says review/audit/plan/assess -> SEDRM; wording says implement/fix/build/refactor/optimize -> loatsEV. When still ambiguous, ASK the user which persona before proceeding.
- **FR7 build wave:** `fr7-wave-rules.md` ALSO applies to wave TODOs (execution order, HC verification, checkpoints CP-0..CP-4). At a conflict, wave checkpoints and health-check evidence requirements override persona flow; persona engineering standards override wave rules on quality matters.

## Context compression - MANDATORY after EVERY completed task (aggressive token discipline)

1. BEFORE declaring a task complete: APPEND a handoff record to `reports\handoff\handoff-log.md` (create the folder on first use; keep each record <= 40 lines): date/time | task id (TODO-n or user task label) | mode used (loatsEV/SEDRM) | files touched | verification evidence (HC ids + exit codes + test counts, or review verdicts) | commit hash if committed | open threads / deferred items | recommended next step.
2. Emit a <= 15-line closing digest in chat: what changed, what was verified, what is next. NO raw tool output, NO file contents, NO paste-dumps.
3. End the turn by telling the user exactly one line: `Task archived to handoff-log. Next: press + for a fresh task (recommended), or Condense Context if continuing.`
4. Never carry raw tool output forward - the handoff file IS the inter-task memory. A new task starts from: .clinerules + the relevant TODO cell + the latest handoff record.

## In-task token discipline (always on, both modes)

- Read only the needed cell/section of large files: SEARCH by heading (e.g. `TODO-7 (`), never whole-file reads of `23Aug2026-Seq ToDos.txt`, `23Aug2026-Consolidated FR.md`, or docs/audit-history reports.
- Prefer targeted search/grep over directory listing; NEVER dump or traverse `node_modules/`, `.opencode/`, `LOATS13July2026/` (venv), or `Lib/site-packages`.
- Summarize command output to exit code + the few decision-relevant lines; the full output stays in the terminal, not in context.
- One task = one goal. If the user's request spans multiple TODOs/modes, split and say so.
