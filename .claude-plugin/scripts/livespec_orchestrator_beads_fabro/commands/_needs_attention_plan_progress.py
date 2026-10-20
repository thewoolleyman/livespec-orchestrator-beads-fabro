"""Plan-result attention facts over the durable progress authority.

This read-only lane reports the original result obligation rather than treating
ancillary work as progress.  The same immutable chain and typed reader used by
the resume gate decide whether a declared target remains overdue.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from livespec_runtime.attention_item import AttentionItem, Handoff, SourceRef

from livespec_orchestrator_beads_fabro.commands._dispatcher_io import ShellCommandRunner
from livespec_orchestrator_beads_fabro.commands._needs_attention_conformance import (
    ConformanceContext,
)
from livespec_orchestrator_beads_fabro.commands._plan_epoch_chain_head import ChainHead
from livespec_orchestrator_beads_fabro.commands._plan_epoch_reconcile import authorized_head
from livespec_orchestrator_beads_fabro.commands._plan_obligation import (
    Obligation,
    obligation_expiry,
    obligation_of,
)
from livespec_orchestrator_beads_fabro.commands._plan_progress_resume import (
    diagnosis_operation,
)
from livespec_orchestrator_beads_fabro.commands._plan_result_observation import (
    OBSERVATION_SATISFIED,
    OBSERVATION_UNOBSERVABLE,
)
from livespec_orchestrator_beads_fabro.commands._plan_result_reader import read_result

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

__all__: list[str] = ["plan_progress_items"]

_CLOSED_STATUS = "done"
_PLAN_HINT_PREFIX = "plan:"


def plan_progress_items(
    *,
    context: ConformanceContext,
    config: StoreConfig,
    items: list[WorkItem],
    now: str,
) -> list[AttentionItem]:
    """Return report-only overdue-result facts for each open tracked plan."""
    facts: list[AttentionItem] = []
    for epic in items:
        if not _is_live_plan(item=epic):
            continue
        head = authorized_head(config=config, epic_id=epic.id)
        if not isinstance(head, ChainHead):
            continue
        obligation = obligation_of(authority=head.authority)
        if obligation is None:
            continue
        observation = read_result(
            project_root=context.project_root,
            reference=obligation.required_result,
            runner=ShellCommandRunner(),
            now=now,
        )
        if observation.status in (OBSERVATION_SATISFIED, OBSERVATION_UNOBSERVABLE):
            continue
        expiry = obligation_expiry(obligation=obligation, now=now)
        if expiry is not None:
            facts.append(
                _overdue_item(
                    context=context,
                    epic=epic,
                    obligation=obligation,
                    expiry=expiry,
                    observation_time=observation.observed_at,
                )
            )
    return facts


def _is_live_plan(*, item: WorkItem) -> bool:
    return (
        item.type == "epic"
        and item.status != _CLOSED_STATUS
        and item.spec_commitment_hint is not None
        and item.spec_commitment_hint.startswith(_PLAN_HINT_PREFIX)
    )


def _overdue_item(
    *,
    context: ConformanceContext,
    epic: WorkItem,
    obligation: Obligation,
    expiry: str,
    observation_time: str,
) -> AttentionItem:
    action = diagnosis_operation(epic_id=epic.id)
    return context.candidate(
        id=f"hygiene:overdue-result:{epic.id}",
        kind="hygiene",
        urgency="high",
        summary=(
            f"Plan epic {epic.id} still lacks its declared required result after its "
            f"{expiry} budget: target {obligation.required_result!r}; deadline "
            f"{obligation.original_deadline}; handoffs "
            f"{obligation.consumed_handoffs}/{obligation.max_handoffs}; last observation "
            f"{observation_time}. Inspect the durable obligation and recover the target "
            f"through {action}."
        ),
        source_ref=SourceRef(repo=context.repo, work_item=epic.id),
        handoff=Handoff(kind="livespec-op", command=action, action_id=action),
    )
