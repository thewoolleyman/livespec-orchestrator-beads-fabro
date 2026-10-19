"""Side-effect seams for the Dispatcher: subprocess runner + journal.

`ShellCommandRunner` is the production `CommandRunner` and now lives in
`_dispatcher_shell_runner`, re-exported here because almost every caller
reaches for it through this facade. It moved to break an import cycle the
whole-run wall budget's export chain closed back onto this module: this
module is both a DEFINITION site and a FACADE, so anything
`WatchedFabroLauncher` below reaches that needed the runner imported this
facade back while it was still initializing. A module INSIDE the
launcher's own import reach must therefore import the LEAF directly —
`_dispatcher_preserve_reference` is the one that does — and that module's
docstring carries the mechanism. The hermetic test tier exercises the
runner with `sys.executable -c` stubs, mirroring how `test_orchestrator`
drives the injected reference CLIs.

`WatchedFabroLauncher` is the production `FabroLauncher`: it runs `fabro
run` in a BACKGROUND thread (through the injected `CommandRunner`, which
blocks in the thread) while the FOREGROUND samples the run's liveness via
`fabro ps`/`fabro events` and `fabro rm -f`-es a confirmed sustained
stall (the coarse wall-clock progress watchdog, work-item
livespec-impl-beads-oyg — the 7us.6 silent-deadlock backstop). Like
`ShellCommandRunner` it is a production seam the hermetic unit tier does
NOT execute: the engine's stall branch is driven by injecting a fake
`FabroLauncher`, and the watchdog DECISION logic is unit-tested directly
in `_dispatcher_watchdog`. No test launches a real fabro run.

`JournalFile` is the structured iteration journal the Dispatcher
guidance requires (livespec non-functional-requirements.md):
append-only JSONL, one
record per engine stage / loop event, machine-readable for post-hoc
audit. Appends are lock-serialized so parallel dispatch threads cannot
interleave lines.

It is also THE APPEND LAYER of the journal invoker attribution contract in
`SPECIFICATION/contracts.md`: every record it writes is stamped with `invoker`
and `invoker_source` ONCE, here, and a record whose caller already supplied
either field is refused as a programming error. Stamping in one place is
what makes the attribution unforgeable — a writer that could stamp its own
identity could assert any identity, one caller at a time. The refusal is
the enforcement of that: it fails loudly at the seam rather than silently
preferring one of two disagreeing values. EVERY journal write MUST route
through `append`; opening the journal path directly is forbidden, and
`tests/test_journal_append_chokepoint.py` is the mechanical control that
proves no code does.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from livespec_runtime.github_auth.errors import GithubAppAuthError

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandResult,
    CommandRunner,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io_fabro_launcher import (
    WatchedFabroLauncher,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_journal_file import (
    JournalFile,
    utc_now_iso,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_shell_runner import (
    ShellCommandRunner,
    child_env,
)
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt

__all__: list[str] = [
    "GITHUB_TOKEN_ENV_VAR",
    "GithubTokenEnvRunner",
    "JournalFile",
    "ShellCommandRunner",
    "WatchedFabroLauncher",
    "child_env",
    "utc_now_iso",
]

# The env var name `gh` (and the `gh auth git-credential` helper raw `git`
# uses) reads its token from; the run-config overlay projects the SAME name
# into the sandbox env table. A NAME, never a secret value.
GITHUB_TOKEN_ENV_VAR = "GH_TOKEN"  # noqa: S105 - env-var NAME, not a secret value


@dataclass(frozen=True, kw_only=True)
class GithubTokenEnvRunner:
    """CommandRunner decorator: refresh GH_TOKEN before EVERY command."""

    inner: CommandRunner
    token: Callable[[], str]

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: Mapping[str, str | None] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        token = attempt(action=self.token, exceptions=(GithubAppAuthError,))
        if isinstance(token, AttemptFailure):
            exc = cast("GithubAppAuthError", token.error)
            return CommandResult(
                exit_code=1,
                stdout="",
                stderr=f"GitHub App token refresh failed (fail-closed): {exc.detail}",
            )
        os.environ[GITHUB_TOKEN_ENV_VAR] = token
        merged_env: dict[str, str | None] = {
            **(env or {}),
            GITHUB_TOKEN_ENV_VAR: os.environ[GITHUB_TOKEN_ENV_VAR],
        }
        if stdin is None:
            return self.inner.run(
                argv=argv,
                cwd=cwd,
                timeout_seconds=timeout_seconds,
                env=merged_env,
            )
        return self.inner.run(
            argv=argv,
            cwd=cwd,
            timeout_seconds=timeout_seconds,
            env=merged_env,
            stdin=stdin,
        )
