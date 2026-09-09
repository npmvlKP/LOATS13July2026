#!/usr/bin/env python3
"""P5 forward-test supervisor (F8-H-01).

Runs the real LOATS trading system (``loats.main`` TradingSystem) with
Analyzer routing ENABLED for the CMP P5 2-week forward test, appending
heartbeat run-log records to ``reports/p5_forward_test_<ts>.json`` so
``scripts/verify_p5_forward_test.py`` can grade conformance.

F8-H-01 closing step: the CMP P5 gate requires routing ALL TradeDecisions
to Analyzer mode. This supervisor enables routing ONLY for the duration
of the supervised run — the production default stays OFF (runtime kill
path preserved), per ADR-006.

Safety:
- Requires an explicit operator acknowledgement that a live OpenAlgo
  endpoint is reachable (``--ack-live-endpoint``) or runs with
  ``--dry-run`` (enables routing in-process, issues no HTTP because the
  orchestrator cycle is not started).
- The kill switch (settings + DB) remains active throughout.

Usage:
    python scripts/run_p5_forward_test.py --dry-run          # smoke
    python scripts/run_p5_forward_test.py --ack-live-endpoint  # real run
    python scripts/run_p5_forward_test.py --status            # inspect log
"""

from __future__ import annotations

import argparse
import asyncio
import datetime
import importlib.util
import json
import os
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

# F8-H-01 (2026-09-07): run logs must be writable OUTSIDE the repo tree so
# test/CI invocations of this supervisor never drop smoke stubs into the
# production evidence directory (≈200 stub logs accumulated there from
# suite runs). The default stays the real reports/ for operator runs;
# tests set P5_RUN_LOG_DIR to a private temp dir.
RUN_LOG_DIR = Path(os.environ.get("P5_RUN_LOG_DIR") or (REPO_ROOT / "reports"))
RUN_LOG_GLOB = "p5_forward_test_*.json"
MIN_SPAN_DAYS = 14
# Live-activity sampling cadence for supervised runs: fold real system
# counters into the run log every 60 s so graded evidence is measured,
# never estimated.
_SAMPLE_INTERVAL_S = 60.0

# ``--status`` honesty threshold: a live-shape log whose last sample is
# older than this is almost certainly an abandoned run (the supervised
# loop samples every _SAMPLE_INTERVAL_S). Status still reports the log,
# but flags the staleness instead of implying the run is accumulating.
_STALE_WARN_S = 600.0

PASS_SYM, FAIL_SYM = "[PASS]", "[FAIL]"


def _load_validator() -> Any | None:
    """Import ``scripts/verify_p5_forward_test.py`` as a module.

    The P5 gate definition lives in one place (the validator's
    ``grade_run_log``); the supervisor reuses it so gate-pass detection
    during a live run can never drift from the official grader.
    """
    cache = getattr(_load_validator, "_module", None)
    if cache is not None:
        return cache
    validator = REPO_ROOT / "scripts" / "verify_p5_forward_test.py"
    spec = importlib.util.spec_from_file_location("p5_forward_validator", validator)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    _load_validator._module = module  # type: ignore[attr-defined]
    return module


