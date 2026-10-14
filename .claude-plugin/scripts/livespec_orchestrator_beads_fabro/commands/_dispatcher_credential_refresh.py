"""Resolve Claude credentials afresh through the target's configured wrapper.

Only Claude token slots cross this boundary. Removing inherited slots before
invoking the wrapper prevents a nested invocation from retaining launch-time
values; replacing those slots afterward also removes accounts deleted upstream.
The resulting environment is used by both this probe and subsequent admission.
Wrapper output and errors are never included in diagnostics or journal records.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import cast

from livespec_orchestrator_beads_fabro.commands._dispatcher_claude_credential import (
    CLAUDE_OAUTH_TOKEN_ENV,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_credential_wrapper import (
    read_dispatch_target_credential_wrapper,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import ShellCommandRunner
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt, parse_json

__all__: list[str] = [
    "refresh_claude_credentials",
]

# -S keeps this stdlib-only child independent of site hooks in the caller's
# Python environment. The wrapper's environment is captured only in memory.
_CAPTURE = (
    "import json, os, sys; "
    "json.dump({k: v for k, v in os.environ.items() "
    "if k == 'CLAUDE_CODE_OAUTH_TOKEN' "
    "or k.startswith('CLAUDE_CODE_OAUTH_TOKEN__')}, sys.stdout)"
)


def _is_token_slot(*, name: str) -> bool:
    return name == CLAUDE_OAUTH_TOKEN_ENV or name.startswith(f"{CLAUDE_OAUTH_TOKEN_ENV}__")


def refresh_claude_credentials(*, repo: Path) -> None:
    """Refresh configured slots, clearing stale values if resolution fails.

    An undeclared wrapper retains the existing environment-only contract.
    A declared wrapper that fails leaves no credential for admission to use.
    """
    wrapper = read_dispatch_target_credential_wrapper(repo=repo)
    if not wrapper:
        return
    for name in tuple(os.environ):
        if _is_token_slot(name=name):
            del os.environ[name]
    result = attempt(
        action=lambda: ShellCommandRunner().run(
            argv=[*wrapper, sys.executable, "-S", "-c", _CAPTURE],
            cwd=repo,
            timeout_seconds=30,
            stdin=subprocess.DEVNULL,
        ),
        exceptions=(OSError, ValueError),
    )
    if isinstance(result, AttemptFailure) or result.exit_code != 0:
        return
    payload = parse_json(text=result.stdout)
    if not isinstance(payload, dict):
        return
    slots = cast(dict[str, object], payload)
    if not all(
        _is_token_slot(name=name) and isinstance(value, str) for name, value in slots.items()
    ):
        return
    os.environ.update(cast(dict[str, str], slots))
