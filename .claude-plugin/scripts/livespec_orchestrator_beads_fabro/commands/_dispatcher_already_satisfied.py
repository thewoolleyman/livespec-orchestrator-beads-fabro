"""The already-satisfied ending, as the Dispatcher reads it and rests the item on it.

The workflow's `already_satisfied` node is the sandbox half: a `red` turn that found the
Definition of Done already holding on the dispatch base ends there, and the node prints
one `LIVESPEC_ALREADY_SATISFIED:` line naming the dispatch base once it has proved the
tree unchanged against it. This module is the Dispatcher half. A run that ends this way
is a correct no-op rather than a dead implementer, so it takes its own outcome and its
own journal row, never the generic truncation record. The ledger half, which rests the
item, lives in `_dispatcher_already_satisfied_rest` because it imports the lifecycle seam
and this module is imported by the engine.

THE PATTERN REQUIRES A FULL DISPATCH-BASE SHA after `base=`. The node's script source
carries the same sentinel followed by a shell substitution, so any listing of the
workflow text can never be read as the ending.

THE ENGINE FOLDS THIS ENDING AS A FAILED RUN. Production Fabro (v0.393, bbe693847)
links petri c6bfd5e38, whose attractor frontend sets `Completion::TerminalNode(exit)`,
and the engine folds a run to Success only when `exit` holds a success-like record.
`already_satisfied` has no edge to `exit` (only `verify_pr` may lead there, which is
the publish guard), so a proved ending reaches the Dispatcher with a failed terminal.
For such a run the ending is read off ONE record: the run's FINAL step-ending record,
which must be `already_satisfied` itself with a success verdict, and only that
node's own output. A sentinel quoted anywhere else never qualifies.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, cast

from livespec_orchestrator_beads_fabro.commands._fabro_executed_candidate import graph_node_id

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
    from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import DispatchPlan

__all__: list[str] = [
    "ALREADY_SATISFIED_NODE",
    "ALREADY_SATISFIED_SENTINEL",
    "ALREADY_SATISFIED_STAGE",
    "already_satisfied_base_from_text",
    "already_satisfied_outcome",
    "already_satisfied_route",
    "final_step_output",
]

ALREADY_SATISFIED_SENTINEL = "LIVESPEC_ALREADY_SATISFIED"
ALREADY_SATISFIED_STAGE = "already-satisfied"
ALREADY_SATISFIED_NODE = "already_satisfied"

# The Petri-era record of a step's ending, MEASURED on run 01M7AFVCPSK2GT0W2SWXP3258Z
# (`implement_commit_settle@1`, a succeeded command step of the pre-split graph): the
# envelope names the node at `item.subject.node.name`, the event at
# `item.record.body.event` is `step.finished` (matched as a suffix, as
# `_dispatcher_terminal_events` does), the verdict is
# `outcome.status == "success"` (a failed step nests a block there instead), and the
# script's output, with its stderr merged in, is `outcome.output.stdout`. That run's step
# carried `github-token source:` lines, which the minting helper writes to stderr.
_STEP_FINISHED = "step.finished"
_SUCCESS = "success"

_EVENT_PATTERN = re.compile(
    re.escape(ALREADY_SATISFIED_SENTINEL) + r": base=(?P<base>[0-9a-f]{40}) "
)


def already_satisfied_base_from_text(*, text: str) -> str | None:
    """The dispatch base the last ending line names, or None when a run printed none."""
    matches = list(_EVENT_PATTERN.finditer(text))
    return matches[-1].group("base") if matches else None


def _mapping(*, value: object) -> dict[str, object]:
    return cast("dict[str, object]", value) if isinstance(value, dict) else {}


def _final_step(*, payload: object) -> tuple[str, dict[str, object]] | None:
    """The run's last step-ending record, as (node, verdict), or None when none is readable."""
    if not isinstance(payload, list):
        return None
    final: tuple[str, dict[str, object]] | None = None
    for raw in cast("list[object]", payload):
        item = _mapping(value=_mapping(value=raw).get("item"))
        body = _mapping(value=_mapping(value=item.get("record")).get("body"))
        event = body.get("event")
        node = _mapping(value=_mapping(value=item.get("subject")).get("node")).get("name")
        if isinstance(event, str) and event.endswith(_STEP_FINISHED) and isinstance(node, str):
            final = (node, _mapping(value=body.get("outcome")))
    return final


def final_step_output(*, payload: object, node: str) -> str:
    """The FINAL step's own output when that step is `node` and it succeeded, else "".

    Only the last step-ending record of the run is read, so a sentinel quoted by an
    earlier step, by another node, or anywhere in the run's text never qualifies.
    """
    final = _final_step(payload=payload)
    if final is None or graph_node_id(node=final[0]) != node:
        return ""
    verdict = final[1]
    stdout = _mapping(value=verdict.get("output")).get("stdout")
    if verdict.get("status") != _SUCCESS or not isinstance(stdout, str):
        return ""
    return stdout


def already_satisfied_route(*, work_item_id: str) -> str:
    return (
        f"to obtain its Proof of Done, run reconcile-merged for {work_item_id} when a merged "
        "pull request for the item exists, and otherwise start a proof-only run against the "
        "dispatch base"
    )


def already_satisfied_outcome(
    *,
    outcome_type: type[DispatchOutcome],
    plan: DispatchPlan,
    run_id: str | None,
    terminal: DispatchOutcome | None,
    text: str,
    events_payload: object | None,
) -> DispatchOutcome | None:
    """The outcome of a run that ended as already satisfied, or None for any other run.

    A run the engine ended green is read from its text. A run the engine folded
    non-green is read ONLY off its final step record (`final_step_output`), because the
    engine folds the `already_satisfied` dead end as failed; any other non-green run
    keeps its own terminal outcome whatever its output quoted.
    """
    source = (
        text
        if terminal is None
        else final_step_output(payload=events_payload, node=ALREADY_SATISFIED_NODE)
    )
    base = already_satisfied_base_from_text(text=source)
    if base is None:
        return None
    return outcome_type(
        work_item_id=plan.work_item_id,
        status="green",
        stage=ALREADY_SATISFIED_STAGE,
        pr_number=None,
        merge_sha=None,
        detail=(
            f"already satisfied: the Definition of Done of {plan.work_item_id} already holds on "
            f"dispatch base {base}, so no Red test was written and no pull request was opened; "
            f"{already_satisfied_route(work_item_id=plan.work_item_id)}"
        ),
        fabro_run_id=run_id,
        already_satisfied_base=base,
    )
