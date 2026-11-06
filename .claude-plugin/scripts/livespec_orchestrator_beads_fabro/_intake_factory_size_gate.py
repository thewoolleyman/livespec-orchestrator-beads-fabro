"""Capture-time application of the adopted factory assertion ceiling."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal, cast

from returns.io import IOFailure, IOResult, IOSuccess
from returns.pipeline import is_successful
from returns.unsafe import unsafe_perform_io

from livespec_orchestrator_beads_fabro._beads_client import make_beads_client
from livespec_orchestrator_beads_fabro.commands._dispatcher_factory_size_gate import (
    resolve_adopted_assertion_count_ceiling,
    stored_factory_size_decision,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_policy_settings import (
    PolicySettingUnreadable,
)
from livespec_orchestrator_beads_fabro.commands._intake_valve_claim_writes import (
    WRITER_INTAKE,
    ClaimWrite,
    ClaimWriteRefused,
    resting_at,
)
from livespec_orchestrator_beads_fabro.store import INTAKE_TRIAGED_LABEL

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

__all__: list[str] = ["apply_intake_factory_size_gate"]

_BLOCKED_REASON_LABEL = "blocked-reason:needs-human"
_RETIRED_INTAKE_LABELS = ["not-yet-actionable"]
_DECOMPOSITION_INTENT = "size-decomposition"


def apply_intake_factory_size_gate(
    *,
    path: StoreConfig,
    item: WorkItem,
) -> IOResult[Literal["backlog"] | None, PolicySettingUnreadable | ClaimWriteRefused]:
    """Route an oversized capture to decomposition, or leave intake unchanged.

    The route is a claim-changing write (`SPECIFICATION/contracts.md`, "Claim
    tokens"). Once `dispatcher.claim_tokens` is true it is made only after
    winning the item's current token, while the item still rests at the
    status intake read. A route that does not win writes nothing, the triage
    marker included, and rides the failure track.
    """
    repo_root = path.repo_root
    if repo_root is None:
        return IOSuccess(None)
    ceiling = resolve_adopted_assertion_count_ceiling(cwd=repo_root)
    if not is_successful(ceiling):
        return IOFailure(unsafe_perform_io(ceiling.failure()))
    decision = stored_factory_size_decision(
        path=path,
        item=item,
        adopted_ceiling=unsafe_perform_io(ceiling.unwrap()),
    )
    if decision.disposition == "proceed":
        return IOSuccess(None)
    reason = cast("str", decision.reason)
    route = ClaimWrite(
        path=path,
        item_id=item.id,
        writer=WRITER_INTAKE,
        intent=_DECOMPOSITION_INTENT,
        still_as_decided=resting_at(status=item.status),
    )
    refusal = route.write_size_decomposition(reason=reason)
    if refusal is not None:
        return IOFailure(route.refused(outcome=refusal))
    make_beads_client(config=path).update_issue(
        issue_id=item.id,
        add_labels=[INTAKE_TRIAGED_LABEL],
        remove_labels=[*_RETIRED_INTAKE_LABELS, _BLOCKED_REASON_LABEL],
    )
    return IOSuccess("backlog")
