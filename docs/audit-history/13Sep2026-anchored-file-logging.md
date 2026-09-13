# Anchored File Logging Wave — CWD-Independent logs/ (2026-09-13)

**Date:** 2026-09-13 (Asia/Calcutta). **Base:** PR #29 branch
`fix/async-audit-dual-write-pin` (commits `78aaf20`, `24825a6`, delta on
`main @ 5aecef8`). This record disposes the overnight P5 outage chain
(writer PID 28688 died 02:11 IST during a host sleep; watchdog resumes
crashed 06:17/06:18/06:23).

## Root cause (two layers)

1. **Wrapper layer (fixed out-of-repo):** `p5_resume_wrapper.cmd` ran
   python with System32 as CWD — the fresh wrapper's `cd /d "%REPO%"`
   line was missing from the resume wrapper (asymmetry introduced with
   the 12Sep restart wave's resume path). Fixed by adding the same
   `cd /d` line; the 06:33 watchdog tick then performed a real,
   span-preserving resume (writer_claimed PID 33648, restarts: 1,
   routing_enabled resumed; span → ~26 Sep gate clock PRESERVED).
2. **Source layer (this wave):** `loats_logging.configure_logging`
   created a CWD-relative `Path("logs")` and handed dictConfig a
   CWD-relative `logs/loats.log` filename. Any scheduled task / service
   whose CWD is not the repo crashes at startup with
   `PermissionError: [WinError 5] Access is denied: 'logs'`. Fixed at
   the source: `resolve_log_dir()` anchors to the repo root via
   `Path(__file__).resolve().parents[2]`, honours a `LOATS_LOG_DIR`
   env override (house `P5_RUN_LOG_DIR` pattern), and the dictConfig
   filename is now absolute.

## Contract change and net

Four tests previously pinned the DEFECT (CWD-relative `logs/`):
`test_configure_logging_production_mode`,
`test_logs_directory_created_in_production_mode`,
`test_environment_based_logging_configuration` (test_logging.py) and
`test_logging_production_mode` (test_simple_logging.py). All four now
pin CWD-independence: with a foreign CWD, no `./logs` may appear and
the file handler must write inside the anchored repo-root `logs/`
(handler `baseFilename` asserted absolute). Plus one new pin:
`test_resolve_log_dir_env_override` (override honored / cleared).

Mutation leg: reverting `resolve_log_dir()` to the CWD-relative literal
fails 4 pins (`4 failed, 7 passed`); source restored after the run.

## Sibling sweep

`logs/loats.log` and `Path("logs")` literals: no other src/scripts
consumer (the `verify_p5_forward_test.py` "logs" hit is an argparse
argument name). Existing dev-host `logs/` directory unaffected: the
anchor resolves to the same physical location.

## Ceiling-neutral pairing

+1 this record; −1 `docs/audit-history/simple_verify.py` (verified zero
references across scripts/tests/src/docs/.github before deletion).
Tree and ceiling both stay 411.
