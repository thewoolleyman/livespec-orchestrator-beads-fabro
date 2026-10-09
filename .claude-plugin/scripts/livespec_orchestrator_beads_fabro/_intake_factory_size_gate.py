"""Capture-time application of the adopted factory assertion ceiling."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal, cast

from returns.io import IOFailure, IOResult, IOSuccess
from returns.pipeline import is_successful
from returns.unsafe import unsafe_perform_io

from livespec_orchestrator_beads_fabro._beads_client import make_beads_client
from livespec_orchestrator_beads_fabro._store_factory_size_gate import (
    route_factory_size_decomposition,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_factory_size_gate import (
    factory_size_decision,
    resolve_adopted_assertion_count_ceiling,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_policy_settings import (
    PolicySettingUnreadable,
)
from livespec_orchestrator_beads_fabro.store import INTAKE_TRIAGED_LABEL

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

__all__: list[str] = ["apply_intake_factory_size_gate"]

_BLOCKED_REASON_LABEL = "blocked-reason:needs-human"
_RETIRED_INTAKE_LABELS = ["not-yet-actionable"]


def apply_intake_factory_size_gate(
    *,
    path: StoreConfig,
    item: WorkItem,
) -> IOResult[Literal["backlog"] | None, PolicySettingUnreadable]:
    """Route an oversized capture to decomposition, or leave intake unchanged."""
    repo_root = path.repo_root
    if repo_root is None:
        return IOSuccess(None)
    ceiling = resolve_adopted_assertion_count_ceiling(cwd=repo_root)
    if not is_successful(ceiling):
        return IOFailure(unsafe_perform_io(ceiling.failure()))
    decision = factory_size_decision(
        item=item,
        adopted_ceiling=unsafe_perform_io(ceiling.unwrap()),
        raw_justification=None,
    )
    if decision.disposition == "proceed":
        return IOSuccess(None)
    reason = cast("str", decision.reason)
    route_factory_size_decomposition(
        path=path,
        work_item_id=item.id,
        reason=reason,
    )
    make_beads_client(config=path).update_issue(
        issue_id=item.id,
        add_labels=[INTAKE_TRIAGED_LABEL],
        remove_labels=[*_RETIRED_INTAKE_LABELS, _BLOCKED_REASON_LABEL],
    )
    return IOSuccess("backlog")
