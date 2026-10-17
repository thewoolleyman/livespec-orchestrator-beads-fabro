#!/usr/bin/env python3
"""livespec sandbox path guard — Claude Code PreToolUse hook (Bash).

Refuses a shell command whose executed segment would remove, move or replace
one of the run's protected paths: the factory sandbox root, the run's working
directory, the working-directory link the engine sets that directory to, or the
run's clone. `livespec_sandbox_path_policy` decides; this module is the only
part that reads the world and speaks to the session.

WHY A PreToolUse DENY IS THE RIGHT SEAT. The governing clause requires the
refusal BEFORE ANY PART of the command executes, and a `PreToolUse` deny stops
the whole tool call rather than one segment of it — so for `cd /tmp && rm -rf
/workspace && mkdir -p /workspace`, measured as the command that ended run
01M4YJGC55V86C9V1X07QG3Y2H, the `cd` does not run either. Nothing downstream
can offer that: by the time a shell is executing segments, the segment that
destroys the run has already destroyed it.

WHAT IT READS, AND WHY EACH READING IS HERE RATHER THAN IN THE POLICY. The
sandbox root comes from the environment (overridable, so a test can build a
real layout under `tmp_path`; production never sets it). The repository comes
from `CLAUDE_PROJECT_DIR`, falling back to the payload's own working directory
— the project directory is preferred because it is STABLE, while the payload's
is wherever the agent last changed to, which a `cd /tmp` moves. Each immediate
child of the root is paired with what it really is, because the
working-directory LINK is identified by what it points at rather than by a name
this guard could predict: the engine chooses that name, and the two engine
layouts choose differently.

FAIL-OPEN AT THE BOUNDARY, deliberately opposite to the decision it wraps. The
decision is exact and refuses only on a positive match, but a crashing
PreToolUse hook wedges every Bash call in the session — so malformed input, an
unmodelled payload shape and a bug in the guard are all silent pass-throughs at
exit 0. An unreadable sandbox root is the same posture one level in: it yields
no protected paths, which is the inert case this guard must present outside a
factory sandbox.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import livespec_sandbox_path_policy as policy

__all__: list[str] = ["DEFAULT_SANDBOX_ROOT", "SANDBOX_ROOT_ENV_VAR", "main"]

# The fabro sandbox's own mount. Correct in production and WRONG anywhere else,
# so the override below exists to let a test build a real layout under a
# temporary root; production never sets it. Mirrors
# `LIVESPEC_SANDBOX_GH_REFRESH_ROOT` in `_dispatcher_gh_refresh`.
DEFAULT_SANDBOX_ROOT = "/workspace"
SANDBOX_ROOT_ENV_VAR = "LIVESPEC_SANDBOX_ROOT"

_PROJECT_DIR_ENV_VAR = "CLAUDE_PROJECT_DIR"
_BASH_TOOL = "Bash"


def main() -> int:
    """Read the PreToolUse payload on stdin and deny a run-destroying command."""
    try:
        decision = _decision(raw=sys.stdin.read(), environ=dict(os.environ))
        if decision is not None:
            _ = sys.stdout.write(decision + "\n")
    except Exception:  # noqa: BLE001 — sole fail-open hook boundary: silent pass-through, exit 0
        return 0
    return 0


def _decision(*, raw: str, environ: dict[str, str]) -> str | None:
    """Return the deny payload for a run-destroying command, or None to allow."""
    if not raw.strip():
        return None
    data = json.loads(raw)
    if data.get("tool_name", "") != _BASH_TOOL:
        return None
    command = data.get("tool_input", {}).get("command", "")
    if not command:
        return None
    root = environ.get(SANDBOX_ROOT_ENV_VAR, "").strip() or DEFAULT_SANDBOX_ROOT
    working = str(data.get("cwd", "") or "").strip()
    repository = environ.get(_PROJECT_DIR_ENV_VAR, "").strip() or working
    targets = policy.removal_targets(command=command, working_directory=working or repository)
    matched = policy.refused_path(
        targets=targets,
        # Each target paired with what it REALLY is, so a symbolic link the
        # agent made itself cannot stand in for the path it points at. Pairing
        # happens here rather than in the policy because the policy has no
        # filesystem; a glob target resolves to itself and the policy ignores
        # the pairing for one anyway.
        resolved={target: _real_path(path=target) for target in targets},
        protected=policy.protected_paths(
            sandbox_root=root,
            repository_path=repository,
            repository_clone=_real_path(path=repository),
            sandbox_entry_targets=_entry_targets(root=root),
        ),
    )
    if matched is None:
        return None
    return _deny_payload(reason=policy.refusal_message(protected_path=matched, command=command))


def _real_path(*, path: str) -> str:
    """What `path` really is, with every symbolic link in it resolved."""
    return str(Path(path).resolve())


def _entry_targets(*, root: str) -> dict[str, str]:
    """Each immediate child of the sandbox root, paired with what it really is.

    A root that cannot be listed yields nothing, so the policy finds no link and
    protects nothing — the inert case outside a factory sandbox.
    """
    try:
        children = sorted(Path(root).iterdir())
    except OSError:
        return {}
    return {str(child): _real_path(path=str(child)) for child in children}


def _deny_payload(*, reason: str) -> str:
    payload = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }
    return json.dumps(payload)


if __name__ == "__main__":
    raise SystemExit(main())
