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

`ShellCommandRunner` converts a TIMEOUT (exit 124), an ABSENT EXECUTABLE (exit
127) and a launch the operating system REFUSES (exit 126) into non-zero
`CommandResult`s, because the engine treats every failure as routable data and
the runner never lets an expected failure escape as an exception. The
absent-executable mapping is what keeps the post-verdict self-update's fail-open
invariant intact on a host whose PATH lacks `gh`: an unresolvable binary skips
the stage exactly as a `gh` ERROR does.

THE THIRD ARM IS THE WHOLE `OSError` CLASS, and it is the repair of a measured
dispatcher crash. `FileNotFoundError` used to be the only `OSError` this runner
named, so every other launch failure escaped as a bug-class exception: `E2BIG`
from an argv entry past Linux's 131072-byte `MAX_ARG_STRLEN` cap, `EACCES` from
a file without the execute bit, `ENOTDIR` from an unusable working directory.
None of those is a bug — each is an environmental condition a caller must
classify — and the one that fired was `E2BIG`, from the Definition-of-Done
judgement, which passes its whole prompt as ONE argv entry and inlines the
verbatim body of every specification heading an item's reference line names. An
item citing a large governing heading therefore crashed the pre-dispatch wall,
the intake routing and the approve valve, on exactly the condition those paths
are required to treat as "the judgement could not run".

126 rather than 127, because the two have DIFFERENT REMEDIES and only one
caller-visible value distinguishes them: 127 is the POSIX command-not-found
convention and the judgement reads it as a missing judge, so an uninvokable
command reported as 127 would send an operator to install a binary that is
already there. 126 is the POSIX "command found but could not be executed"
counterpart, and every caller already reads any non-zero exit as a failure.
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
            # `OSError` rather than `FileNotFoundError`, which is one of its
            # subclasses: every launch failure the operating system reports
            # arrives as an `OSError`, and the narrower tuple let the rest of
            # them escape as bug-class exceptions.
            exceptions=(subprocess.TimeoutExpired, OSError),
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

    All three branches keep the failure as routable DATA rather than letting it
    escape: a TIMED-OUT command becomes exit 124, a command whose EXECUTABLE IS
    ABSENT becomes exit 127 (the POSIX command-not-found convention), and a
    command the operating system refuses to LAUNCH becomes exit 126 (its
    found-but-not-executable counterpart). The absent case matters to every
    post-verdict probe that shells through this runner: callers receive data
    they can journal or classify instead of crashing the dispatch with a
    `FileNotFoundError`.

    THE ORDER OF THE FIRST TWO ARMS IS LOAD-BEARING. `FileNotFoundError` is an
    `OSError`, so a generic arm placed first would swallow it and report every
    absent executable as 126 — collapsing the one code `_invocation_cause`
    reads as `no-eligible-model` into the one it reads as a failed command.

    The ERRNO MESSAGE rides the generic arm's stderr, because the exit code
    alone cannot say which refusal it was: an oversized argument list and a
    missing execute bit are both 126 here and have nothing in common as
    remedies, so the operating system's own account of the fault is the only
    thing that points an operator anywhere.
    """
    if isinstance(error, FileNotFoundError):
        return CommandResult(
            exit_code=127,
            stdout="",
            stderr=f"executable not found: {argv[0]}: {error}",
        )
    if isinstance(error, OSError):
        return CommandResult(
            exit_code=126,
            stdout="",
            stderr=f"command could not be invoked: {argv[0]}: {error}",
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