def _grade_current_run(run_log: Path, pretend_ended: bool = False) -> Any | None:
    """Grade the current run-log state; returns a Grade or None.

    With ``pretend_ended=True`` the grade answers "would this run clear the
    gate if it ended now?" — used by the supervisor's gate-stop check, since
    the on-disk log stays ``ended_at: null`` (ongoing) until shutdown.
    """
    validator = _load_validator()
    if validator is None:
        return None
    try:
        data = json.loads(run_log.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if pretend_ended and data.get("ended_at") is None:
        data["ended_at"] = _utcnow_iso()
    return validator.grade_run_log(data)


def _utcnow_iso() -> str:
    return datetime.datetime.now(datetime.UTC).isoformat()


def _find_run_log(path: Path | None) -> Path | None:
    """Return the given path or the default-selection run log.

    Default selection is delegated to the validator's
    ``select_default_run_log`` (single source of policy): the live
    evidence run wins over newer smoke-test stubs, so ``--status`` cannot
    mis-grade a dry-run stub while the supervised run is ongoing — the
    mis-gradation observed live 2026-09-05 (stub 170809 shadowed the
    resumed 063556 evidence run).
    """
    if path is not None:
        return path if path.exists() else None
    validator = _load_validator()
    if validator is None:
        raise RuntimeError(
            "P5 validator (scripts/verify_p5_forward_test.py) failed to load; "
            "cannot select the default run log"
        )
    # select_default_run_log is loaded dynamically (Any); the annotation
    # documents the declared contract. Note: the repo mypy config excludes
    # scripts/, so this file is checked only in default (non-strict) mode.
    selected: Path | None = validator.select_default_run_log(RUN_LOG_DIR)
    return selected


def _init_run_log(reason: str, dry_run: bool) -> Path:
    """Create a fresh run-log file with the run's initial state."""
    RUN_LOG_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.datetime.now(datetime.UTC).strftime("%Y%m%d_%H%M%S")
    path = RUN_LOG_DIR / f"p5_forward_test_{stamp}.json"
    record: dict[str, Any] = {
        "metadata": {
            "phase_gate": "P5",
            "finding": "F8-H-01",
            "reason": reason,
            "dry_run": dry_run,
            "script": "scripts/run_p5_forward_test.py",
        },
        "routing": {
            "enabled_at_start": True,  # supervisor always enables routing
            "env_flag_default": False,
            "note": (
                "production default remains OFF (ADR-006); routing enabled "
                "only for the supervised P5 run via enable_analyzer_routing()"
            ),
        },
        "started_at": _utcnow_iso(),
        "ended_at": None,
        "unhandled_exceptions": 0,
        "restarts": 0,
        # Single-writer guard (2026-09-08): the PID of the supervisor
        # process currently sampling this log, plus that process's
        # creation time -- the pair makes a recycled PID detectable (a
        # recycled PID matching by image alone would permanently block
        # takeover of an in-span run). Claim enforced by an OS-level lock
        # on the <log>.claim sidecar; both JSON fields are human/status
        # evidence, not the serialization point.
        "supervisor_pid": None,
        "supervisor_started_at": None,
        "resume_refusal": None,
        # cycles_completed/counters are LIVE samples (orchestrator cycle
        # count, TradeDecisionEngine routing outcomes) folded in by the
        # supervised loop — never estimates. Baselines are captured at run
        # start so the deltas measure only this run's activity.
        "cycles_completed": 0,
        "cycles_completed_baseline": None,
        "counters": {"success": 0, "disabled": 0, "error": 0},
        "counters_baseline": None,
        "events": [],
    }
    path.write_text(json.dumps(record, indent=2), encoding="utf-8")
    return path


def _update_run_log(path: Path, mutate: dict[str, Any]) -> None:
    """Atomically merge ``mutate`` into the run log JSON."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        data = {}
    data.update(mutate)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _append_event(path: Path, kind: str, detail: str) -> None:
    """Append a timestamped event to the run log."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    events = data.setdefault("events", [])
    events.append({"timestamp": _utcnow_iso(), "kind": kind, "detail": detail})
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _capture_live_baseline(system: Any) -> dict[str, Any]:
    """Read the live counter baselines before the supervised window starts.

    Deltas against these baselines measure only THIS run's activity; the
    process may have been importing/initializing long before started_at.
    """
    from loats.orchestrator import orchestrator
    from loats.trade_decision import trade_decision_engine

    return {
        "cycles_completed": orchestrator.cycle_count,
        "counters": trade_decision_engine.get_routing_stats(),
    }


def _effective_resume_baseline(
    raw: dict[str, Any], logged_cycles: int, logged_counters: dict[str, int]
) -> dict[str, Any]:
    """Shift a fresh process's live counters so a resumed run log continues
    from where the previous process's last sample left off.

    Per key: baseline = max(live_now - logged, 0). When live >= logged the
    log continues seamlessly (deltas keep accumulating); when a counter
    RESET happened across the restart (live < logged) the baseline floors
    at the live value, so only post-resume activity is counted — a drop in
    the log, never inflation.
    """
    live_counters = raw["counters"]
    return {
        "cycles_completed": max(int(raw["cycles_completed"]) - int(logged_cycles), 0),
        "counters": {
            key: max(
                int(live_counters.get(key, 0)) - int(logged_counters.get(key, 0)),
                0,
            )
            for key in ("success", "disabled", "error")
        },
    }


def _process_image_path(pid: int) -> str:
    """Return the full image path of ``pid`` (best effort, stdlib only).

    - Windows: OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION) +
      QueryFullProcessImageNameW.
    - POSIX: ``/proc/<pid>/exe`` (a ``(deleted)`` suffix is stripped).
    - Returns ``_PROCESS_IMAGE_UNREADABLE`` when the process exists but its
      image cannot be read (protected process, no /proc) — a live process
      must never be mistaken for a free PID, so unreadable is distinct from
      nonexistent.
    - Returns ``""`` only when the PID does not exist (free).
    """
    if pid <= 0:
        return ""
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        ERROR_INVALID_PARAMETER = 87
        ERROR_NOT_FOUND = 1168
        kernel32 = ctypes.WinDLL("kernel32.dll", use_last_error=True)
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.OpenProcess.argtypes = [
            wintypes.DWORD,
            wintypes.BOOL,
            wintypes.DWORD,
        ]
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            err = ctypes.get_last_error()
            if err in (ERROR_INVALID_PARAMETER, ERROR_NOT_FOUND):
                return ""  # PID free
            return _PROCESS_IMAGE_UNREADABLE
        try:
            size = wintypes.DWORD(1024)
            buf = ctypes.create_unicode_buffer(size.value)
            if not kernel32.QueryFullProcessImageNameW(
                handle, 0, buf, ctypes.byref(size)
            ):
                return _PROCESS_IMAGE_UNREADABLE
            return buf.value
        finally:
            kernel32.CloseHandle(handle)
    # POSIX fallback: /proc/<pid>/exe is the image path.
    try:
        link = str(Path(f"/proc/{pid}/exe").readlink())
        return link.removesuffix(" (deleted)")
    except FileNotFoundError:
        return ""  # PID free
    except OSError:
        return _PROCESS_IMAGE_UNREADABLE


_PROCESS_IMAGE_UNREADABLE = "<unreadable>"


def _current_process_image() -> str:
    """This process's REAL executable image (venv-launcher safe).

    ``sys.executable`` names the interpreter as invoked (e.g.
    ``loatsNEW\\Scripts\\python.exe``), but a Windows venv ``python.exe``
    is a launcher whose PROCESS IMAGE is the base interpreter (here
    ``C:\\Program Files\\Python312\\python.exe``) — the same image
    QueryFullProcessImageNameW returns for every live writer. Comparing
    against ``sys.executable`` misclassifies all live writers as dead: a
    fail-open bug in a single-writer guard. Empirically on this host the
    current-process pseudo-handle is REJECTED by QueryFullProcessImageNameW
    (error 6), so the reliable route is OpenProcess on our own PID.
    """
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32.dll", use_last_error=True)
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.OpenProcess.argtypes = [
            wintypes.DWORD,
            wintypes.BOOL,
            wintypes.DWORD,
        ]
        # 1) OpenProcess on our own PID (verified reliable on this host).
        handle = kernel32.OpenProcess(0x1000, False, os.getpid())
        if handle:
            try:
                size = wintypes.DWORD(1024)
                buf = ctypes.create_unicode_buffer(size.value)
                if kernel32.QueryFullProcessImageNameW(
                    handle, 0, buf, ctypes.byref(size)
                ):
                    return buf.value
            finally:
                kernel32.CloseHandle(handle)
        # 2) Current-process pseudo-handle (works on most builds).
        size = wintypes.DWORD(1024)
        buf = ctypes.create_unicode_buffer(size.value)
        if kernel32.QueryFullProcessImageNameW(
            kernel32.GetCurrentProcess(), 0, buf, ctypes.byref(size)
        ):
            return buf.value
    return str(Path(sys.executable).resolve())  # last-resort fallback


_CURRENT_IMAGE_NORMCASE = os.path.normcase(_current_process_image())


def _process_creation_time(pid: int) -> str | None:
    """The process's creation time as an ISO-8601 UTC string, or None.

    Windows: OpenProcess + GetProcessTimes. POSIX: field 22 of
    /proc/<pid>/stat (clock ticks since boot; both sides of a comparison
    run on the same host, so raw ticks are a valid identity).

    None means "could not determine" — the caller decides (claim writers
    record None; liveness checks treat a recorded value with an unreadable
    live process as fail-closed).
    """
    if pid <= 0:
        return None
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32.dll", use_last_error=True)
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.OpenProcess.argtypes = [
            wintypes.DWORD,
            wintypes.BOOL,
            wintypes.DWORD,
        ]
        handle = kernel32.OpenProcess(0x1000, False, pid)
        if not handle:
            return None
        try:
            creation = wintypes.FILETIME()
            exit_ft = wintypes.FILETIME()
            kernel = wintypes.FILETIME()
            user = wintypes.FILETIME()
            if not kernel32.GetProcessTimes(
                handle,
                ctypes.byref(creation),
                ctypes.byref(exit_ft),
                ctypes.byref(kernel),
                ctypes.byref(user),
            ):
                return None
            ft = (creation.dwHighDateTime << 32) | creation.dwLowDateTime
            # FILETIME epoch 1601-01-01 → Unix epoch seconds.
            seconds = (ft - 116444736000000000) / 10_000_000
            return datetime.datetime.fromtimestamp(seconds, tz=datetime.UTC).isoformat()
        finally:
            kernel32.CloseHandle(handle)
    try:
        stat = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
    except OSError:
        return None
    # Field 22 (1-based) sits after the comm field, which may contain
    # spaces/parentheses — split from the last ')'.
    try:
        after_comm = stat.rsplit(")", 1)[1].split()
        return str(int(after_comm[19]))  # field 22 overall
    except (IndexError, ValueError):
        return None


def _same_instant(a: str | None, b: str | None) -> bool:
    """Compare two creation-time stamps for equality (tolerant).

    Returns False when either side is None/unparseable — an identity that
    cannot be proven equal must not be treated as a match.
    """
    if not a or not b:
        return False
    if a == b:
        return True
    try:
        da = datetime.datetime.fromisoformat(a)
        db = datetime.datetime.fromisoformat(b)
    except ValueError:
        return False
    if da.tzinfo is None:
        da = da.replace(tzinfo=datetime.UTC)
    if db.tzinfo is None:
        db = db.replace(tzinfo=datetime.UTC)
    return da == db


class _WriterClaim:
    """An OS-level exclusive claim on a run log, held for the writer's
    lifetime.

    msvcrt.locking (Windows) / fcntl.flock (POSIX) on a ``<log>.claim``
    sidecar. The kernel releases the lock when the process dies — a hard
    kill cannot orphan a claim — which is what makes this deterministic
    where the JSON read-modify-write was not (adversarial review
    2026-09-08, blocking finding 2).
    """

    def __init__(self, run_log: Path):
        self.run_log = run_log
        self.sidecar = run_log.with_suffix(run_log.suffix + ".claim")
        self._fh: Any = None
        self.acquired = False
        self._acquire()

    def _acquire(self) -> None:
        self._fh = open(self.sidecar, "a+b")
        try:
            if os.name == "nt":
                import msvcrt

                self._fh.seek(0)
                msvcrt.locking(self._fh.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl  # POSIX-only; no stubs on Windows

                fcntl.flock(  # type: ignore[attr-defined]
                    self._fh.fileno(),
                    fcntl.LOCK_EX | fcntl.LOCK_NB,  # type: ignore[attr-defined]
                )
            self.acquired = True
        except OSError:
            self.close()

    def close(self) -> None:
        if self._fh is not None:
            try:
                if self.acquired and os.name == "nt":
                    import msvcrt

                    self._fh.seek(0)
                    msvcrt.locking(self._fh.fileno(), msvcrt.LK_UNLCK, 1)
            except OSError:
                pass  # lock dies with the handle anyway
            finally:
                try:
                    self._fh.close()
                except OSError:
                    pass
                self._fh = None
                self.acquired = False

    def release(self) -> None:
        self.close()


_ACTIVE_CLAIM: _WriterClaim | None = None


def _pid_alive_running_supervisor(
    pid: int | None, started_at: str | None = None
) -> bool:
    """True iff (pid, creation time) identifies a live writer process.

    Identity is the process creation time bound at claim time, not the PID
    alone: on this gate host ~19 unrelated processes share the supervisor's
    interpreter image, so a recycled PID that merely matches by image would
    PERMANENTLY BLOCK takeover of an in-span evidence run (adversarial
    review 2026-09-08, blocking finding 1). A live same-image process whose
    creation time differs from the recorded one is a recycler — dead.

    A recorded PID with no creation-time stamp (pre-identity log) falls
    back to image matching, and an unreadable-but-alive PID still fails
    closed. ``pid == os.getpid()`` is trivially this supervisor.
    """
    if pid is None:
        return False
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        # Corrupt log field: treat as no writer rather than crash the
        # resolver/status path (grade_run_log applies the same tolerance).
        return False
    if pid <= 0:
        return False
    if pid == os.getpid():
        return True
    image = _process_image_path(pid)
    if image == "":
        return False  # PID free
    if image == _PROCESS_IMAGE_UNREADABLE:
        return True  # fail closed: assume a live writer we cannot inspect
    if os.path.normcase(Path(image).resolve()) != _CURRENT_IMAGE_NORMCASE:
        return False  # recycled by a different binary
    if not started_at:
        # Pre-identity log: image match is the best available evidence.
        return True
    created = _process_creation_time(pid)
    if created is None:
        return True  # fail closed: alive but uninspectable
    return _same_instant(created, started_at)


def _claim_run_log(
    run_log: Path,
    refusal: str | None = None,
    identity: tuple[int, str | None] | None = None,
) -> bool:
    """Claim writer-ship of an ongoing run log.

    Mutual exclusion is an OS-level exclusive lock on a ``<log>.claim``
    sidecar held for the writer's lifetime (the kernel releases it when the
    process dies, so a hard kill cannot orphan a claim). The JSON record
    (``supervisor_pid`` + ``supervisor_started_at``) is for humans and the
    ``--status`` view, and doubles as the recycled-PID detector — NOT as
    the serialization point: a JSON read-modify-write cannot close the
    claim race (adversarial review 2026-09-08, blocking finding 2).

    Succeeds when the lock is acquired AND the recorded writer identity is
    absent, dead, or this process itself (self re-claim — refreshes the
    record and clears a stale ``resume_refusal``). A live recorded writer
    or a foreign-held lock makes the claim fail and persists ``refusal``
    into ``resume_refusal`` for operators.

    ``identity`` overrides this process's own (pid, creation-time) for
    tests; the creation-time half is what makes a recycled PID detectable
    (blocking finding 1).
    """
    global _ACTIVE_CLAIM
    if identity is None:
        identity = (os.getpid(), _process_creation_time(os.getpid()))
    my_pid, my_created = identity

    new_claim: _WriterClaim | None = None
    held_here = (
        _ACTIVE_CLAIM is not None
        and _ACTIVE_CLAIM.acquired
        and _ACTIVE_CLAIM.run_log == run_log
    )
    if not held_here:
        new_claim = _WriterClaim(run_log)
        if not new_claim.acquired:
            # A live writer's kernel lock is why we lost — exactly the
            # single-writer guarantee, enforced by the OS.
            if refusal:
                _update_run_log(run_log, {"resume_refusal": refusal})
            new_claim.close()
            return False

    promoted = False
    try:
        try:
            data = json.loads(run_log.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return False
        if not isinstance(data, dict) or data.get("ended_at") is not None:
            return False
        recorded_pid = data.get("supervisor_pid")
        recorded_created = data.get("supervisor_started_at")
        if recorded_pid is not None:
            try:
                recorded_int = int(recorded_pid)
            except (TypeError, ValueError):
                recorded_int = 0  # corrupt field: no live writer provable
            self_reclaim = recorded_int == my_pid and refusal is None
            if not self_reclaim and _pid_alive_running_supervisor(
                recorded_int, recorded_created
            ):
                if refusal:
                    _update_run_log(run_log, {"resume_refusal": refusal})
                return False
        _update_run_log(
            run_log,
            {
                "supervisor_pid": my_pid,
                "supervisor_started_at": my_created,
                "resume_refusal": None,
            },
        )
        promoted = True
    finally:
        # Promote the lock to the process-level claim on success; drop it
        # on every refusal path so we never hold a lock without owning the
        # recorded claim.
        if new_claim is not None:
            if promoted:
                if _ACTIVE_CLAIM is not None:
                    _ACTIVE_CLAIM.close()
                _ACTIVE_CLAIM = new_claim
            else:
                new_claim.close()
            new_claim = None
    return True


def _release_run_log(run_log: Path) -> None:
    """Release this supervisor's claim on exit.

    Identity-scoped: only a claim recorded by THIS pid (or an unrecorded /
    corrupt record) is cleared — a successor's claim is never touched.
    Never touches ``ended_at``: releasing a claim must not resurrect an
    ended run (grading reads ``ended_at``, not the claim).
    """
    global _ACTIVE_CLAIM
    try:
        data = json.loads(run_log.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        data = None
    if isinstance(data, dict):
        recorded = data.get("supervisor_pid")
        if recorded is not None:
            try:
                mine = int(recorded) == os.getpid()
            except (TypeError, ValueError):
                mine = False
            if not mine:
                return  # a successor's claim: not ours to clear
        _update_run_log(run_log, {"supervisor_pid": None})
    if _ACTIVE_CLAIM is not None and _ACTIVE_CLAIM.run_log == run_log:
        _ACTIVE_CLAIM.release()
        _ACTIVE_CLAIM = None


def _resolve_resume_target(path: Path | None) -> Path | None:
    """Validate an explicit resume target, or find the newest eligible one.

    Eligible = structurally readable run log, dry_run false, still ongoing
    (``ended_at`` null), AND not held by a live supervisor process (the
    single-writer guard: resuming a log another live process is sampling
    would fold interleaved counter baselines into one run log). Prints the
    reason and returns None when nothing is resumable — resuming a dry-run,
    an ended run, or an actively-supervised run would fabricate or corrupt
    evidence.
    """
    candidates: list[Path]
    if path is not None:
        candidates = [path]
    else:
        candidates = sorted(
            RUN_LOG_DIR.glob(RUN_LOG_GLOB),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
    for candidate in candidates:
        if not candidate.exists():
            if path is not None:
                print(
                    f"{FAIL_SYM} resume target not found: {candidate}", file=sys.stderr
                )
                return None
            continue
        try:
            data = json.loads(candidate.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            if path is not None:
                print(
                    f"{FAIL_SYM} resume target unreadable: {candidate}", file=sys.stderr
                )
                return None
            continue
        metadata = data.get("metadata") or {}
        if metadata.get("dry_run"):
            if path is not None:
                print(
                    f"{FAIL_SYM} {candidate.name}: dry-run log — nothing to resume",
                    file=sys.stderr,
                )
                return None
            continue
        if data.get("ended_at") is not None:
            if path is not None:
                print(
                    f"{FAIL_SYM} {candidate.name}: run already ended — "
                    "start a new run instead",
                    file=sys.stderr,
                )
                return None
            continue
        # Single-writer guard: a live supervisor process already sampling
        # this log makes a second writer a counter-corruption hazard.
        if _pid_alive_running_supervisor(
            data.get("supervisor_pid"), data.get("supervisor_started_at")
        ):
            print(
                f"{FAIL_SYM} {candidate.name}: live supervisor "
                f"(PID {data.get('supervisor_pid')}) holds this run log — "
                "refusing to resume (single-writer guard)",
                file=sys.stderr,
            )
            if path is not None:
                _update_run_log(
                    candidate,
                    {
                        "resume_refusal": (
                            "resume refused: live writer PID "
                            f"{data.get('supervisor_pid')} holds this log "
                            "(single-writer guard)"
                        )
                    },
                )
                return None
            continue
        return candidate
    if path is None:
        print(
            f"{FAIL_SYM} no resumable run log (dry_run=false, ended_at=null) "
            f"under {RUN_LOG_DIR}",
            file=sys.stderr,
        )
    return None


def _sample_live_activity(system: Any, run_log: Path, baseline: dict[str, Any]) -> None:
    """Fold live system counters into the run log (deltas over baseline).

    Sources (read-only, never fabricated):
    - ``orchestrator.cycle_count``  → ``cycles_completed`` delta
    - ``trade_decision_engine.get_routing_stats()`` → ``counters`` delta
    - ``system.running`` / kill switch state → ``system_healthy`` sample
    """
    from loats.alerts import alerts
    from loats.orchestrator import orchestrator
    from loats.trade_decision import trade_decision_engine

    live_cycles = max(0, orchestrator.cycle_count - baseline["cycles_completed"])
    live_counters = trade_decision_engine.get_routing_stats()
    base_counters = baseline["counters"]
    deltas = {
        key: max(0, int(live_counters.get(key, 0)) - int(base_counters.get(key, 0)))
        for key in ("success", "disabled", "error")
    }
    _update_run_log(
        run_log,
        {
            "cycles_completed": live_cycles,
            "counters": deltas,
            "last_sampled_at": _utcnow_iso(),
            "system_healthy": {
                "system_running": bool(system.running),
                "kill_switch_active": alerts.is_kill_switch_active(),
            },
        },
    )


async def _supervise_live(
    system: Any,
    run_log: Path,
    baseline: dict[str, Any],
    duration: float | None,
    task: asyncio.Task[None] | None,
) -> int:
    """Sample live activity until the duration expires, the system task
    ends, or the P5 gate (per the official validator) is satisfied.

    Returns the number of unhandled exceptions observed while supervising.
    """
    loop = asyncio.get_running_loop()
    deadline = loop.time() + duration if duration is not None else None
    unhandled = 0
    while True:
        _sample_live_activity(system, run_log, baseline)
        grade = _grade_current_run(run_log, pretend_ended=True)
        if grade is not None and grade.verdict == "PASS":
            _append_event(
                run_log,
                "gate_pass_detected",
                "verify_p5_forward_test.grade_run_log verdict=PASS "
                f"(span >= {MIN_SPAN_DAYS}d, 0 exceptions, routing enabled)",
            )
            print(
                f"{PASS_SYM} P5 gate satisfied (>= {MIN_SPAN_DAYS}d span, "
                "0 exceptions, routing enabled); ending supervised run"
            )
            break
        now = loop.time()
        if deadline is not None and now >= deadline:
            break
        if task is not None and task.done():
            if not task.cancelled() and task.exception() is not None:
                exc = task.exception()
                unhandled += 1
                _append_event(
                    run_log,
                    "unhandled_exception",
                    f"system task ended: {type(exc).__name__}: {exc}",
                )
                print(f"{FAIL_SYM} system task ended: {exc}", file=sys.stderr)
            break
        delay = _SAMPLE_INTERVAL_S
        if deadline is not None:
            delay = min(delay, max(0.0, deadline - now))
        if task is not None:
            # Wake on whichever comes first: the sample interval or the
            # system task completing. asyncio.wait never cancels ``task``.
            await asyncio.wait({task}, timeout=delay)
        else:
            await asyncio.sleep(delay)
    return unhandled


async def _run(
    dry_run: bool, reason: str, duration: float | None, resume_log: Path | None = None
) -> int:
    """Supervise one P5 forward-test run with routing enabled.

    With ``resume_log`` set, continue that ongoing run log in this fresh
    process instead of starting a new one — the 14-day span must survive
    host restarts. Counter continuity is guaranteed by
    ``_effective_resume_baseline`` (continues seamlessly, never inflates).
    """
    from loats.trade_decision import trade_decision_engine

    resumed = resume_log is not None and not dry_run
    if resumed:
        assert resume_log is not None
        run_log = resume_log
        print(f"[P5] resuming run log: {run_log}")
    else:
        run_log = _init_run_log(reason, dry_run)
        print(f"[P5] run log: {run_log}")
    print(f"[P5] dry_run={dry_run} duration={duration or 'until stopped'}")

    if not dry_run:
        # Single-writer guard: claim writer-ship before any baseline is
        # written. main() pre-checks via _resolve_resume_target, but the
        # claim here is the enforcement point — a watchdog and an operator
        # racing to resume the same log must yield exactly one writer.
        if not _claim_run_log(
            run_log, refusal="second writer detected (single-writer guard)"
        ):
            print(
                f"{FAIL_SYM} run log is held by a live supervisor "
                "— refusing to start a second writer",
                file=sys.stderr,
            )
            return 2
        if resumed:
            _append_event(run_log, "writer_claimed", f"PID {os.getpid()}")

    unhandled = 0
    task: asyncio.Task[None] | None = None
    system = None
    baseline: dict[str, Any] | None = None

    try:
        if dry_run:
            # Smoke path: enable routing in-process, exercise the disabled
            # -> enabled transition and the run-log writer, no orchestrator
            # cycle, no HTTP.
            trade_decision_engine.enable_analyzer_routing()
            assert trade_decision_engine.analyzer_routing_enabled is True
            _append_event(run_log, "routing_enabled", "dry-run smoke")
            await asyncio.sleep(0)
            print(
                "[P5] dry-run complete: routing enable path exercised, "
                "run log initialized"
            )
        else:
            from loats.main import TradingSystem

            system = TradingSystem()
            await system.initialize()
            # Enable routing for the supervised run (default stays OFF).
            trade_decision_engine.enable_analyzer_routing()
            if resumed:
                _append_event(
                    run_log, "routing_enabled", "live supervised run (resumed)"
                )
                prior = json.loads(run_log.read_text(encoding="utf-8"))
                logged_cycles = int(prior.get("cycles_completed") or 0)
                logged_counters_raw = prior.get("counters") or {}
                logged_counters = {
                    key: int(logged_counters_raw.get(key) or 0)
                    for key in ("success", "disabled", "error")
                }
                prior_restarts = int(prior.get("restarts") or 0)
                baseline = _effective_resume_baseline(
                    _capture_live_baseline(system),
                    logged_cycles,
                    logged_counters,
                )
                _update_run_log(
                    run_log,
                    {
                        "restarts": prior_restarts + 1,
                        "cycles_completed_baseline": baseline["cycles_completed"],
                        "counters_baseline": dict(baseline["counters"]),
                        "last_sampled_at": _utcnow_iso(),
                    },
                )
            else:
                _append_event(run_log, "routing_enabled", "live supervised run")
                baseline = _capture_live_baseline(system)
                _update_run_log(
                    run_log,
                    {
                        "cycles_completed_baseline": baseline["cycles_completed"],
                        "counters_baseline": dict(baseline["counters"]),
                    },
                )
            task = asyncio.create_task(system.start())
            unhandled += await _supervise_live(
                system, run_log, baseline, duration, task
            )
    except (KeyboardInterrupt, asyncio.CancelledError):
        _append_event(run_log, "interrupted", "operator interrupt")
    except Exception as exc:
        unhandled += 1
        _append_event(run_log, "unhandled_exception", f"{type(exc).__name__}: {exc}")
        print(f"{FAIL_SYM} unhandled exception: {exc}", file=sys.stderr)
    finally:
        if system is not None:
            try:
                await system.shutdown()
            except Exception as exc:
                unhandled += 1
                _append_event(run_log, "shutdown_error", f"{type(exc).__name__}: {exc}")
        if task is not None and not task.done():
            task.cancel()
        if system is not None and baseline is not None:
            # Final sample so the ended run log carries the last measured
            # activity state, not the previous interval's.
            try:
                _sample_live_activity(system, run_log, baseline)
            except Exception:
                pass
        try:
            trade_decision_engine.disable_analyzer_routing()
        except Exception:
            pass
        _update_run_log(
            run_log,
            {
                "ended_at": _utcnow_iso(),
                "unhandled_exceptions": unhandled,
            },
        )
        # Release the single-writer claim only AFTER ended_at is durable:
        # releasing first would leave a claimed-but-ended window where a
        # resumed supervisor could refuse a legitimately finished run.
        _release_run_log(run_log)
        print("[P5] run ended; grading with scripts/verify_p5_forward_test.py")

    return 0 if unhandled == 0 else 1


def _status(path: Path | None) -> int:
    """Print the current state of the newest (or given) run log."""
    run_log = _find_run_log(path)
    if run_log is None:
        print("no P5 run log found (reports/p5_forward_test_*.json)")
        return 1
    data = json.loads(run_log.read_text(encoding="utf-8"))
    started = data.get("started_at")
    ended = data.get("ended_at")
    span = ""
    if started:
        s = datetime.datetime.fromisoformat(started)
        e = (
            datetime.datetime.fromisoformat(ended)
            if ended
            else datetime.datetime.now(datetime.UTC)
        )
        if e.tzinfo is None:
            e = e.replace(tzinfo=datetime.UTC)
        if s.tzinfo is None:
            s = s.replace(tzinfo=datetime.UTC)
        span = f"{(e - s).total_seconds() / 86400:.2f}d"
    print(f"run log   : {run_log}")
    print(f"started_at: {started}")
    ended_or_now = (
        datetime.datetime.fromisoformat(ended)
        if ended
        else datetime.datetime.now(datetime.UTC)
    )
    counters = data.get("counters") or {}
    cycles = data.get("cycles_completed")
    activity = (
        cycles + sum(int(v) for v in counters.values()) if cycles is not None else None
    )
    if activity is not None:
        sampled = data.get("last_sampled_at")
        freshness = ""
        if sampled:
            s = datetime.datetime.fromisoformat(sampled)
            if s.tzinfo is None:
                s = s.replace(tzinfo=datetime.UTC)
            if ended_or_now.tzinfo is None:
                ended_or_now = ended_or_now.replace(tzinfo=datetime.UTC)
            freshness = (
                f", last sample {(ended_or_now - s).total_seconds():.0f}s before end"
            )
        print(
            f"activity  : {activity} measured (cycles={cycles}, "
            f"counters={counters}{freshness})"
        )
    else:
        print("activity  : none recorded (legacy log — no live sampling)")
    process = "ongoing" if not ended else "ended"
    print(f"ended_at  : {ended or '(ongoing)'} [{process}]")
    # Single-writer guard visibility: who holds the log, and any refusal
    # recorded when a second writer was turned away.
    writer_pid = data.get("supervisor_pid")
    if writer_pid is not None:
        if _pid_alive_running_supervisor(writer_pid, data.get("supervisor_started_at")):
            state = "alive"
        else:
            state = "stale (dead or recycled PID)"
        print(f"writer    : PID {writer_pid} [{state}]")
    else:
        print("writer    : none (unclaimed or pre-guard log)")
    if data.get("resume_refusal"):
        print(f"refusal   : {data['resume_refusal']}")
    if not ended:
        sampled = data.get("last_sampled_at")
        sampled_ts = datetime.datetime.fromisoformat(sampled) if sampled else None
        now = datetime.datetime.now(datetime.UTC)
        if sampled_ts is not None:
            if sampled_ts.tzinfo is None:
                sampled_ts = sampled_ts.replace(tzinfo=datetime.UTC)
            age = (now - sampled_ts).total_seconds()
            if age > _STALE_WARN_S:
                print(
                    f"WARNING   : last sample {age / 3600:.1f}h ago "
                    f"(supervisor samples every {_SAMPLE_INTERVAL_S:.0f}s) — "
                    "no supervisor is writing to this run log; "
                    "resume it: python scripts/run_p5_forward_test.py --resume"
                )
    print(f"span      : {span} (required >= {MIN_SPAN_DAYS}d)")
    print(f"exceptions: {data.get('unhandled_exceptions')}")
    print(f"counters  : {counters}")
    grade = _grade_current_run(run_log)
    print(f"verdict   : {grade.verdict if grade is not None else 'ungradeable'}")
    return 0


def main() -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="P5 forward-test supervisor (F8-H-01)."
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--dry-run",
        action="store_true",
        help="smoke test: exercise routing enable + run-log init, no HTTP",
    )
    mode.add_argument(
        "--ack-live-endpoint",
        action="store_true",
        help=(
            "acknowledge a reachable OpenAlgo Analyzer endpoint; starts the "
            "real supervised run (production default stays OFF)"
        ),
    )
    mode.add_argument("--status", action="store_true", help="inspect run log")
    mode.add_argument(
        "--resume",
        action="store_true",
        help=(
            "resume the newest ongoing live run (or the --run-log target) in "
            "this process — survives host restarts without breaking the "
            "14-day span; refused for dry-run or ended logs"
        ),
    )
    parser.add_argument(
        "--run-log",
        type=Path,
        default=None,
        help="explicit run-log path (default: newest under reports/)",
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=None,
        help="supervise for N seconds then stop (testing)",
    )
    parser.add_argument(
        "--reason", default="F8-H-01 P5 forward test", help="run-log reason"
    )
    args = parser.parse_args()

    if args.status:
        return _status(args.run_log)

    if args.dry_run:
        return asyncio.run(_run(dry_run=True, reason=args.reason, duration=None))

    if args.resume:
        target = _resolve_resume_target(args.run_log)
        if target is None:
            return 2
        return asyncio.run(
            _run(
                dry_run=False,
                reason=args.reason,
                duration=args.duration,
                resume_log=target,
            )
        )

    if not args.ack_live_endpoint:
        print(
            f"{FAIL_SYM} live run requires --ack-live-endpoint "
            "(operator confirms reachable Analyzer endpoint)",
            file=sys.stderr,
        )
        return 2
    return asyncio.run(_run(dry_run=False, reason=args.reason, duration=args.duration))


if __name__ == "__main__":
    # Exit-code contract (2026-09-05): main()'s return value is the process
    # exit code. Previously the bare main() call discarded it, so a failed
    # live run (unhandled exceptions) exited 0 — invisible to Task
    # Scheduler / CI / any wrapper scripting on the outcome.
    sys.exit(main())
