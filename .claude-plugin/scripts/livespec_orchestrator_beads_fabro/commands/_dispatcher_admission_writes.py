"""The Dispatcher admission valve's ledger writes and their policy gate."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from returns.unsafe import unsafe_perform_io

from livespec_orchestrator_beads_fabro.commands._dispatcher_admission_slots import (
    auto_approve_governing_settings,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_decision_journal import (
    auto_disposition_journal_record,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_policy_settings import (
    resolve_claim_tokens,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_valves import (
    AdmissionPlan,
    admission_held_detail,
)
from livespec_orchestrator_beads_fabro.io import write_stderr
from livespec_orchestrator_beads_fabro.store import update_work_item_status
from livespec_orchestrator_beads_fabro.types import StoreConfig

__all__: list[str] = ["approve_ready_items", "claim_tokens_enabled", "held_outcomes"]

_CLAIM_TOKENS_DISABLED = False


def claim_tokens_enabled(*, repo: Path) -> bool:
    """Whether this committed Dispatcher configuration requires guarded writes."""
    return unsafe_perform_io(resolve_claim_tokens(cwd=repo).value_or(_CLAIM_TOKENS_DISABLED))


def approve_ready_items(
    *, plan: AdmissionPlan, config: StoreConfig, journal: JournalFile
) -> set[str]:
    """Write the planner's auto-approval leg before any ready-item admission."""
    approved_ids = {item.id for item in plan.approved}
    for item in plan.approved:
        update_work_item_status(path=config, item_id=item.id, status="ready")
        journal.append(record={"stage": "ledger-approve", "work_item_id": item.id})
        journal.append(
            record=auto_disposition_journal_record(
                work_item_id=item.id,
                disposition="auto-approve",
                governing_settings=auto_approve_governing_settings(item=item),
            )
        )
    return approved_ids


def held_outcomes(*, plan: AdmissionPlan, journal: JournalFile) -> list[DispatchOutcome]:
    """Journal and surface every planned admission hold without changing its item."""
    outcomes: list[DispatchOutcome] = []
    for item, reason in plan.held:
        held = DispatchOutcome(
            work_item_id=item.id,
            status="failed",
            stage="admission-held",
            pr_number=None,
            merge_sha=None,
            detail=admission_held_detail(item_id=item.id, reason=reason),
        )
        journal.append(record={"stage": "outcome", "outcome": asdict(held)})
        _ = write_stderr(text=f"SURFACE: {held.detail}\n")
        outcomes.append(held)
    return outcomes
