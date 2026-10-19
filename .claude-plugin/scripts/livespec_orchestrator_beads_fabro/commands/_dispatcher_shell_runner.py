"""The production `CommandRunner`, and the child environment it builds.

Split out of `_dispatcher_io` to break an IMPORT CYCLE the whole-run wall
budget's arm closed, and the cycle is worth recording because the shape recurs:
`_dispatcher_io` is both a DEFINITION site and a FACADE — it defines this runner
and the journal, and re-exports `WatchedFabroLauncher`. So anything the launcher
reaches that needed the runner imported the facade back, and the facade was
already mid-initialization. The budget's export chain
(`_dispatcher_run_wall_budget_preserve` -> the run reference export ->
`_dispatcher_preserve_reference`) is what first reached it.

Extracting the runner to a LEAF is the fix rather than a lazy import at the one
call site, because the cycle is a property of the layout and not of that call.
`_dispatcher_io` still RE-EXPORTS both names, because almost every caller reaches
for them through that facade and re-pointing all of them would be a churn no
reader benefits from. What the re-export does NOT license is importing them from
the facade inside the launcher's own import reach: that is where the cycle
closes, and `_dispatcher_preserve_reference` imports this module directly for
exactly that reason. A module added to that chain must do the same -- the symptom
is a loud `ImportError` at collection, never a silent one.

`ShellCommandRunner` converts both a TIMEOUT (exit 124) and an ABSENT
EXECUTABLE (exit 127) into non-zero `CommandResult`s, because the engine treats
every failure as routable data and the runner never lets an expected failure
escape as an exception. The absent-executable mapping is what keeps the
post-verdict self-update's fail-open invariant intact on a host whose PATH lacks
`gh`: an unresolvable binary skips the stage exactly as a `gh` ERROR does.
"""

from __future__ import annotations

import os
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt

__all__: list[str] = [
    "ShellCommandRunner",
    "child_env",
]


def child_env(*, delta: Mapping[str, str | None]) -> dict[str, str]:
    """This process's environment with `delta` applied: strings SET, `None` REMOVES.

    The removal arm is what lets a caller ask for a child WITHOUT a variable
    this process carries. A mapping merged over `os.environ` cannot express
    that, and the alternative -- deleting the name from `os.environ` around the
    call -- would reach every other dispatch running in this process, since
    `dispatcher.py loop --parallel` drives its wave through a thread pool.
    Removing a name this process does not carry is a no-op, so a caller may
    name its whole scrub set without first asking which members are present.
    """
    resolved = dict(os.environ)
    for name, value in delta.items():
        if value is None:
            _ = resolved.pop(name, None)
        else:
            resolved[name] = value
    return resolved


@dataclass(frozen=True, kw_only=True)
class ShellCommandRunner:
    """Production CommandRunner: subprocess.run with captured output."""

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: Mapping[str, str | None] | None = None,
        stdin: int | None = None,
        start_new_session: bool = False,
    ) -> CommandResult:
        completed = attempt(
            action=lambda: subprocess.run(  # noqa: S603 - argvs are Dispatcher-built, never shell
                argv,
                cwd=str(cwd),
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                check=False,
                env=None if env is None else child_env(delta=env),
                stdin=stdin,
                start_new_session=start_new_session,
            ),
            exceptions=(subprocess.TimeoutExpired, FileNotFoundError),
        )
        if isinstance(completed, AttemptFailure):
            return _failure_result(
                error=completed.error,
                argv=argv,
                timeout_seconds=timeout_seconds,
            )
        return CommandResult(
            exit_code=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )


def _failure_result(
    *,
    error: Exception,
    argv: list[str],
    timeout_seconds: float,
) -> CommandResult:
    """Map a caught runner exception onto a non-zero `CommandResult`.

    Both branches keep the failure as routable DATA rather than letting it
    escape: a TIMED-OUT command becomes exit 124, and a command whose
    EXECUTABLE IS ABSENT becomes exit 127 (the POSIX command-not-found
    convention). The absent case matters to every post-verdict probe that
    shells through this runner: callers receive data they can journal or
    classify instead of crashing the dispatch with a `FileNotFoundError`.
    """
    if isinstance(error, FileNotFoundError):
        return CommandResult(
            exit_code=127,
            stdout="",
            stderr=f"executable not found: {argv[0]}: {error}",
        )
    exc = cast("subprocess.TimeoutExpired", error)
    return CommandResult(
        exit_code=124,
        stdout=_decode(raw=exc.stdout),
        stderr=_decode(raw=exc.stderr) + f"\ntimeout after {timeout_seconds}s",
    )


def _decode(*, raw: object) -> str:
    if isinstance(raw, bytes):
        return raw.decode("utf-8", errors="replace")
    if isinstance(raw, str):
        return raw
    return ""
