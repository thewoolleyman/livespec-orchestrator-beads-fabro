"""Stop hook: run the shared host session-wait check before a Claude turn ends.

The check lists ended-but-unacknowledged targets, overdue waits, missing waiter
processes, unavailable inventory, and launch obligations whose independent
recovery owner is missing — including work launched with no wait at all. The
hook blocks the stop when the check reports findings, so the owning session
reads them before parking.

It blocks ONCE: Claude Code sets `stop_hook_active` on the continuation a block
produced, and a second block there would trap the session in a loop. A check
that could not run is reported as unavailable rather than read as healthy.

This is the Claude runtime's integration only. Native Codex and pi are not
covered by it; their guidance invokes the same `check` command explicitly.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import cast

__all__: list[str] = [
    "CheckOutcome",
    "block_reason",
    "check_command",
    "main",
    "run_check",
]

_CHECK_TIMEOUT_SECONDS = 25.0

_UNAVAILABLE_REASON = """The session-wait check was unavailable, so this turn's outstanding waits \
and launch obligations could not be verified. Run the plugin's \
`scripts/bin/session_wait.py check --repo <repo>` and read its result before finishing."""

_FINDINGS_HEADER = "The session-wait check found unresolved items before this turn ends:"

_FINDINGS_REMEDY = """Resolve each one: receive the result and run `session_wait.py ack` for an \
ended wait, re-arm a bounded wait for a missing waiter, or confirm the independent \
recovery owner covers an outstanding obligation. Then finish."""


@dataclass(frozen=True, kw_only=True)
class CheckOutcome:
    returncode: int
    stdout: str


def check_command(*, plugin_root: Path, project: Path) -> list[str]:
    return [
        sys.executable,
        str(plugin_root / "scripts" / "bin" / "session_wait.py"),
        "check",
        "--repo",
        str(project),
    ]


def run_check(*, command: list[str], timeout_seconds: float) -> CheckOutcome | None:
    """Run the check, or report `None` when it could not run to an exit status."""
    try:
        completed = subprocess.run(
            command,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return CheckOutcome(returncode=completed.returncode, stdout=completed.stdout)


def block_reason(*, outcome: CheckOutcome | None) -> str:
    """The reason to block on, or an empty string when the turn may end."""
    if outcome is not None and outcome.returncode == 0:
        return ""
    lines = _finding_lines(outcome=outcome)
    if not lines:
        return _UNAVAILABLE_REASON
    return "\n".join([_FINDINGS_HEADER, *lines, _FINDINGS_REMEDY])


def _finding_lines(*, outcome: CheckOutcome | None) -> list[str]:
    if outcome is None or outcome.returncode != 1:
        return []
    try:
        findings = json.loads(outcome.stdout)["summary"]["findings"]
        return [f"- {entry['id']}: {entry['finding']} ({entry['source']})" for entry in findings]
    except (ValueError, KeyError, TypeError):
        return []


def _stop_hook_active() -> bool:
    try:
        payload = json.loads(sys.stdin.read())
    except ValueError:
        return False
    return (
        isinstance(payload, dict)
        and cast("dict[str, object]", payload).get("stop_hook_active") is True
    )


def main() -> int:
    plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
    project = os.environ.get("CLAUDE_PROJECT_DIR")
    if os.environ.get("CODEX_THREAD_ID") or not plugin_root or not project:
        return 0
    if _stop_hook_active():
        return 0
    outcome = run_check(
        command=check_command(plugin_root=Path(plugin_root), project=Path(project)),
        timeout_seconds=_CHECK_TIMEOUT_SECONDS,
    )
    reason = block_reason(outcome=outcome)
    if reason:
        _ = sys.stdout.write(json.dumps({"decision": "block", "reason": reason}) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
