"""Dispatcher ledger escalation for Fabro human-gate blocked outcomes.

THE LEDGER WRITE IS ONE ACT FOR EVERY ENDING AND THE STDERR LINE IS NOT. The
item rests at `blocked` / `needs-human` whatever routed it there, so nothing
below branches on the ending before writing. What does branch is the SURFACE
line, because `drive` captures this stream beside the dispatch `stdout_json`
and both reach one operator in one result: while a single wording served all
three endings, a transport fault produced a result whose detail said no agent
asked anything and whose stderr said the run was parked at a human gate. The
contradiction is not merely untidy — the incorrect half is the half that names
an action, so it is the half an operator acts on.
"""

from __future__ import annotations

from pathlib import Path

from livespec_orchestrator_beads_fabro._store_blocked_mutations import (
    update_work_item_blocked_state,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import store_config
from livespec_orchestrator_beads_fabro.commands._fabro_causal_stage import (
    STAGE_FAILURE,
    UNESTABLISHED,
)
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt
from livespec_orchestrator_beads_fabro.errors import (
    BeadsCommandError,
    BeadsConnectionError,
    BeadsMappingError,
    BeadsTenantMissingError,
    WorkItemNotFoundError,
)
from livespec_orchestrator_beads_fabro.io import write_stderr
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = ["escalate_needs_human_block"]

_LEDGER_WRITE_ERRORS = (
    WorkItemNotFoundError,
    BeadsCommandError,
    BeadsConnectionError,
    BeadsMappingError,
    BeadsTenantMissingError,
)


def escalate_needs_human_block(
    *,
    repo: Path,
    item: WorkItem,
    outcome: DispatchOutcome,
    journal: JournalFile,
) -> None:
    """Persist a Fabro human-gate terminal as blocked/needs-human.

    A Fabro `blocked` terminal means the implementation run reached an in-loop
    human gate. Persist that as a Dispatcher-level terminal ledger state, not as
    `backlog`: the item remains unavailable to autonomous admission until a
    human valve deliberately clears the block.
    """
    if outcome.status != "blocked":
        return
    if item.status == "blocked" and item.blocked_reason == "needs-human":
        return
    updated = attempt(
        action=lambda: update_work_item_blocked_state(
            path=store_config(repo=repo),
            item_id=item.id,
            status="blocked",
            blocked_reason="needs-human",
            admission_policy="manual",
        ),
        exceptions=_LEDGER_WRITE_ERRORS,
    )
    if isinstance(updated, AttemptFailure):
        journal.append(
            record={
                "stage": "needs-human-blocked-error",
                "work_item_id": item.id,
                "reason": f"{type(updated.error).__name__}",
            }
        )
        return
    journal.append(
        record={
            "stage": "needs-human-blocked",
            "work_item_id": item.id,
            "reason": "needs-human",
            "outcome_stage": outcome.stage,
            "outcome_status": outcome.status,
        }
    )
    _ = write_stderr(text=_surface_line(item_id=item.id, kind=outcome.needs_human_kind))


def _surface_line(*, item_id: str, kind: str | None) -> str:
    """The one line this escalation writes to the stream `drive` captures.

    THE VALVE IS NAMED IN EVERY ARM and the lifecycle never moves: the item
    rests at `blocked` / `needs-human` and `resolve-blocked:<id>:ready` is the
    only route out. What the arms disagree about is whether a QUESTION is
    pending — which is what the reader goes looking for, and the thing a single
    wording had to be wrong about for two of the three endings.

    THE GATE WORDING IS THE FALLTHROUGH, and it serves three inputs that are
    not the same thing. A genuine `AGENT_REQUEST` belongs there on its merits —
    an agent asked, a human has something to decide, and that ending was never
    the one mis-rendered, so its line stays byte-identical. An ABSENT verdict
    belongs there because every caller reporting none is a path that never
    reached the Fabro terminal mapper and therefore has no evidence either way;
    routing it into an attributed arm would make this change a silent rewording
    of endings it does not describe. And an UNMODELLED value belongs there
    because the two attributed arms each make a positive claim about what
    happened, so a verdict this function does not recognise must not be
    assigned one — which is also why they are tested FIRST and the gate is
    reached by falling past them, rather than the gate being tested for.
    """
    valve = f"`resolve-blocked:{item_id}:ready`"
    if kind == STAGE_FAILURE:
        return (
            f"SURFACE: work-item {item_id} reached the Fabro needs-human terminal "
            "after a non-retryable stage fault; no agent asked anything, so no "
            "answer is owed — marked blocked/needs-human; triage the failure named "
            f"in the dispatch detail, then release it with {valve}.\n"
        )
    if kind == UNESTABLISHED:
        return (
            f"SURFACE: work-item {item_id} reached the Fabro needs-human terminal, "
            "and the run's record does not establish whether a stage failed or an "
            "agent asked — marked blocked/needs-human; triage the run to find out "
            f"before answering, then release it with {valve}.\n"
        )
    return (
        f"SURFACE: work-item {item_id} parked at a Fabro human gate; "
        "marked blocked/needs-human and held terminal until a human valve "
        "moves it out.\n"
    )
