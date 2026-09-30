"""Replaying ACP fallback event projection during a reconciliation pass.

`SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback
priority": "The Dispatcher MUST fetch events from the run's resolved
factory target, project by stable event id, calculate holds from
occurrence time, and REPLAY PROJECTION DURING RECONCILIATION", and the
projection-failure fact "clears only after successful idempotent
projection for the run/node".

THE REPLAY SET IS THE FAILURES, NOT THE INVENTORY, and that choice is
what makes this affordable. A busy factory carries hundreds of rows in
`ps -a`; projecting every one of them on every tick would put hundreds
of `fabro events` calls on a pass that exists to free scheduler slots.
What actually needs replaying is precisely what did not read the first
time -- the unresolved projection-failure facts -- because a successful
first read already wrote its holds and its warnings, and re-reading it
would append nothing (first write wins on the stable event id).

A TARGETED PASS ALSO REPLAYS ITS OWN ITEM. `reconcile_runs_for_item`
narrows to one work-item, and the natural reason to call it is that
something about that item went wrong; replaying its newest journaled run
there costs one fetch and is the cheapest way for a per-item recovery to
also repair that item's projection.

THE FACTORY IS PASSED DOWN, NEVER RE-RESOLVED. The reconciler is already
iterating one declared factory and has surveyed it through that
factory's own target, so the replay reads events from the same host. Re-
resolving would let a replay ask the repository default about a run that
lives on the other factory, where the answer is a clean, plausible "no
such run" -- the wrong-population trap arriving through a default.
"""

from __future__ import annotations

from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._acp_projection_failure import (
    unresolved_projection_failures,
)
from livespec_orchestrator_beads_fabro.commands._acp_projection_run import (
    AcpProjectionRequest,
    project_run_events,
)
from livespec_orchestrator_beads_fabro.commands._config import FactoryTarget
from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_runs_inputs import (
    ReconcileInputs,
)

__all__: list[str] = [
    "replay_acp_projection",
    "replay_targets",
]

_JOURNAL_SUBPATH = ("tmp", "fabro-dispatch-journal.jsonl")


def replay_targets(
    *, inputs: ReconcileInputs, factory: FactoryTarget, journal_path: Path
) -> tuple[tuple[str, str], ...]:
    """The `(run_id, work_item_id)` pairs this factory's replay must re-read.

    A failure whose run is not journaled to any work-item is skipped
    rather than replayed under a guessed id: the projection writes the
    item id into every hold observation it mints, and attributing one
    outage to the wrong item is worse than leaving the fact standing for
    a human to read.
    """
    targets: dict[str, str] = {}
    for failure in unresolved_projection_failures(journal_path=journal_path):
        if failure.factory_name != factory.name:
            continue
        item_id = inputs.journaled.item_id_by_run.get(failure.run_id)
        if item_id is not None:
            targets[failure.run_id] = item_id
    only = inputs.only_work_item_id
    if only is not None:
        run_id = inputs.journaled.newest_run_id_by_item.get(only)
        if run_id is not None:
            targets[run_id] = only
    return tuple(sorted(targets.items()))


def replay_acp_projection(*, inputs: ReconcileInputs, factory: FactoryTarget) -> int:
    """Re-read and re-project every run this factory still owes a projection.

    Returns how many runs were replayed, which is what the caller
    journals; the projection itself records its own outcome per run, so
    a count here is a summary rather than a second authority on what
    happened.
    """
    journal_path = inputs.repo.joinpath(*_JOURNAL_SUBPATH)
    replayed = 0
    for run_id, work_item_id in replay_targets(
        inputs=inputs, factory=factory, journal_path=journal_path
    ):
        _ = project_run_events(
            request=AcpProjectionRequest(
                repo=inputs.repo,
                repo_name=inputs.repo.name,
                work_item_id=work_item_id,
                run_id=run_id,
                journal_path=journal_path,
            ),
            journal=inputs.journal,
            runner=inputs.runner,
            factory=factory,
        )
        replayed += 1
    return replayed
