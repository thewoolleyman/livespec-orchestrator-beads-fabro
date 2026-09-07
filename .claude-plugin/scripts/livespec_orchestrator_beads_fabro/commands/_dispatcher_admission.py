"""Admission valve orchestration for the Dispatcher.

This module owns the Dispatcher's admission / candidate-selection valve:
host-only candidates are refused through the completion disposition helper,
manual or unresolvable-assignee candidates are held and surfaced, and
admitted candidates are transitioned `ready -> active` with their resolved
assignee before Fabro launch.

It also SEQUENCES the two legs of one pass. The rework leg
(`_dispatcher_rework_admission`) runs FIRST and consumes capacity before any
new `ready` item is admitted, because the ratified rework-pending re-dispatch
contract orders it that way: promised fix-forward work outranks work not yet
started. Both legs pass through the SAME mechanical eligibility filter below,
so a marked row is refused by a host-only route, a non-null `factory_safety`,
an unreadable label read, or an unexpired provider-exhaustion record on
exactly the terms a ready candidate is.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from pathlib import Path

from returns.unsafe import unsafe_perform_io

from livespec_orchestrator_beads_fabro.commands import _dispatcher_self_update as selfup
from livespec_orchestrator_beads_fabro.commands._dispatcher_capacity_deferred import (
    CapacitySnapshot,
    capacity_deferred_outcomes,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_claim_reclaim import (
    claimed_active_accounting,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_completion import host_only_refusal
from livespec_orchestrator_beads_fabro.commands._dispatcher_credentials import read_dispatch_labels
from livespec_orchestrator_beads_fabro.commands._dispatcher_decision_journal import (
    auto_disposition_journal_record,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dispatch_lock import (
    write_dispatch_lock,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile, utc_now_iso
from livespec_orchestrator_beads_fabro.commands._dispatcher_loop_outcomes import (
    failed_dispatch_outcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import store_config
from livespec_orchestrator_beads_fabro.commands._dispatcher_provider_exhaustion import (
    provider_exhaustion_refusal,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_rework_admission import (
    ReworkPass,
    admit_rework,
    rework_pending_candidates,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_valves import (
    DEFAULT_WIP_CAP,
    admission_held_detail,
    plan_admissions,
    resolve_assignee,
    resolve_wip_cap,
)
from livespec_orchestrator_beads_fabro.commands._ready_aging_order import ready_aging_order
from livespec_orchestrator_beads_fabro.io import write_stderr
from livespec_orchestrator_beads_fabro.store import update_work_item_status
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "Admission",
    "admission_held_outcome",
    "admit_and_select",
]


@dataclass(frozen=True, kw_only=True)
class Admission:
    """The outcome of the admission valve over a candidate set.

    `admitted` carries the items transitioned `ready -> active` (assignee
    set) that the Dispatcher then launches; `rework` carries the already-
    `active` marked rows this pass re-dispatches, which the caller launches
    BEFORE `admitted` so the drain's observable order matches the contract's
    selection order; `deferred` carries capacity-deferred items from either
    leg; `refused` carries the non-launched terminal outcomes — host-only
    routing refusals plus admission holds (manual / unresolvable assignee) —
    that ride in the wave's outcome list so the verdict and the post-verdict
    alarm see them.
    """

    admitted: list[WorkItem]
    deferred: list[DispatchOutcome]
    refused: list[DispatchOutcome]
    rework: list[WorkItem] = field(default_factory=list)


def admit_and_select(
    *,
    repo: Path,
    items: list[WorkItem],
    candidates: list[WorkItem],
    journal: JournalFile,
    enforce_cap: bool,
    rework: ReworkPass | None = None,
) -> Admission:
    """Run the admission valve over the rank-sorted candidate set.

    The sole enforcer of the approval/admission valve + per-repo WIP cap. For
    each candidate, in order: a host-only self-machinery item is routed away
    (refused, never admitted — the uvd hang-guard); then `plan_admissions`
    holds a manual pending item, auto-approves an auto pending item into
    `ready`, holds an unresolvable-assignee item, and admits the highest-`rank`
    ready items into the free WIP slots, writing each `ready -> active` with
    its resolved assignee. `enforce_cap` reads the per-repo `wip_cap` from
    `.livespec.jsonc` and discounts the already-`active` items.
    A targeted `dispatch --item` is an operator override that passes
    `enforce_cap=False` (every host-cleared candidate gets a slot).
    `dispatcher.py dispatch --item` reaches that override.
    `drive --action impl:` does not, because it routes selected items through
    the cap-enforcing `loop` path used by unattended draining. The admit writes
    + the held surfaces are journaled here; the launched items flow on to
    `_dispatch_one`.

    `rework` carries the pass's rework narrowing and budget. Its leg runs
    BEFORE the ready plan and its admissions occupy capacity first, which is
    what makes "marked rows before any new `ready` item" a property of the
    valve rather than of one caller's ordering.
    """
    accounting = claimed_active_accounting(repo=repo, items=items, journal=journal)
    rework_pass = rework if rework is not None else ReworkPass()
    rework_admittable, refused = _filter_host_only_candidates(
        repo=repo,
        candidates=list(
            rework_pending_candidates(
                items=items,
                accounting=accounting,
                rework=rework_pass,
                # The same aging inputs the ready queue this pass drains was
                # ordered by, resolved off the same repository root.
                ready_aging=ready_aging_order(project_root=repo),
            )
        ),
        journal=journal,
    )
    admittable, ready_refused = _filter_host_only_candidates(
        repo=repo,
        candidates=candidates,
        journal=journal,
    )
    refused.extend(ready_refused)
    wip_cap = (
        # An unreadable `.livespec.jsonc` falls back to the documented cap,
        # visibly and here rather than inside the reader. `unsafe_perform_io`
        # is required: `IOResult.value_or` returns `IO[value]`, not the value.
        unsafe_perform_io(resolve_wip_cap(cwd=repo).value_or(DEFAULT_WIP_CAP))
        if enforce_cap
        else None
    )
    reworked = admit_rework(
        repo=repo,
        candidates=tuple(rework_admittable),
        journal=journal,
        active_count=accounting.active_count,
        wip_cap=wip_cap,
    )
    occupied = accounting.active_count + len(reworked.admitted)
    free_slots = _ready_free_slots(
        admittable=admittable,
        occupied=occupied,
        wip_cap=wip_cap,
        budget_left=_budget_left(rework=rework_pass, taken=len(reworked.admitted)),
    )
    plan = plan_admissions(
        ready_items=admittable,
        free_slots=free_slots,
        cwd=repo,
        resolve_assignee=resolve_assignee,
    )
    admitted: list[WorkItem] = []
    deferred: list[DispatchOutcome] = []
    config = store_config(repo=repo)
    approved_ids = {item.id for item in plan.approved}
    for item in plan.approved:
        update_work_item_status(path=config, item_id=item.id, status="ready")
        journal.append(record={"stage": "ledger-approve", "work_item_id": item.id})
        journal.append(
            record=auto_disposition_journal_record(
                work_item_id=item.id,
                disposition="auto-approve",
                governing_settings=_auto_approve_governing_settings(item=item),
            )
        )
    for item, assignee in plan.admitted:
        journal_item = replace(item, status="ready") if item.id in approved_ids else item
        update_work_item_status(
            path=config, item_id=journal_item.id, status="active", assignee=assignee
        )
        dispatch_id = selfup.run_id()
        _ = write_dispatch_lock(repo=repo, work_item_id=item.id, dispatch_id=dispatch_id)
        journal.append(
            record={"stage": "ledger-admit", "work_item_id": item.id, "assignee": assignee}
        )
        admitted.append(replace(journal_item, status="active", assignee=assignee))
    for item, reason in plan.held:
        held = admission_held_outcome(item=item, reason=reason)
        journal.append(record={"stage": "outcome", "outcome": asdict(held)})
        _ = write_stderr(text=f"SURFACE: {admission_held_detail(item_id=item.id, reason=reason)}\n")
        refused.append(held)
    if wip_cap is not None:
        deferred = capacity_deferred_outcomes(
            admittable=admittable,
            admitted=admitted,
            held=plan.held,
            capacity=CapacitySnapshot(
                active_count=occupied,
                wip_cap=wip_cap,
                free_slots=free_slots,
                live_lock_active_ids=accounting.live_lock_active_ids,
                journal_unreadable_active_ids=accounting.journal_unreadable_active_ids,
                green_terminal_active_ids=accounting.green_terminal_active_ids,
            ),
            journal=journal,
        )
    return Admission(
        admitted=admitted,
        deferred=[*reworked.deferred, *deferred],
        refused=refused,
        rework=list(reworked.admitted),
    )


def _budget_left(*, rework: ReworkPass, taken: int) -> int | None:
    """What is left of the pass's `--budget` after the rework leg took its share.

    `None` means unbounded — the `dispatch --item` override carries no budget,
    and the ready candidate list a `loop` hands in was already truncated to the
    budget upstream, so this only ever REMOVES the slots rework already spent.
    """
    if rework.budget is None:
        return None
    return max(0, rework.budget - taken)


def _ready_free_slots(
    *,
    admittable: list[WorkItem],
    occupied: int,
    wip_cap: int | None,
    budget_left: int | None,
) -> int:
    slots = len(admittable) if wip_cap is None else max(0, wip_cap - occupied)
    if budget_left is None:
        return slots
    return min(slots, budget_left)


def _filter_host_only_candidates(
    *,
    repo: Path,
    candidates: list[WorkItem],
    journal: JournalFile,
) -> tuple[list[WorkItem], list[DispatchOutcome]]:
    admittable: list[WorkItem] = []
    refused: list[DispatchOutcome] = []
    for item in candidates:
        exhaustion_refusal = provider_exhaustion_refusal(
            work_item_id=item.id,
            journal=journal,
            journal_path=getattr(journal, "path", None),
            now_iso=utc_now_iso(),
        )
        if exhaustion_refusal is not None:
            refused.append(exhaustion_refusal)
            continue
        raw_labels = read_dispatch_labels(repo=repo, item=item)
        if isinstance(raw_labels, str):
            refused.append(
                failed_dispatch_outcome(
                    journal=journal,
                    work_item_id=item.id,
                    stage="ledger-labels",
                    detail=raw_labels,
                )
            )
            continue
        host_refusal = host_only_refusal(
            repo=repo,
            item=item,
            journal=journal,
            raw_labels=raw_labels,
        )
        if host_refusal is not None:
            refused.append(host_refusal)
        else:
            admittable.append(item)
    return admittable, refused


def _auto_approve_governing_settings(*, item: WorkItem) -> tuple[str, ...]:
    if item.admission_policy == "auto":
        return ("admission:auto",)
    return ("auto_approve_ready",)


def admission_held_outcome(*, item: WorkItem, reason: str) -> DispatchOutcome:
    """Build the `admission-held` terminal for an item held at the admission valve.

    A `failed` outcome (so the dispatch exit code flips to 1 and the
    maintainer's eyes are required) at the `admission-held` stage; nothing is
    launched and nothing is closed — a manual item stays at `pending-approval`
    for the maintainer to approve, while an unresolvable item stays put until
    assignment is fixed.
    """
    return DispatchOutcome(
        work_item_id=item.id,
        status="failed",
        stage="admission-held",
        pr_number=None,
        merge_sha=None,
        detail=admission_held_detail(item_id=item.id, reason=reason),
    )
