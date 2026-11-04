"""Why one tenant's ready rows are NOT admitted — the shared verdict, reused.

The idle-slot clause reads a hold from exactly two places: ledger STATUS, and
the shared admission-eligibility verdict "evaluated with capacity excepted
(the drain's own non-capacity eligibility that the idle-factory fact also
consumes)". Status is handled by the classifier; this module is the second
half, and it is composed from the drain's OWN stages rather than from a
look-alike predicate, for the reason the idle-factory fact gives: a second
composition point would disagree with the first the moment either gained a
check.

PROSE CANNOT HOLD A READY CHILD, and that is a measured refinement rather than
an omission. The journaled script this surface replaces classified
`bd-ib-35kfra` DISPATCHABLE NOW while a driver ruling held it in a comment; no
mechanical surface can read that, so the ratified clause says an operator hold
MUST be expressed through ledger status or the admission verdict. Nothing here
reads a comment, and an `admission:manual` label on an item that is ALREADY
`ready` holds nothing — admission policy gates only `pending-approval -> ready`.

THE TWO TENANT-WIDE WAITS COME FIRST because they are facts about the tenant
rather than about any row: a recorded provider-exhaustion wait or an
admission-required ACP chain wait holds EVERY ready child of that tenant, so
grading rows underneath one would report a vendor outage as a property of each
item. They are read through the same two predicates the idle-factory fact
consumes, with no credential probe and no confirmation turn.

The three per-row stages below are ordered as the drain orders them, and the
reported reason is the verdict's OWN where it exposes one: `plan_admissions`
names `manual-admission` / `unresolvable-assignee`, the acceptance wall
returns its refusal text, and readiness exposes no reason at all — so a row
refused there is reported by STAGE, which is what the clause asks for when the
verdict exposes nothing.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_acceptance_eligibility import (
    acceptance_eligibility,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_idle_slot_classify import READY_STATUS
from livespec_orchestrator_beads_fabro.commands._dispatcher_loop_selection import ready_items
from livespec_orchestrator_beads_fabro.commands._dispatcher_valves import (
    plan_admissions,
    resolve_assignee,
)
from livespec_orchestrator_beads_fabro.commands._needs_attention_waits import (
    acp_chain_wait_active,
    provider_exhaustion_wait_active,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "HOLD_ACP_CHAIN_WAIT",
    "HOLD_PROVIDER_EXHAUSTION_WAIT",
    "HOLD_STAGE_READINESS",
    "tenant_hold_reasons",
]

HOLD_PROVIDER_EXHAUSTION_WAIT = (
    "tenant provider-exhaustion wait: every ready child of this tenant is held"
)
HOLD_ACP_CHAIN_WAIT = (
    "tenant admission-required ACP chain wait: every ready child of this tenant is held"
)
HOLD_STAGE_READINESS = "refused at the readiness stage"


def tenant_hold_reasons(*, repo: Path, items: Sequence[WorkItem]) -> dict[str, str]:
    """Map each HELD ready row of one tenant to the reason it is not admitted.

    A ready row absent from the result is admitted by the shared verdict with
    capacity excepted. Rows that are not `ready` never appear: every other
    status is already its own class, so grading them here would offer a second
    answer for a row the classifier has already decided.
    """
    ready = [item for item in items if item.status == READY_STATUS]
    wait = _tenant_wait(repo=repo)
    if wait is not None:
        return {item.id: wait for item in ready}
    candidates = ready_items(items=list(items), repo=repo)
    candidate_ids = {item.id for item in candidates}
    reasons = {item.id: HOLD_STAGE_READINESS for item in ready if item.id not in candidate_ids}
    reasons.update(_wall_refusals(repo=repo, candidates=candidates))
    reasons.update(_admission_holds(repo=repo, candidates=candidates, refused=set(reasons)))
    return reasons


def _tenant_wait(*, repo: Path) -> str | None:
    if provider_exhaustion_wait_active(project_root=repo):
        return HOLD_PROVIDER_EXHAUSTION_WAIT
    if acp_chain_wait_active(project_root=repo):
        return HOLD_ACP_CHAIN_WAIT
    return None


def _wall_refusals(*, repo: Path, candidates: Sequence[WorkItem]) -> dict[str, str]:
    """The acceptance wall's own refusal text, per candidate it refuses."""
    verdicts = {item.id: acceptance_eligibility(item=item, cwd=repo).refusal for item in candidates}
    return {item_id: refusal for item_id, refusal in verdicts.items() if refusal is not None}


def _admission_holds(
    *,
    repo: Path,
    candidates: Sequence[WorkItem],
    refused: set[str],
) -> dict[str, str]:
    """`plan_admissions` run with capacity excepted — every slot the set needs.

    `free_slots=len(eligible)` is what "capacity excepted" means: with a slot
    for every candidate, the only rows the planner holds are the ones it would
    hold at any capacity, which is precisely the non-capacity eligibility the
    clause names.
    """
    eligible = [item for item in candidates if item.id not in refused]
    plan = plan_admissions(
        ready_items=eligible,
        free_slots=len(eligible),
        cwd=repo,
        resolve_assignee=resolve_assignee,
    )
    return {item.id: reason for item, reason in plan.held}
