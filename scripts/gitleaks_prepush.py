#!/usr/bin/env python3
"""Defense-in-depth pre-push secret net: default-rules gitleaks on the incoming diff.

Registered as the F8-C-02 NEXT item (docs/audit-history/
10Sep2026-gitleaks-prepush-net.md). The repository config
``.gitleaks.toml`` allowlists ``.env.test`` ON PURPOSE, so any gitleaks
run that loads it can never re-flag that class. This hook scans the
commits a push could publish under PURE default rules (an injected
minimal config with no allowlist) and fails the push closed on a leak.

Contract:
- stdin-independent BY DESIGN: pre-commit consumes the pre-push stdin
  itself (verified in installed pre-commit 4.6.2 hook_impl.py), so a
  hook that reads stdin would always see EOF and silently pass. The
  scan range is derived from git directly.
- Range: ``git rev-list --branches --not --remotes`` -- every commit
  only this host holds is exactly what a push could publish. This is
  pre-commit's own fallback range semantics (--not --remotes) widened
  to all local branches, so it never depends on the pushed ref name.
  Empty set -> nothing to scan, exit 0 (the binary is not invoked).
- gitleaks >= 8.19 removed ``detect``/``protect``; the supported
  surface is ``gitleaks git --log-opts=...`` (verified live on 8.30.1,
  where the removed subcommands exit 126).
- Fail-closed: a missing gitleaks binary or any nonzero gitleaks exit
  fails the push. GITLEAKS_BINARY overrides binary resolution for
  tests and non-PATH installs.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# The entire config: default rules, NO allowlist. Config precedence puts
# an explicit --config above any (target path)/.gitleaks.toml, so this
# is what gitleaks sees even when run from the repo root.
DEFAULT_RULES_TOML = (
    "# Defense-in-depth pre-push net: pure default rules, no allowlist.\n"
    "[extend]\n"
    "useDefault = true\n"
)


def resolve_binary(env: Mapping[str, str] | None = None) -> str | None:
    """Return the gitleaks binary path, or None when absent.

    GITLEAKS_BINARY wins over PATH resolution so tests and non-PATH
    installs are deterministic.
    """
    environ = os.environ if env is None else env
    override = environ.get("GITLEAKS_BINARY", "")
    if override:
        return override
    return shutil.which("gitleaks", path=environ.get("PATH"))


def introduced_commits(repo_root: Path) -> list[str]:
    """Commits only this host holds (publishable by some push)."""
    proc = subprocess.run(
        ["git", "rev-list", "--branches", "--not", "--remotes"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    if proc.returncode != 0:
        print(
            f"[gitleaks-prepush] git rev-list failed (rc {proc.returncode}): "
            f"{proc.stderr.strip()}",
            file=sys.stderr,
        )
        raise SystemExit(1)
    return proc.stdout.split()


def run_scan(
    repo_root: Path,
    commits: Sequence[str],
    binary: str,
    env: Mapping[str, str] | None = None,
) -> int:
    """Scan commits under default rules; return gitleaks' exit code."""
    config_fd, config_name = tempfile.mkstemp(
        prefix="gitleaks-default-rules-", suffix=".toml"
    )
    config_path = Path(config_name)
    try:
        with os.fdopen(config_fd, "w", encoding="utf-8") as handle:
            handle.write(DEFAULT_RULES_TOML)
        argv = [
            binary,
            "git",
            # "<introduced> --not --remotes": the exclusion caps gitleaks'
            # ancestry walk at exactly the introduced set. Bare SHAs make
            # gitleaks scan the FULL ancestry (464 commits on this repo),
            # which permanently false-positives on the dispositioned
            # gitleaks-report artifacts already in history (live-verified:
            # the net blocked its own wave's push before this fix).
            f"--log-opts={' '.join(commits)} --not --remotes",
            f"--config={config_path}",
            "--no-banner",
            "--no-color",
            "--redact",
            "-v",
        ]
        proc = subprocess.run(
            argv,
            cwd=repo_root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=None if env is None else dict(env),
            check=False,
        )
        if proc.stdout:
            print(proc.stdout, end="" if proc.stdout.endswith("\n") else "\n")
        if proc.stderr:
            print(
                proc.stderr,
                file=sys.stderr,
                end="" if proc.stderr.endswith("\n") else "\n",
            )
        return proc.returncode
    finally:
        config_path.unlink(missing_ok=True)


def main() -> int:
    """Hook entry point. Returns the process exit code."""
    binary = resolve_binary()
    if binary is None:
        print(
            "[gitleaks-prepush] FAIL: gitleaks binary not found. The pre-push\n"
            "secret net fails closed - install it with:\n"
            "    winget install Gitleaks.Gitleaks\n"
            "or set GITLEAKS_BINARY to the binary path.",
            file=sys.stderr,
        )
        return 1

    commits = introduced_commits(REPO_ROOT)
    if not commits:
        print("[gitleaks-prepush] push introduces 0 new commits: pass")
        return 0

    rc = run_scan(REPO_ROOT, commits, binary)
    if rc == 0:
        print(
            f"[gitleaks-prepush] pass: {len(commits)} introduced commit(s) "
            "scanned under default rules (no allowlist)."
        )
        return 0
    if rc == 126:
        print(
            "[gitleaks-prepush] FAIL: gitleaks rejected the invocation "
            "(rc 126). The subcommand/flag surface changed (gitleaks "
            "removed detect/protect in 8.19); update "
            "scripts/gitleaks_prepush.py to the supported surface.",
            file=sys.stderr,
        )
    else:
        print(
            f"[gitleaks-prepush] FAIL: default-rules gitleaks scan exited "
            f"{rc} over {len(commits)} introduced commit(s). Secrets must "
            f"be removed and rotated before this push lands.",
            file=sys.stderr,
        )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
