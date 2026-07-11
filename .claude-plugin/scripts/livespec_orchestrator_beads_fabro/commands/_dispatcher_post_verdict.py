"""Out-of-band reflector post-verdict stage for the Dispatcher."""

from __future__ import annotations

import argparse
import os
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandRunner
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import reflector_oob_spans_path
from livespec_orchestrator_beads_fabro.commands._dispatcher_reflector_oob import (
    GitPrLessonsProposer,
    LessonsProposer,
    resolve_mode,
    resolve_reflector_budget_seconds,
    run_reflector_oob,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_self_update import post_verdict_runner

__all__: list[str] = [
    "ReflectorSpawn",
    "reflector_oob_after_verdict",
]


class ReflectorSpawn(Protocol):
    def __call__(self, *, body: Callable[[], None]) -> None: ...


def reflector_oob_after_verdict(  # noqa: PLR0913 — kw-only fail-open stage; seams are independently injectable.
    *,
    args: argparse.Namespace,
    repo: Path,
    journal: JournalFile,
    runner: CommandRunner | None = None,
    token_supplier: Callable[[], str] | None = None,
    lessons_proposer: LessonsProposer | None = None,
    spawn: ReflectorSpawn | None = None,
) -> None:
    """Fire the out-of-band LLM reflector as the 5th post-verdict stage (29f.4).

    Called AFTER the verdict / exit code is computed (alongside the
    ntfy-alarm, cost-gate, self-update, and mechanical-reflection stages)
    and is the LAST consumer leg of the 29f telemetry pipeline. The reflector
    runs in a daemon thread; `run_reflector_oob` is itself fail-OPEN, time-boxed,
    and default-OFF (the `LIVESPEC_REFLECTOR_OOB` lever), so on a plain dispatch
    this is a no-op that never raises and never touches the verdict.

    Daemon-lifetime reconciliation (29f.8 gap 2). The full cron/timer that is
    the reflector's eventual home is still DEFERRED; the minimal fix here is a
    lever-gated JOIN. A daemon thread dies when the dispatcher process exits, so
    a ~6-min review can never finish in the single-dispatch case — the time-box
    raise (gap 1) is meaningless without this. When the lever is ARMED
    (observe / file), the spawn JOINS the thread up to the stage budget (plus a
    small margin) so the reflector actually completes its review before the
    process exits. When the lever is OFF (the default), the body short-circuits
    inside `run_reflector_oob` immediately, so the fire-and-forget daemon adds
    NO delay — the plain-dispatch path is unchanged.

    `runner` / `lessons_proposer` are injectable for the hermetic test
    tier; production is the real `ShellCommandRunner` (the `claude -p` +
    git/gh subprocess seam) and `GitPrLessonsProposer` (the lessons-via-PR
    seam). `spawn` is injectable so the test tier runs the body
    SYNCHRONOUSLY instead of detaching a thread; production detaches a
    daemon thread. The OOB reflector writes its own verdict spans to a
    journal-sibling file the enrich stage forwards.
    """
    resolved_runner = post_verdict_runner(runner=runner, token_supplier=token_supplier)
    resolved_proposer = (
        lessons_proposer
        if lessons_proposer is not None
        else GitPrLessonsProposer(runner=resolved_runner)
    )
    spans_path = reflector_oob_spans_path(args=args, repo=repo)

    def _body() -> None:
        run_reflector_oob(
            repo=repo,
            journal=journal,
            spans_path=spans_path,
            runner=resolved_runner,
            lessons_proposer=resolved_proposer,
        )

    resolved_spawn = spawn if spawn is not None else _default_reflector_spawn()
    resolved_spawn(body=_body)


def _default_reflector_spawn() -> ReflectorSpawn:
    """Pick the daemon-thread spawn for the OOB reflector by lever state (29f.8 gap 2).

    OFF (default): the fire-and-forget daemon — the body short-circuits, so it
    adds no delay. ARMED (observe / file): a JOINING daemon bounded by the stage
    budget + margin, so the ~6-min review completes before the process exits
    (a daemon thread would otherwise be killed mid-review on a single dispatch).
    """
    mode = resolve_mode(raw=os.environ.get("LIVESPEC_REFLECTOR_OOB"))
    if mode == "off":
        return _spawn_daemon
    budget = resolve_reflector_budget_seconds(environ=dict(os.environ))
    join_timeout = budget + _REFLECTOR_JOIN_MARGIN
    return lambda body: _spawn_daemon_joining(body=body, join_timeout=join_timeout)


# Margin added to the stage budget for the lever-armed JOIN, so the join waits
# slightly longer than the reflector's own internal time-box (the reflector
# self-bounds; the join is a backstop, never the primary deadline).
_REFLECTOR_JOIN_MARGIN = 30.0


def _spawn_daemon(*, body: Callable[[], None]) -> None:
    """Run `body` in a fire-and-forget daemon thread (never blocks the loop)."""
    thread = threading.Thread(target=body, name="reflector-oob", daemon=True)
    thread.start()


def _spawn_daemon_joining(*, body: Callable[[], None], join_timeout: float) -> None:
    """Run `body` in a daemon thread and JOIN it up to `join_timeout` (29f.8 gap 2).

    The thread stays a daemon (a process exit still reaps it), but the JOIN
    holds the process open long enough for the armed reflector to finish its
    review — without it, a ~6-min review dies when the dispatcher exits. The
    join is bounded, so a wedged reflector never hangs the loop: on timeout the
    daemon is abandoned and the process proceeds to exit.
    """
    thread = threading.Thread(target=body, name="reflector-oob", daemon=True)
    thread.start()
    thread.join(timeout=join_timeout)
