"""The `approve` valve: the entry-to-`ready` transition a human performs.

A sibling of `_drive_accept_valve` and `_drive_reject_valve`, and it moved out
of `_drive_valves` for the same reason `accept` did: the module whose job is
ROUTING grew a second concern. What pushed it over the file ceiling was the
semantic half of the Definition-of-Done gate ("Judged before admission"), which
is a model call — so the valve now reaches a provider, and routing does not.

THE TWO WALLS BELOW ARE ORDERED CHEAP-FIRST AND THAT IS LOAD-BEARING. The
mechanical half is a parse of the item against the governed spec tree; the
semantic half spends a judgement. An item the parse already refuses is one no
judgement can admit, so taking the judgement first would spend a model call per
refused approval and change no outcome.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from returns.pipeline import is_successful
from returns.unsafe import unsafe_perform_io

from livespec_orchestrator_beads_fabro import store
from livespec_orchestrator_beads_fabro._store_factory_size_gate import (
    route_factory_size_decomposition,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_acceptance_eligibility import (
    acceptance_eligibility,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_gate import (
    judge_item_definition_of_done,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_record import (
    STAGE_PRE_ADMISSION,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_factory_size_gate import (
    resolved_stored_factory_size_decision,
)
from livespec_orchestrator_beads_fabro.commands._drive_valve_predicates import can_approve_item
from livespec_orchestrator_beads_fabro.commands._drive_valve_result import (
    invalid_source_state,
    valve_refusal,
    valve_success,
)

if TYPE_CHECKING:
    from pathlib import Path

    from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

__all__: list[str] = ["approve_item"]


def _definition_of_done_refusal(
    *, repo: Path, config: StoreConfig, item: WorkItem, action_id: str
) -> dict[str, Any] | None:
    """Both halves of the entry-to-`ready` Definition-of-Done gate, as one answer.

    The MECHANICAL half consumes the SAME shared eligibility decision the
    pre-dispatch wall does, so an item this valve admits is one the dispatch
    path will accept — the two disagreeing is exactly what that clause's single
    decision prevents. The SEMANTIC half ("Judged before admission") runs
    second, because it is a model call and spending one on an item the free
    parse already refuses buys nothing.

    Neither refusal WRITES a status: the item rests at `pending-approval`
    rather than being routed to `backlog` or `blocked` on these grounds. The
    judgement does record its own verdict on the item, which is what carries
    the remedy past this invocation.

    THE VARIANT IS READ OFF THE SAME DECISION RATHER THAN RESOLVED AGAIN, and
    the early return is what keeps the two halves agreeing. "Judged before
    admission" scopes the judgement to an "implement-kind item", and the
    mechanical half has ALREADY exempted a groom-kind one — it returns no
    refusal for it at all — so running the judgement regardless would hold at
    `pending-approval` exactly the item the groom door is waiting for, which is
    the inversion `_dispatcher_criteria_wall_variant`'s docstring exists to
    prevent, reintroduced one line below the exemption. Discarding the
    `.variant` the decision already carries is how that happened; binding the
    result is the repair.
    """
    eligibility = acceptance_eligibility(item=item, cwd=repo)
    refusal = eligibility.refusal
    if refusal is not None:
        return valve_refusal(
            aid=action_id,
            wid=item.id,
            err="ungradeable-acceptance-criteria",
            msg=f"approve refused: {refusal}.",
        )
    if eligibility.variant.exempt:
        return None
    judgement = judge_item_definition_of_done(
        item=item, repo=repo, path=config, stage=STAGE_PRE_ADMISSION
    )
    if judgement.holds:
        return valve_refusal(
            aid=action_id,
            wid=item.id,
            err="definition-of-done-held",
            msg=f"approve refused: {'; '.join(judgement.findings)}",
        )
    return None


def approve_item(
    *, repo: Path, config: StoreConfig, item: WorkItem, action_id: str
) -> dict[str, Any]:
    if item.status != "pending-approval":
        return invalid_source_state(aid=action_id, item=item, expected="pending-approval")
    if not can_approve_item(item=item, cwd=repo):
        return valve_refusal(
            aid=action_id,
            wid=item.id,
            err="invalid-source-state",
            msg="approve requires an effective-manual pending-approval item.",
        )
    size_result = resolved_stored_factory_size_decision(
        cwd=repo,
        path_factory=lambda: config,
        item=item,
    )
    if not is_successful(size_result):
        failure = unsafe_perform_io(size_result.failure())
        return valve_refusal(
            aid=action_id,
            wid=item.id,
            err="policy-setting-unreadable",
            msg=failure.detail,
        )
    size = unsafe_perform_io(size_result.unwrap())
    if size.disposition == "decompose":
        reason = cast("str", size.reason)
        route_factory_size_decomposition(path=config, work_item_id=item.id, reason=reason)
        return valve_refusal(
            aid=action_id,
            wid=item.id,
            err="size-decomposition",
            msg=reason,
        ) | {"target_status": "backlog", "message": reason}
    held = _definition_of_done_refusal(repo=repo, config=config, item=item, action_id=action_id)
    if held is not None:
        return held
    store.update_work_item_status(path=config, item_id=item.id, status="ready")
    return valve_success(
        aid=action_id,
        wid=item.id,
        stage="human-valve-approve",
        status="ready",
        assignee=None,
        msg=f"Approved {item.id}: pending-approval -> ready.",
    )
