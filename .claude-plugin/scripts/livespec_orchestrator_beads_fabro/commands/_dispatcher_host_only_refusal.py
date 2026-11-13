"""The Dispatcher's pre-launch host-only refusal disposition.

Split out of `_dispatcher_completion.py`, which had accreted two unrelated
concerns: this PRE-LAUNCH refusal (decided before any fabro sandbox exists) and
the POST-MERGE completion / acceptance / bounce dispositions (decided after a
run reaches its terminal). The refusal carries its own ledger write —
`_set_awaits_scope_override` is used by nothing else — so the two travel
together and nothing private crosses the seam.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import asdict
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import store_config
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import (
    declares_workflow_scope_refusal,
    host_only_refusal_detail,
    is_host_only_item,
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
from livespec_orchestrator_beads_fabro.store import update_work_item_awaits_scope_override
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "host_only_refusal",
]

_LEDGER_WRITE_ERRORS = (
    WorkItemNotFoundError,
    BeadsCommandError,
    BeadsConnectionError,
    BeadsMappingError,
    BeadsTenantMissingError,
)


def host_only_refusal(
    *, repo: Path, item: WorkItem, journal: JournalFile, raw_labels: Sequence[str] = ()
) -> DispatchOutcome | None:
    """Refuse to sandbox a host-only self-machinery item (uvd hang-guard).

    Returns the `host-only-refused` outcome (routed BEFORE any fabro
    launch, so the in-sandbox/in-hook git commit can never deadlock — the
    7us.6 hang class) when the item carries the explicit host-only
    marker, or None to let the dispatch proceed. The refusal is a
    `failed` outcome so the dispatch exit code flips to 1 and the
    orchestrator host-routes the item; the detail carries the actionable
    host-route instruction. Nothing is closed — the item stays open.
    """
    workflow_scope_refusal = declares_workflow_scope_refusal(item=item, raw_labels=raw_labels)
    if not is_host_only_item(item=item, raw_labels=raw_labels):
        if item.awaits_scope_override:
            _set_awaits_scope_override(repo=repo, item_id=item.id, value=False)
        return None
    if workflow_scope_refusal:
        _set_awaits_scope_override(repo=repo, item_id=item.id, value=True)
    elif item.awaits_scope_override:
        _set_awaits_scope_override(repo=repo, item_id=item.id, value=False)
    outcome = DispatchOutcome(
        work_item_id=item.id,
        status="failed",
        stage="host-only-refused",
        pr_number=None,
        merge_sha=None,
        detail=host_only_refusal_detail(item_id=item.id, raw_labels=raw_labels),
    )
    journal.append(record={"stage": "outcome", "outcome": asdict(outcome)})
    _ = write_stderr(text=f"SURFACE: {outcome.detail}\n")
    return outcome


def _set_awaits_scope_override(*, repo: Path, item_id: str, value: bool) -> None:
    result = attempt(
        action=lambda: update_work_item_awaits_scope_override(
            path=store_config(repo=repo),
            item_id=item_id,
            value=value,
        ),
        exceptions=_LEDGER_WRITE_ERRORS,
    )
    if isinstance(result, AttemptFailure):
        _ = write_stderr(
            text=(
                f"WARN: failed to update awaits_scope_override for {item_id} "
                f"({type(result.error).__name__}: {result.error})\n"
            )
        )
