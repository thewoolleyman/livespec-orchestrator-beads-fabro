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
from livespec_orchestrator_beads_fabro.commands._dispatcher_acceptance_eligibility import (
    acceptance_eligibility,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement import (
    take_origin_reading,
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
from livespec_orchestrator_beads_fabro.commands._drive_valve_result import (
    invalid_source_state,
    valve_refusal,
    valve_success,
)
from livespec_orchestrator_beads_fabro.commands._intake_valve_claim_writes import (
    WRITER_HUMAN_VALVE,
    ClaimWrite,
    resting_at,
    valve_claim_refusal,
)

if TYPE_CHECKING:
    from pathlib import Path

    from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

__all__: list[str] = ["approve_item"]

_SOURCE_STATUS = "pending-approval"
# What an approve has done by the time its transition is refused. The
# Definition-of-Done judgement runs first and records its own verdict on the
# item (`_definition_of_done_refusal`); a refused transition does not remove it.
_JUDGED = (
    "any Definition-of-Done judgement this press ran is already recorded on the item "
    "and stays there"
)


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
    # ONE reading of the default branch's spec serves the mechanical half and the
    # judgement, so both grade the same revision of the References.
    origin = take_origin_reading(items=(item,), cwd=repo)
    eligibility = acceptance_eligibility(item=item, cwd=repo, origin_sections=origin)
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
        item=item, repo=repo, path=config, stage=STAGE_PRE_ADMISSION, origin_sections=origin
    )
    if judgement.holds:
        return valve_refusal(
            aid=action_id,
            wid=item.id,
            err="definition-of-done-held",
            msg=f"approve refused: {'; '.join(judgement.findings)}",
        )
    return None


def _approval(*, repo: Path, config: StoreConfig, item: WorkItem, intent: str) -> ClaimWrite:
    """One of this valve's two claim-changing writes, decided on a `pending-approval` item."""
    return ClaimWrite(
        repo=repo,
        path=config,
        item_id=item.id,
        writer=WRITER_HUMAN_VALVE,
        intent=intent,
        still_as_decided=resting_at(status=_SOURCE_STATUS),
    )


def _size_decomposition(
    *, repo: Path, config: StoreConfig, item: WorkItem, action_id: str, reason: str
) -> dict[str, Any]:
    """Route an oversized item to `backlog` and refuse the approval with the reason.

    The route is a claim-changing write, so once `dispatcher.claim_tokens` is
    true it is made only after winning the item's current token. A route that
    does not win has moved nothing, and the refusal names the protocol's outcome
    and not a `backlog` the item never reached.
    """
    lost = _approval(
        repo=repo, config=config, item=item, intent="approve:size-decomposition"
    ).write_size_decomposition(reason=reason)
    if lost is not None:
        return valve_claim_refusal(aid=action_id, wid=item.id, verb="approve", outcome=lost)
    return valve_refusal(
        aid=action_id,
        wid=item.id,
        err="size-decomposition",
        msg=reason,
    ) | {"target_status": "backlog", "message": reason}


def approve_item(
    *, repo: Path, config: StoreConfig, item: WorkItem, action_id: str
) -> dict[str, Any]:
    """Admit a `pending-approval` item to `ready`, whatever its admission policy.

    The status, not the admission label, is what the item is waiting on. A
    `set-admission:<id>:auto` flip never moves the item (it rests at
    `pending-approval` until a Dispatcher pass reaches it), so refusing the
    explicit `approve` on the label would strand an item that was parked at this
    valve when its policy changed.
    """
    if item.status != _SOURCE_STATUS:
        return invalid_source_state(aid=action_id, item=item, expected=_SOURCE_STATUS)
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
        return _size_decomposition(
            repo=repo,
            config=config,
            item=item,
            action_id=action_id,
            reason=cast("str", size.reason),
        )
    held = _definition_of_done_refusal(repo=repo, config=config, item=item, action_id=action_id)
    if held is not None:
        return held
    lost = _approval(repo=repo, config=config, item=item, intent="approve").write_status(
        status="ready",
        unguarded=lambda: store.update_work_item_status(
            path=config, item_id=item.id, status="ready"
        ),
    )
    if lost is not None:
        return valve_claim_refusal(
            aid=action_id, wid=item.id, verb="approve", outcome=lost, already_done=_JUDGED
        )
    return valve_success(
        aid=action_id,
        wid=item.id,
        stage="human-valve-approve",
        status="ready",
        assignee=None,
        msg=f"Approved {item.id}: pending-approval -> ready.",
    )
