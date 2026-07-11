"""Side-effect seams for the Dispatcher: subprocess runner + journal.

`ShellCommandRunner` is the production `CommandRunner`: it executes the
engine's argvs via `subprocess.run` with captured output and converts
timeouts into non-zero `CommandResult`s (the engine treats every failure
as routable data, so the runner never lets an expected failure escape as
an exception). The hermetic test tier exercises it with
`sys.executable -c` stubs, mirroring how `test_orchestrator` drives the
injected reference CLIs.

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
"""

from __future__ import annotations

import json
import os
import subprocess
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from livespec_runtime.github_auth.errors import GithubAppAuthError

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandResult,
    CommandRunner,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io_fabro_launcher import (
    WatchedFabroLauncher,
)

__all__: list[str] = [
    "GITHUB_TOKEN_ENV_VAR",
    "GithubTokenEnvRunner",
    "JournalFile",
    "ShellCommandRunner",
    "WatchedFabroLauncher",
    "utc_now_iso",
]

# The env var name `gh` (and the `gh auth git-credential` helper raw `git`
# uses) reads its token from; the run-config overlay projects the SAME name
# into the sandbox env table. A NAME, never a secret value.
GITHUB_TOKEN_ENV_VAR = "GH_TOKEN"  # noqa: S105 - env-var NAME, not a secret value


@dataclass(frozen=True, kw_only=True)
class ShellCommandRunner:
    """Production CommandRunner: subprocess.run with captured output."""

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
    ) -> CommandResult:
        try:
            completed = subprocess.run(  # noqa: S603 - argvs are Dispatcher-built, never shell
                argv,
                cwd=str(cwd),
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                check=False,
                env=None if env is None else {**os.environ, **env},
            )
        except subprocess.TimeoutExpired as exc:
            return CommandResult(
                exit_code=124,
                stdout=_decode(raw=exc.stdout),
                stderr=_decode(raw=exc.stderr) + f"\ntimeout after {timeout_seconds}s",
            )
        return CommandResult(
            exit_code=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )


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
        env: dict[str, str] | None = None,
    ) -> CommandResult:
        try:
            os.environ[GITHUB_TOKEN_ENV_VAR] = self.token()
        except GithubAppAuthError as error:
            return CommandResult(
                exit_code=1,
                stdout="",
                stderr=f"GitHub App token refresh failed (fail-closed): {error.detail}",
            )
        merged_env = {**(env or {}), GITHUB_TOKEN_ENV_VAR: os.environ[GITHUB_TOKEN_ENV_VAR]}
        return self.inner.run(argv=argv, cwd=cwd, timeout_seconds=timeout_seconds, env=merged_env)


@dataclass(frozen=True, kw_only=True)
class JournalFile:
    """Append-only JSONL journal; thread-safe across parallel dispatches."""

    path: Path
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def append(self, *, record: dict[str, object]) -> None:
        stamped: dict[str, object] = {"at": utc_now_iso(), **record}
        line = json.dumps(stamped, sort_keys=True) + "\n"
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as handle:
                _ = handle.write(line)


def utc_now_iso() -> str:
    """Current UTC time in ISO-8601 with seconds precision."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _decode(*, raw: object) -> str:
    if isinstance(raw, bytes):
        return raw.decode("utf-8", errors="replace")
    if isinstance(raw, str):
        return raw
    return ""
