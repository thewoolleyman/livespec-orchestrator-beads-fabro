"""A terminal sentinel the client printed outranks an inspect that never answered.

The sentinel is positive proof the run ENDED, and on the pinned engine the
client's own stderr is the only channel that carries it: an unanswered inspect
leaves `inspect.failure` empty, so a `run-unobservable` outcome here would
discard the one verdict in hand. Every disposition downstream — the ledger
valve, the durable needs-human cause comment, the preserved-ref record and the
non-convergence cap — gates on a `blocked` or `failed` status, so a shadowed
sentinel rests the item at `active` with none of them written.
"""

from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_dead_implementer import (
    DEAD_IMPLEMENTER_SENTINEL,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandResult,
    PollPolicy,
    run_dispatch,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import (
    NEEDS_HUMAN_MARKER,
    NON_CONVERGED_MARKER,
)

from tests.livespec_orchestrator_beads_fabro.commands.test_dispatcher_fabro_reattach import (
    Journal,
    Runner,
)
from tests.livespec_orchestrator_beads_fabro.commands.test_dispatcher_fabro_reattach_deadline import (
    plan_for_test,
)


@pytest.mark.parametrize(
    ("sentinel_line", "expected_status", "detail_fragment"),
    [
        (
            f"{NEEDS_HUMAN_MARKER}: the acceptance criteria name a scenario heading",
            "blocked",
            "the acceptance criteria name a scenario heading",
        ),
        (
            f"{NON_CONVERGED_MARKER}: the review loop did not converge",
            "failed",
            f"{NON_CONVERGED_MARKER}: the review loop did not converge",
        ),
        (
            f"{DEAD_IMPLEMENTER_SENTINEL}: implementer left the worktree unchanged",
            "failed",
            f"{DEAD_IMPLEMENTER_SENTINEL}: implementer left the worktree unchanged",
        ),
    ],
)
def test_client_terminal_sentinel_outranks_an_unanswered_inspect(
    *, tmp_path: Path, sentinel_line: str, expected_status: str, detail_fragment: str
) -> None:
    runner = Runner(
        replies=[
            CommandResult(exit_code=1, stdout="Run: 01DROPPED\n", stderr=sentinel_line),
            *[CommandResult(exit_code=1, stdout="", stderr="server request timed out after 30s")]
            * 12,
        ]
    )
    outcome = run_dispatch(
        plan=plan_for_test(repo=tmp_path),
        runner=runner,
        journal=Journal(),
        sleep=lambda _seconds: None,
        poll=PollPolicy(attempts=1, interval_seconds=0),
    )
    assert (outcome.status, outcome.stage) == (expected_status, "fabro-run")
    assert outcome.fabro_run_id == "01DROPPED"
    assert detail_fragment in outcome.detail


def test_dead_implementer_sentinel_still_carries_its_governing_condition(*, tmp_path: Path) -> None:
    runner = Runner(
        replies=[
            CommandResult(
                exit_code=1,
                stdout="Run: 01DROPPED\n",
                stderr=f"{DEAD_IMPLEMENTER_SENTINEL}: implementer left the worktree unchanged",
            ),
            *[CommandResult(exit_code=1, stdout="", stderr="inspect timed out")] * 12,
        ]
    )
    outcome = run_dispatch(
        plan=plan_for_test(repo=tmp_path),
        runner=runner,
        journal=Journal(),
        sleep=lambda _seconds: None,
        poll=PollPolicy(attempts=1, interval_seconds=0),
    )
    assert outcome.dead_implementer_condition == "dead_implementer_unchanged_tree"
