#!/usr/bin/env python3
"""LOATS P5 wave-state verifier (stdlib-only, offline by default).

Encodes the eight 19-Oct wave items as observable on-disk facts and grades
them against either the frozen PRE-WAVE state (default; all items expected
OPEN at the pinned HEAD) or the POST-WAVE state (all items expected CLOSED).

Modes:
    pre  (default)  HEAD == 0dcf63ed and every wave item still OPEN.
    post            HEAD moved past 0dcf63ed and every wave item CLOSED.

Wave items covered (16-Oct-2026 live probe basis at 0dcf63ed, all OPEN):
    L-03     nifty_lot_size pinned at 25 (true lot 65, FAOP70616)
    HC-23    'mods' zero-consumer alias (report only; retirement optional)
    M-02     database.py cross-thread sqlite connection, no single writer
    M-03     RSS startup gate advisory (error+alert+return, never blocks)
    L-01     openalgo.py kill-switch twins + duplicated apikey body-key
    P1-R     no resume-owner lock anywhere in src
    P1-A     audit JSONL append handle, no rotation
    P1-D     no DB persist at the routing dispatch point (outcomes only)

Exit codes: 0 = every gate matches the selected expectation;
1 = at least one gate mismatched or errored; 2 = usage/environment error.

PowerShell 5.1 usage (repo root, repo venv):
    .\\.venv\\Scripts\\python.exe .\\scripts\\p5_verify_state.py
    .\\.venv\\Scripts\\python.exe .\\scripts\\p5_verify_state.py --expect post
    .\\.venv\\Scripts\\python.exe .\\scripts\\p5_verify_state.py --json --telegram

Tripwire discipline: a green pre-run proves the frozen pre-wave state; a
green post-run is necessary but NOT sufficient wave evidence. The full gate
chain (ruff/mypy/bandit/pytest/coverage/pip-audit/safety/gitleaks) and code
review still apply on wave day. Untracked tool: committing it at wave time
requires the TRACKED_FILE_CEILING re-pin in the same commit.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path

PRE_HEAD = "0dcf63ed"
SETTINGS_RELPATH = Path("src/loats/config/settings.py")
DATABASE_RELPATH = Path("src/loats/database.py")
ORCHESTRATOR_RELPATH = Path("src/loats/orchestrator.py")
OPENALGO_RELPATH = Path("src/loats/openalgo.py")
TRADE_DECISION_RELPATH = Path("src/loats/trade_decision.py")
REPORTS_GLOB = "p5_forward_test_*.json"
RESUME_LOCK_RE = re.compile(
    r"resume[_-]?(owner|lock)|owner[_-]?lock|lock[_-]?(file|held)",
    re.IGNORECASE,
)
APIKEY_NEEDLE = 'json_body.setdefault("apikey"'
DISPATCH_ANCHOR = "Routing TradeDecision to Analyzer"
DISPATCH_PERSIST_TOKENS = (
    "async_log_audit",
    "_persist_routing_outcome",
    "db._log_audit",
)
WATCHDOG_CANDIDATES = ("loats-ops/p5_watchdog.log", "../loats-ops/p5_watchdog.log")
WATCHDOG_WARN_BYTES = 200 * 1024 * 1024
SAMPLE_STALE_MIN = 15.0
IST_OFFSET = timedelta(hours=5, minutes=30)


class Check:
    """One verifier row: gate rows drive the exit code, info rows do not."""

    def __init__(self, cid: str, item: str, kind: str = "gate") -> None:
        self.id = cid
        self.item = item
        self.kind = kind
        self.status = "INFO"
        self.expected = ""
        self.actual = ""
        self.detail = ""

    def as_dict(self) -> dict[str, str]:
        return {
            "id": self.id,
            "item": self.item,
            "kind": self.kind,
            "status": self.status,
            "expected": self.expected,
            "actual": self.actual,
            "detail": self.detail,
        }


def read_text(repo: Path, rel: Path) -> str:
    path = repo / rel
    if not path.is_file():
        raise FileNotFoundError(str(path))
    return path.read_text(encoding="utf-8", errors="replace")


def find_line(text: str, needle: str) -> int | None:
    pos = text.find(needle)
    if pos < 0:
        return None
    return text.count("\n", 0, pos) + 1


def method_body(text: str, name: str) -> str:
    """Source of a 4-space-indented method, up to the next sibling def.

    The scan for the next sibling starts on the line AFTER the def line:
    starting it at the end of the def name would let re.M's caret match
    the '(' of the parameter list at position 0 and truncate the body.
    """
    pattern = re.compile(rf"^    (?:async def|def) {re.escape(name)}\b", re.M)
    match = pattern.search(text)
    if match is None:
        return ""
    line_end = text.find("\n", match.end())
    if line_end < 0:
        return text[match.start() :]
    segment = text[line_end + 1 :]
    nxt = re.search(r"^    (?:async def|def) \w|^\S", segment, re.M)
    end = line_end + 1 + nxt.start() if nxt else len(text)
    return text[match.start() : end]


def field_value(text: str, field: str) -> tuple[int | None, int | None]:
    """Integer default of a pydantic Field and its 1-based line number."""
    pattern = re.compile(rf"^\s*{re.escape(field)}:\s*int\s*=\s*Field\(\s*(\d+)", re.M)
    match = pattern.search(text)
    if match is None:
        return None, None
    return int(match.group(1)), text.count("\n", 0, match.start()) + 1


def git_out(repo: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or f"git {' '.join(args)} failed")
    return proc.stdout.strip()


def grep_tree(repo: Path, pattern: re.Pattern[str]) -> list[str]:
    """Case-insensitive line hits for pattern across src/loats/**/*.py."""
    hits: list[str] = []
    root = repo / "src" / "loats"
    for path in sorted(root.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            if pattern.search(line):
                hits.append(f"{path.relative_to(repo)}:{lineno}")
    return hits


def check_head(repo: Path, mode: str, chk: Check) -> None:
    head = git_out(repo, "rev-parse", "--short=8", "HEAD")
    chk.actual = head
    if mode == "pre":
        chk.expected = f"== {PRE_HEAD} (wave still pending)"
        chk.status = "PASS" if head == PRE_HEAD else "FAIL"
        if chk.status == "FAIL":
            chk.detail = "HEAD moved before the wave - pre-wave freeze broken"
    else:
        chk.expected = f"!= {PRE_HEAD} (wave commits landed)"
        chk.status = "PASS" if head != PRE_HEAD else "FAIL"


def check_tree(repo: Path, mode: str, chk: Check) -> None:
    chk.kind = "info"
    chk.expected = "report only"
    try:
        lines = [
            ln
            for ln in git_out(repo, "status", "--porcelain").splitlines()
            if ln.strip()
        ]
    except Exception as exc:
        chk.status = "WARN"
        chk.actual = f"status unavailable: {exc}"
        return
    chk.actual = f"{len(lines)} dirty path(s)"
    chk.detail = "; ".join(lines[:5]) if lines else "working tree clean"


def check_l03(repo: Path, mode: str, chk: Check) -> None:
    text = read_text(repo, SETTINGS_RELPATH)
    value, line = field_value(text, "nifty_lot_size")
    if value is None:
        chk.status = "ERROR"
        chk.actual = "nifty_lot_size field not found"
        return
    chk.actual = f"nifty_lot_size={value} (settings.py:{line})"
    if mode == "pre":
        chk.expected = "25 (item OPEN: circular FAOP70616 flip still operator-gated)"
        chk.status = "PASS" if value == 25 else "FAIL"
    else:
        chk.expected = "!= 25 (flip applied, BANKNIFTY handled separately)"
        chk.status = "PASS" if value != 25 else "FAIL"


def check_hc23(repo: Path, mode: str, chk: Check) -> None:
    chk.kind = "info"
    chk.expected = "report only (optional retirement)"
    text = read_text(repo, SETTINGS_RELPATH)
    value, line = field_value(text, "mods")
    if value is None:
        chk.actual = "mods alias absent"
        chk.detail = "HC-23 alias retired"
    else:
        chk.actual = f"mods={value} (settings.py:{line})"
        chk.detail = "zero-consumer alias still present; retirement optional"


def check_m02(repo: Path, mode: str, chk: Check) -> None:
    text = read_text(repo, DATABASE_RELPATH)
    line = find_line(text, "check_same_thread=False")
    chk.actual = f"present at database.py:{line}" if line else "absent"
    if mode == "pre":
        chk.expected = "present (item OPEN: cross-thread conn, no single writer)"
        chk.status = "PASS" if line else "FAIL"
    else:
        chk.expected = "absent (single-writer remediation landed)"
        chk.status = "FAIL" if line else "PASS"


def check_m03(repo: Path, mode: str, chk: Check) -> None:
    text = read_text(repo, ORCHESTRATOR_RELPATH)
    body = method_body(text, "_validate_rss_startup_gate")
    if not body:
        chk.status = "ERROR"
        chk.actual = "_validate_rss_startup_gate not found"
        return
    line = find_line(text, "async def _validate_rss_startup_gate")
    has_raise = "raise" in body
    advisory = ("return" in body) and not has_raise
    chk.actual = (
        f"orchestrator.py:{line} "
        f"advisory-return={not has_raise} fail-closed-raise={has_raise}"
    )
    if mode == "pre":
        chk.expected = "advisory (error+alert+return, startup continues) = OPEN"
        chk.status = "PASS" if advisory else "FAIL"
    else:
        chk.expected = "fail-closed (raise on gate failure)"
        chk.status = "PASS" if has_raise else "FAIL"


def check_l01_twins(repo: Path, mode: str, chk: Check) -> None:
    text = read_text(repo, OPENALGO_RELPATH)
    total = len(re.findall(r"^def _check_kill_switch\b", text, re.M)) + len(
        re.findall(r"^async def _async_check_kill_switch\b", text, re.M)
    )
    l_sync = find_line(text, "def _check_kill_switch")
    l_async = find_line(text, "async def _async_check_kill_switch")
    chk.actual = f"sync@{l_sync} async@{l_async} (kill defs={total})"
    if mode == "pre":
        chk.expected = "defs=2 (twins with duplicated bodies) = OPEN"
        chk.status = "PASS" if total == 2 else "FAIL"
    else:
        chk.expected = "defs=1 (deduplicated implementation)"
        chk.status = "PASS" if total == 1 else "FAIL"


def check_l01_bodykey(repo: Path, mode: str, chk: Check) -> None:
    text = read_text(repo, OPENALGO_RELPATH)
    count = text.count(APIKEY_NEEDLE)
    first = find_line(text, APIKEY_NEEDLE)
    chk.actual = f"{count} occurrence(s), first at openalgo.py:{first}"
    if mode == "pre":
        chk.expected = "2 (body-key injection duplicated sync/async) = OPEN"
        chk.status = "PASS" if count == 2 else "FAIL"
    else:
        chk.expected = "1 (single shared injection path)"
        chk.status = "PASS" if count == 1 else "FAIL"


def check_p1_resume(repo: Path, mode: str, chk: Check) -> None:
    hits = grep_tree(repo, RESUME_LOCK_RE)
    chk.actual = f"{len(hits)} hit(s)" + (f", e.g. {hits[0]}" if hits else "")
    if mode == "pre":
        chk.expected = "0 hits (item OPEN: resume-owner lock absent)"
        chk.status = "PASS" if not hits else "FAIL"
    else:
        chk.expected = ">=1 hit (resume-owner lock implemented)"
        chk.status = "PASS" if hits else "FAIL"


def check_p1_rotate(repo: Path, mode: str, chk: Check) -> None:
    text = read_text(repo, DATABASE_RELPATH)
    count = len(re.findall(r"rotat", text, re.IGNORECASE))
    chk.actual = f"{count} rotat* match(es) in database.py"
    if mode == "pre":
        chk.expected = "0 (item OPEN: audit JSONL append handle, no rotation)"
        chk.status = "PASS" if count == 0 else "FAIL"
    else:
        chk.expected = ">=1 (audit-log rotation implemented)"
        chk.status = "PASS" if count > 0 else "FAIL"


def check_p1_dispatch(repo: Path, mode: str, chk: Check) -> None:
    text = read_text(repo, TRADE_DECISION_RELPATH)
    body = method_body(text, "_do_route_or_disable")
    anchor = body.find(DISPATCH_ANCHOR)
    if anchor < 0:
        chk.status = "ERROR"
        chk.actual = f"dispatch anchor not found: {DISPATCH_ANCHOR!r}"
        return
    try_pos = body.find("try:", anchor)
    window = body[anchor : try_pos if try_pos > 0 else len(body)]
    line = find_line(text, DISPATCH_ANCHOR)
    marked = any(tok in window for tok in DISPATCH_PERSIST_TOKENS)
    chk.actual = f"dispatch window at trade_decision.py:{line} persist-call={marked}"
    if mode == "pre":
        chk.expected = "persist-call=False (item OPEN: log+counter only at dispatch)"
        chk.status = "PASS" if not marked else "FAIL"
    else:
        chk.expected = "persist-call=True (DB persist at the dispatch point)"
        chk.status = "PASS" if marked else "FAIL"


def check_span(repo: Path, mode: str, chk: Check) -> None:
    chk.kind = "info"
    chk.expected = "live-span quartet (report only)"
    files = sorted(
        (repo / "reports").glob(REPORTS_GLOB), key=lambda p: p.stat().st_mtime
    )
    if not files:
        chk.status = "WARN"
        chk.actual = "no p5_forward_test_*.json snapshots"
        return
    path = files[-1]
    data = json.loads(path.read_text(encoding="utf-8"))
    now = datetime.now(UTC)
    mtime = datetime.fromtimestamp(path.stat().st_mtime, UTC)
    age_min = round((now - mtime).total_seconds() / 60, 1)
    sampled = data.get("last_sampled_at")
    sample_age: float | None = None
    if isinstance(sampled, str):
        try:
            sample_age = round(
                (now - datetime.fromisoformat(sampled)).total_seconds() / 60, 1
            )
        except ValueError:
            sample_age = None
    ended = data.get("ended_at")
    kill_ok = data.get("kill_switch_verified")
    unhandled = data.get("unhandled_exceptions")
    chk.actual = (
        f"{path.name} ended_at={ended} sampled={sample_age}min-ago "
        f"kill_verified={kill_ok} unhandled={unhandled} "
        f"restarts={data.get('restarts')}"
    )
    problems: list[str] = []
    if sample_age is not None and sample_age > SAMPLE_STALE_MIN:
        problems.append(f"sampling stale ({sample_age}min)")
    if kill_ok is not True:
        problems.append("kill_switch_verified is not true")
    if unhandled:
        problems.append(f"unhandled_exceptions={unhandled}")
    if ended is None and not problems:
        chk.status = "INFO"
        chk.detail = f"live span healthy (snapshot mtime age {age_min}min)"
    elif problems:
        chk.status = "WARN"
        chk.detail = "; ".join(problems)
    else:
        chk.status = "INFO"
        chk.detail = "closed span (graded by verify_p5_forward_test.py)"


def check_watchdog(repo: Path, mode: str, chk: Check, override: Path | None) -> None:
    chk.kind = "info"
    chk.expected = "report only (carried hygiene: no rotation configured)"
    candidates = [override] if override else [repo / c for c in WATCHDOG_CANDIDATES]
    found = next((c for c in candidates if c is not None and c.is_file()), None)
    if found is None:
        chk.status = "INFO"
        chk.actual = "not found at probed locations"
        chk.detail = "re-locate loats-ops/p5_watchdog.log at the next ops window"
        return
    size_mb = found.stat().st_size / (1024 * 1024)
    chk.actual = f"{found} = {size_mb:.1f} MB"
    if found.stat().st_size > WATCHDOG_WARN_BYTES:
        chk.status = "WARN"
        chk.detail = "trim at the next ops window (post-close)"
    else:
        chk.status = "INFO"


def check_telegram(repo: Path, mode: str, chk: Check) -> None:
    chk.kind = "info"
    chk.expected = "getMe ok=true (masked token display only)"
    env = repo / ".env"
    token = ""
    if env.is_file():
        for raw in env.read_text(encoding="utf-8", errors="replace").splitlines():
            stripped = raw.strip()
            if stripped.startswith("TELEGRAM_BOT_TOKEN="):
                token = stripped.split("=", 1)[1].strip().strip('"')
                break
    if not token:
        chk.status = "WARN"
        chk.actual = "no TELEGRAM_BOT_TOKEN in .env"
        return
    masked = token[:6] + "..." + token[-4:] if len(token) > 12 else "<masked>"
    try:
        url = f"https://api.telegram.org/bot{token}/getMe"
        with urllib.request.urlopen(url, timeout=10) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        chk.status = "WARN"
        chk.actual = f"getMe failed: {type(exc).__name__}"
        return
    ok = bool(payload.get("ok"))
    username = (payload.get("result") or {}).get("username")
    chk.actual = f"getMe ok={ok} bot=@{username} token={masked}"
    chk.status = "INFO" if ok else "WARN"


def run_checks(repo: Path, mode: str, args: argparse.Namespace) -> list[Check]:
    checks: list[Check] = [
        Check("GIT-HEAD", "HEAD pin"),
        Check("TREE", "working tree", kind="info"),
        Check("L-03", "NIFTY lot 25 flip"),
        Check("HC-23", "mods alias retirement", kind="info"),
        Check("M-02", "sqlite single-writer"),
        Check("M-03", "RSS gate fail-closed"),
        Check("L-01A", "kill twins dedup"),
        Check("L-01B", "apikey body-key dedup"),
        Check("P1-R", "resume-owner lock"),
        Check("P1-A", "audit rotation"),
        Check("P1-D", "dispatch DB persist"),
        Check("SPAN", "P5 span quartet", kind="info"),
        Check("WATCHDOG", "watchdog log hygiene", kind="info"),
    ]
    if args.telegram:
        checks.append(Check("TG", "telegram getMe", kind="info"))
    runners = {
        "GIT-HEAD": check_head,
        "TREE": check_tree,
        "L-03": check_l03,
        "HC-23": check_hc23,
        "M-02": check_m02,
        "M-03": check_m03,
        "L-01A": check_l01_twins,
        "L-01B": check_l01_bodykey,
        "P1-R": check_p1_resume,
        "P1-A": check_p1_rotate,
        "P1-D": check_p1_dispatch,
        "SPAN": check_span,
        "WATCHDOG": lambda r, m, c: check_watchdog(r, m, c, args.watchdog_path),
        "TG": check_telegram,
    }
    for chk in checks:
        try:
            runners[chk.id](repo, mode, chk)
        except Exception as exc:
            chk.status = "ERROR"
            chk.expected = chk.expected or "row evaluation failed"
            chk.actual = f"{type(exc).__name__}: {exc}"
    return checks


def print_table(repo: Path, mode: str, checks: list[Check], head: str) -> None:
    now = datetime.now(UTC)
    print("LOATS P5 wave-state verifier")
    print(f"repo : {repo}")
    print(f"head : {head}   mode: {mode}")
    print(f"time : {now.isoformat()} UTC | {(now + IST_OFFSET).isoformat()} IST")
    print("-" * 100)
    for chk in checks:
        print(f"[{chk.status}] {chk.id:<9} {chk.item}")
        print(f"           expected: {chk.expected}")
        print(f"           actual  : {chk.actual}")
        if chk.detail:
            print(f"           detail  : {chk.detail}")
    print("-" * 100)
    gates = [c for c in checks if c.kind == "gate"]
    failed = [c for c in gates if c.status in ("FAIL", "ERROR")]
    verdict = "PASS" if not failed else "FAIL"
    print(f"RESULT: {verdict} ({len(gates) - len(failed)}/{len(gates)} gates)")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="LOATS P5 wave-state verifier")
    parser.add_argument(
        "--repo",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="repository root (default: script parent's parent)",
    )
    parser.add_argument(
        "--expect",
        choices=("pre", "post"),
        default="pre",
        help="pre = frozen pre-wave state, post = wave landed",
    )
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    parser.add_argument(
        "--telegram", action="store_true", help="probe Telegram getMe (network)"
    )
    parser.add_argument(
        "--watchdog-path", type=Path, default=None, help="explicit p5_watchdog.log path"
    )
    args = parser.parse_args(argv)
    repo = args.repo.resolve()
    if not (repo / "src" / "loats").is_dir():
        print(f"ERROR: not a LOATS repo: {repo}", file=sys.stderr)
        return 2
    try:
        head = git_out(repo, "rev-parse", "--short=8", "HEAD")
    except Exception as exc:
        print(f"ERROR: git unavailable: {exc}", file=sys.stderr)
        return 2
    checks = run_checks(repo, args.expect, args)
    if args.json:
        gates = [c for c in checks if c.kind == "gate"]
        failed = [c for c in gates if c.status in ("FAIL", "ERROR")]
        print(
            json.dumps(
                {
                    "repo": str(repo),
                    "head": head,
                    "mode": args.expect,
                    "generated_at": datetime.now(UTC).isoformat(),
                    "result": "PASS" if not failed else "FAIL",
                    "checks": [c.as_dict() for c in checks],
                },
                indent=2,
            )
        )
    else:
        print_table(repo, args.expect, checks, head)
    return (
        0
        if all(c.status not in ("FAIL", "ERROR") for c in checks if c.kind == "gate")
        else 1
    )


if __name__ == "__main__":
    sys.exit(main())
