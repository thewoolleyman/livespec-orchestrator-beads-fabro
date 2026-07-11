"""Admission valve orchestration for the Dispatcher.

This module owns the Dispatcher's admission / candidate-selection valve:
host-only candidates are refused through an injected local callback,
manual or unresolvable-assignee candidates are held and surfaced, and
admitted candidates are transitioned `ready -> active` with their resolved
assignee before Fabro launch.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable
from dataclasses import asdict, dataclass, replace
from functools import partial
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_autonomous_audit import (
    autonomous_decision_journal_record,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_autonomous_collapse import (
    collapse_admission_to_auto,
    effective_admission_policy_under_mode,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import store_config
from livespec_orchestrator_beads_fabro.commands._dispatcher_valves import (
    admission_held_detail,
    plan_admissions,
    resolve_assignee,
    resolve_wip_cap,
)
from livespec_orchestrator_beads_fabro.io import write_stderr
from livespec_orchestrator_beads_fabro.store import update_work_item_status
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "Admission",
    "admission_held_outcome",
    "admit_and_select",
    "autonomous_armed",
]

# The `decision` text journaled on each full-autonomous-mode auto-resolution
# audit record (the S2 autonomous-decision record). Names what the mode
# decided so no auto-resolution is silent.
_AUTONOMOUS_APPROVE_DECISION = (
    "routine manual-admission auto-approved to ready under armed autonomous mode"
)


@dataclass(frozen=True, kw_only=True)
class Admission:
    """The outcome of the admission valve over a candidate set.

    `admitted` carries the items transitioned `ready -> active` (assignee
    set) that the Dispatcher then launches; `refused` carries the
    non-launched terminal outcomes — host-only routing refusals plus
    admission holds (manual / unresolvable assignee) — that ride in the
    wave's outcome list so the verdict and the post-verdict alarm see them.
    A capacity-deferred admission-eligible item appears in NEITHER list — it
    simply waits for the next pass.
    """

    admitted: list[WorkItem]
    refused: list[DispatchOutcome]


def autonomous_armed(*, args: argparse.Namespace) -> bool:
    """Read the per-run full-autonomous-mode armed flag threaded onto args.

    `_run_loop_command` sets `args.autonomous_armed` from the S1 arming
    decision. The targeted `dispatch --item` path never arms the mode (the
    `--mode autonomous` opt-in rides `loop`, not `dispatch`), so it never sets
    the attribute; the `getattr` default keeps that path — and any legacy
    caller — at the safe unarmed default. `bool(...)` narrows the untyped
    Namespace attribute to a typed bool.
    """
    return bool(getattr(args, "autonomous_armed", False))


def admit_and_select(  # noqa: PLR0913 - kw-only admission valve; fields are caller inputs.
    *,
    repo: Path,
    items: list[WorkItem],
    candidates: list[WorkItem],
    journal: JournalFile,
    enforce_cap: bool,
    armed: bool,
    host_only_refusal: Callable[..., DispatchOutcome | None],
) -> Admission:
    """Run the admission valve over the rank-sorted candidate set.

    The sole enforcer of the approval/admission valve + per-repo WIP cap. For
    each candidate, in order: a host-only self-machinery item is routed away
    (refused, never admitted — the uvd hang-guard); then `plan_admissions`
    holds a manual pending item, auto-approves an auto pending item into
    `ready`, holds an unresolvable-assignee item, and admits the highest-`rank`
    ready items into the free WIP slots, writing each `ready -> active` with
    its resolved assignee. `enforce_cap` reads the per-repo `wip_cap` from
    `.livespec.jsonc` and discounts the already-`active` items; a targeted
    `dispatch --item` is an operator override that passes `enforce_cap=False`
    (every host-cleared candidate gets a slot). The admit writes + the held
    surfaces are journaled here; the launched items flow on to `_dispatch_one`.

    `armed` layers the full-autonomous-mode approve-gate collapse
    (SPECIFICATION/scenarios.md Scenario 33): an armed run injects an
    armed-aware admission-policy resolver so a routine `manual` pending item is
    auto-approved into `ready` instead of held — EXCEPT a design-human-gated
    spec-change-tier slice, which stays held/escalated (Scenario 36). Each such
    collapse is journaled as an autonomous auto-resolution audit record
    (`gate` `approve`); when not armed the resolver is the base policy and
    behavior is exactly unchanged.
    """
    admittable: list[WorkItem] = []
    refused: list[DispatchOutcome] = []
    for item in candidates:
        host_refusal = host_only_refusal(item=item, journal=journal)
        if host_refusal is not None:
            refused.append(host_refusal)
        else:
            admittable.append(item)
    if enforce_cap:
        active_count = sum(1 for item in items if item.status == "active")
        free_slots = max(0, resolve_wip_cap(cwd=repo) - active_count)
    else:
        free_slots = len(admittable)
    plan = plan_admissions(
        ready_items=admittable,
        free_slots=free_slots,
        resolve_assignee=resolve_assignee,
        admission_policy=partial(effective_admission_policy_under_mode, armed=armed),
    )
    admitted: list[WorkItem] = []
    config = store_config(repo=repo)
    approved_ids = {item.id for item in plan.approved}
    for item in plan.approved:
        update_work_item_status(path=config, item_id=item.id, status="ready")
        journal.append(record={"stage": "ledger-approve", "work_item_id": item.id})
        if collapse_admission_to_auto(item=item, armed=armed):
            journal.append(
                record=autonomous_decision_journal_record(
                    work_item_id=item.id,
                    gate="approve",
                    decision=_AUTONOMOUS_APPROVE_DECISION,
                    disposition="auto-resolved",
                )
            )
    for item, assignee in plan.admitted:
        journal_item = replace(item, status="ready") if item.id in approved_ids else item
        update_work_item_status(
            path=config, item_id=journal_item.id, status="active", assignee=assignee
        )
        journal.append(
            record={"stage": "ledger-admit", "work_item_id": item.id, "assignee": assignee}
        )
        admitted.append(replace(journal_item, status="active", assignee=assignee))
    for item, reason in plan.held:
        held = admission_held_outcome(item=item, reason=reason)
        journal.append(record={"stage": "outcome", "outcome": asdict(held)})
        _ = write_stderr(text=f"SURFACE: {admission_held_detail(item_id=item.id, reason=reason)}\n")
        refused.append(held)
    return Admission(admitted=admitted, refused=refused)


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
