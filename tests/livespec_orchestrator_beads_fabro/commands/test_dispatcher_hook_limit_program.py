"""The in-sandbox hook-limit observer, run as the sandbox runs it.

Binds the observation half of `SPECIFICATION/scenarios.md` Scenario 177's
over-limit-push sub-scenarios, for work-item ``bd-ib-xi63mq``.

THE PROGRAM IS EXECUTED, NOT TRANSCRIBED. It is a materialized string this
package never imports, so the only thing that can establish what it does is
running its exact bytes -- the discipline
`tests/.../test_dispatcher_publication_head.py` already applies to the
publication-head reader. A test that re-implemented the process walk in Python
and compared answers would be asserting agreement between two of its own
readings.

AND IT IS RUN AGAINST REAL PROCESS TREES AND THE REAL `/proc`, not a fabricated
one. The measurement the clause asks for -- a hook run's elapsed milliseconds,
taken from its own `starttime` against the boot clock -- is exactly the part a
synthetic `/proc` would get to define rather than test: a fixture author picks
the tick values, so the arithmetic would be graded against the fixture's idea of
them. A real sleeping descendant whose argv names a hook is cheap, and it is the
only version of this test that could fail if the tick conversion were wrong.
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_hook_limit_program import (
    HOOK_LIMIT_LIMITS_FILENAME,
    HOOK_LIMIT_PROGRAM_FILENAME,
    PUSH_OBSERVATION_RESERVE_SECONDS,
    hook_limit_limits_path_expansion,
    hook_limit_prepare_steps_block,
    hook_limit_program_path_expansion,
    hook_limit_program_source,
    publish_draft_limit_from_graph,
    push_observation_budget_seconds,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_hook_over_limit import (
    HOOK_OVER_LIMIT_SENTINEL,
    hook_over_limit_from_text,
)

_REPO_ROOT = Path(__file__).resolve().parents[3]
_GRAPH = (
    _REPO_ROOT
    / ".claude-plugin"
    / ".fabro"
    / "workflows"
    / "implement-work-item"
    / "workflow.fabro"
)


def _program(*, tmp_path: Path) -> Path:
    path = tmp_path / HOOK_LIMIT_PROGRAM_FILENAME
    _ = path.write_text(hook_limit_program_source(), encoding="utf-8")
    return path


# The child's environment, spelled out rather than inherited. An explicit env
# is what scrubs `COVERAGE_PROCESS_START` and `COV_CORE_*`, whose instrumented
# child races this suite's own coverage run -- the condition the
# `subprocess_spawn_allowlist` entry for this file is conditioned on.
def _child_env(*, tmp_path: Path) -> dict[str, str]:
    return {"PATH": "/usr/bin:/bin", "HOME": str(tmp_path)}


def _observe(*, program: Path, push_pid: int, extra: tuple[str, ...] = ()) -> tuple[int, str]:
    result = subprocess.run(
        [
            sys.executable,
            str(program),
            "--push-pid",
            str(push_pid),
            "--node",
            "publish_draft",
            "--operation",
            "push",
            "--hook-name",
            "pre-push",
            "--limit-seconds",
            "3600",
            *extra,
        ],
        capture_output=True,
        text=True,
        check=False,
        env=_child_env(tmp_path=program.parent),
    )
    return result.returncode, result.stderr


def _hook_script(*, tmp_path: Path, seconds: int) -> Path:
    """A stand-in pre-push hook, at a path whose argv names `hooks/pre-push`."""
    hooks = tmp_path / ".git" / "hooks"
    hooks.mkdir(parents=True, exist_ok=True)
    hook = hooks / "pre-push"
    _ = hook.write_text(f"#!/bin/sh\nsleep {seconds}\n", encoding="utf-8")
    hook.chmod(0o755)
    return hook


def _delegating_hook_script(*, tmp_path: Path, seconds: int) -> Path:
    """A stand-in pre-push hook shaped like THIS repository's: it EXECS away.

    `.git/hooks/pre-push` here ends in
    `exec mise exec -- lefthook run --no-auto-install "$hook_name" "$@"`, so by
    the time the full suite is running -- the part that outlives a limit -- the
    hook process's own argv names the DELEGATE and carries the hook name as an
    argument, and no longer names the installed hook's path at all. The
    delegate's work is a child, so a reader that cannot see the exec'd process
    has no later-starting fallback to under-report either.
    """
    hooks = tmp_path / ".git" / "hooks"
    hooks.mkdir(parents=True, exist_ok=True)
    delegate = tmp_path / "hook-runner-stand-in"
    _ = delegate.write_text(f"#!/bin/sh\nsleep {seconds}\n", encoding="utf-8")
    delegate.chmod(0o755)
    hook = hooks / "pre-push"
    _ = hook.write_text(
        f'#!/bin/sh\nexec "{delegate}" run --no-auto-install pre-push "$@"\n',
        encoding="utf-8",
    )
    hook.chmod(0o755)
    return hook


def test_a_hook_still_running_at_the_limit_is_reported_with_its_elapsed_time(
    tmp_path: Path,
) -> None:
    """Scenario 177: the event names the node, the operation, the limit, the elapsed."""
    hook = _hook_script(tmp_path=tmp_path, seconds=30)
    # A stand-in push: a shell that runs the hook as a CHILD. The trailing
    # `true` is what stops the shell exec-ing into the hook and collapsing the
    # two into one process, which is the shape a real `git push` never has.
    push = subprocess.Popen(["sh", "-c", f"{hook}; true"])
    try:
        time.sleep(2)
        code, stderr = _observe(program=_program(tmp_path=tmp_path), push_pid=push.pid)
    finally:
        push.kill()
        _ = push.wait()

    assert code == 0, stderr
    event = hook_over_limit_from_text(text=stderr)
    assert event is not None, stderr
    assert (event.node, event.operation, event.limit_seconds) == ("publish_draft", "push", 3600)
    # A real measurement rather than a constant: the hook had been running for
    # about two seconds, and an implementation that reported zero, or the
    # push's own age, or the limit, would all fail this band.
    assert 1_000 <= event.hook_elapsed_ms <= 20_000, event.hook_elapsed_ms


def test_a_hook_that_execs_into_a_delegate_is_still_found_and_named(
    tmp_path: Path,
) -> None:
    """Scenario 177: the event is named for the hook shape this repository runs.

    THE DISCRIMINATING CASE. A reader keyed on the installed hook's PATH cannot
    return a hit here however healthy it is, and its miss is silent twice over:
    the node swallows the observer's exit, so the publication still fails closed
    but UNNAMED -- no row, no cause -- which is exactly the unexplained
    needs-human ending Scenario 177 exists to prevent.

    The non-exec case above is kept as the control, so this is not one blind spot
    traded for another: both shapes must be reported.
    """
    hook = _delegating_hook_script(tmp_path=tmp_path, seconds=30)
    push = subprocess.Popen(["sh", "-c", f"{hook}; true"])
    try:
        time.sleep(2)
        code, stderr = _observe(program=_program(tmp_path=tmp_path), push_pid=push.pid)
    finally:
        push.kill()
        _ = push.wait()

    assert code == 0, stderr
    event = hook_over_limit_from_text(text=stderr)
    assert event is not None, stderr
    assert (event.node, event.operation, event.limit_seconds) == ("publish_draft", "push", 3600)
    # The same real measurement the non-exec case asserts, and here it also
    # pins WHICH process was taken as the hook run's root: the delegate's own
    # `sleep` child starts last and would report near zero.
    assert 1_000 <= event.hook_elapsed_ms <= 20_000, event.hook_elapsed_ms


def test_a_push_with_no_hook_running_reports_no_event(tmp_path: Path) -> None:
    """Scenario 177: a push ended after its hook finished is not this event."""
    push = subprocess.Popen(["sh", "-c", "sleep 30; true"])
    try:
        time.sleep(1)
        code, stderr = _observe(program=_program(tmp_path=tmp_path), push_pid=push.pid)
    finally:
        push.kill()
        _ = push.wait()

    assert code == 1
    assert HOOK_OVER_LIMIT_SENTINEL not in stderr
    assert "is not a hook-over-limit event" in stderr


def test_an_unmeasurable_elapsed_time_reports_no_invented_figure(tmp_path: Path) -> None:
    """A hook that WAS running but could not be timed yields no event.

    The discriminating arm: the observer has found its hook run, so the easy
    coding is to report the event with a zero or a guessed elapsed figure. The
    clause asks for the hook run's elapsed milliseconds, and a record carrying
    an invented one is worse than no record -- so `uptime` being unreadable
    withholds the event. Reproduced by pointing the reader at a proc root that
    carries the process table it needs and NO `uptime`.
    """
    hook = _hook_script(tmp_path=tmp_path, seconds=30)
    push = subprocess.Popen(["sh", "-c", f"{hook}; true"])
    proc_root = tmp_path / "proc"
    proc_root.mkdir()
    try:
        time.sleep(1)
        # SYMLINK each process entry rather than copying its bytes: a symlink
        # never reads the file, so this loop needs no "the process exited while
        # I was walking" arm -- an arm whose execution the case could not
        # control anyway. `uptime` is simply never linked, which is the one
        # reading the observer must fail to take.
        for entry in Path("/proc").iterdir():
            if entry.name.isdigit():
                (proc_root / entry.name).symlink_to(entry)
        code, stderr = _observe(
            program=_program(tmp_path=tmp_path),
            push_pid=push.pid,
            extra=("--proc-root", str(proc_root)),
        )
    finally:
        push.kill()
        _ = push.wait()

    assert code == 1
    assert HOOK_OVER_LIMIT_SENTINEL not in stderr
    assert "could not be measured" in stderr


def test_a_malformed_invocation_refuses_rather_than_reporting(tmp_path: Path) -> None:
    """Usage errors exit 2 and report nothing, so a broken call is not an event."""
    result = subprocess.run(
        [sys.executable, str(_program(tmp_path=tmp_path)), "--push-pid", "1"],
        capture_output=True,
        text=True,
        check=False,
        env=_child_env(tmp_path=tmp_path),
    )
    assert result.returncode == 2
    assert HOOK_OVER_LIMIT_SENTINEL not in result.stderr

    not_an_integer = subprocess.run(
        [
            sys.executable,
            str(_program(tmp_path=tmp_path)),
            "--push-pid",
            "not-a-pid",
            "--node",
            "publish_draft",
            "--operation",
            "push",
            "--hook-name",
            "pre-push",
            "--limit-seconds",
            "3600",
        ],
        capture_output=True,
        text=True,
        check=False,
        env=_child_env(tmp_path=tmp_path),
    )
    assert not_an_integer.returncode == 2
    assert "must be integers" in not_an_integer.stderr


def test_the_push_bound_sits_below_the_limit_and_never_reaches_zero() -> None:
    """The reserve is subtracted, and a tiny limit still leaves a real bound."""
    assert push_observation_budget_seconds(limit_seconds=3600) == (
        3600 - PUSH_OBSERVATION_RESERVE_SECONDS
    )
    assert push_observation_budget_seconds(limit_seconds=1800) == (
        1800 - PUSH_OBSERVATION_RESERVE_SECONDS
    )
    # A limit smaller than the reserve must not floor to zero: a zero bound
    # falls through the node's wait before the push can start, which would
    # report every push as over-limit at no elapsed time at all.
    assert push_observation_budget_seconds(limit_seconds=5) == 1
    assert push_observation_budget_seconds(limit_seconds=PUSH_OBSERVATION_RESERVE_SECONDS) == 1


def test_the_limit_is_read_off_the_graph_and_withheld_when_it_cannot_be(
    tmp_path: Path,
) -> None:
    """The figure comes from the artifact the run executes, or from nothing."""
    assert publish_draft_limit_from_graph(graph=_GRAPH) == 1800

    assert publish_draft_limit_from_graph(graph=tmp_path / "absent.fabro") is None

    no_node = tmp_path / "no-node.fabro"
    _ = no_node.write_text('digraph g {\n  other [\n timeout="900s"\n ]\n}\n', encoding="utf-8")
    assert publish_draft_limit_from_graph(graph=no_node) is None

    no_timeout = tmp_path / "no-timeout.fabro"
    _ = no_timeout.write_text(
        'digraph g {\n  publish_draft [\n label="x"\n ]\n}\n', encoding="utf-8"
    )
    assert publish_draft_limit_from_graph(graph=no_timeout) is None

    unparseable = tmp_path / "unparseable.fabro"
    _ = unparseable.write_text(
        'digraph g {\n  publish_draft [\n timeout="soon"\n ]\n}\n', encoding="utf-8"
    )
    assert publish_draft_limit_from_graph(graph=unparseable) is None


def test_the_prepare_step_lands_the_program_and_withholds_unknown_figures() -> None:
    """The program is always materialized; the figures only when they are known."""
    known = hook_limit_prepare_steps_block(limit_seconds=3600)

    assert HOOK_LIMIT_PROGRAM_FILENAME in known
    assert HOOK_LIMIT_LIMITS_FILENAME in known
    assert "LIVESPEC_PUBLISH_DRAFT_LIMIT_SECONDS=3600" in known
    assert "LIVESPEC_PUBLISH_DRAFT_PUSH_BUDGET_SECONDS=3480" in known
    # The sentinel reaches the sandbox as ONE spelling, substituted rather than
    # typed: a program carrying `__SENTINEL__` would print a line the host
    # parser cannot match, and the event would be observed and then lost.
    assert HOOK_OVER_LIMIT_SENTINEL in known
    assert "__SENTINEL__" not in known

    withheld = hook_limit_prepare_steps_block(limit_seconds=None)

    assert HOOK_LIMIT_PROGRAM_FILENAME in withheld
    assert HOOK_LIMIT_LIMITS_FILENAME not in withheld
    assert "LIVESPEC_PUBLISH_DRAFT_PUSH_BUDGET_SECONDS" not in withheld


def test_the_node_and_the_prepare_step_resolve_one_root() -> None:
    """A node resolving a different root than the prepare pass finds no program."""
    assert hook_limit_program_path_expansion().endswith(f"/{HOOK_LIMIT_PROGRAM_FILENAME}")
    assert hook_limit_limits_path_expansion().endswith(f"/{HOOK_LIMIT_LIMITS_FILENAME}")
    shared = hook_limit_program_path_expansion().rsplit("/", 1)[0]
    assert hook_limit_limits_path_expansion().rsplit("/", 1)[0] == shared
    assert shared in hook_limit_prepare_steps_block(limit_seconds=3600)
