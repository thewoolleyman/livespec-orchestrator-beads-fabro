"""Close a forge-proven scratch-branch drill without treating it as repayment."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro._incident_authority_types import (
    AuthorityRefusal,
    IncidentAttempt,
    IncidentReading,
)
from livespec_orchestrator_beads_fabro._incident_drill_evidence import recorded_drill_evidence
from livespec_orchestrator_beads_fabro._incident_phases import lifecycle_state_for
from livespec_orchestrator_beads_fabro._store_claim_tokens import change_claim
from livespec_orchestrator_beads_fabro.effects._incident_authority_reader import read_history
from livespec_orchestrator_beads_fabro.effects._incident_authority_transition import (
    commit_transition,
)
from livespec_orchestrator_beads_fabro.effects._incident_entry_writer import (
    require_current_generation,
)

if TYPE_CHECKING:
    from pathlib import Path

    from livespec_orchestrator_beads_fabro._beads_client import BeadsClient
    from livespec_orchestrator_beads_fabro.commands._dispatcher_engine_types import CommandRunner

__all__: list[str] = ["DrillClose", "close_drill"]

_ALLOWED = frozenset(
    ("repair", "master-observation", "reverting", "rollback-conflict", "collecting-failures")
)
_PHASE = "drill-closed"


@dataclass(frozen=True, kw_only=True)
class DrillClose:
    reading: IncidentReading
    lifecycle_state: str
    repayment_outstanding: bool


def _refusal(*, code: str, detail: str) -> AuthorityRefusal:
    return AuthorityRefusal(code=code, detail=detail)


def _successor(*, reading: IncidentReading) -> IncidentAttempt:
    return replace(
        reading.attempt,
        phase=_PHASE,
        operation_id=f"{reading.attempt.attempt_id}#drill-close",
        generation=reading.attempt.generation + 1,
        repayment_required=False,
    )


def _closed(*, reading: IncidentReading) -> DrillClose:
    return DrillClose(
        reading=reading,
        lifecycle_state=lifecycle_state_for(phase=_PHASE) or "",
        repayment_outstanding=False,
    )


def _recover_or_commit(
    *,
    client: BeadsClient,
    reading: IncidentReading,
    runner: CommandRunner,
    repo: Path,
    repository: str,
) -> IncidentReading | AuthorityRefusal:
    """Recover a fixed close operation or prove the current chain before writing it."""
    successor = _successor(reading=reading)
    current = require_current_generation(client=client, observed=reading)
    if isinstance(current, AuthorityRefusal):
        recovered = commit_transition(
            client=client, observed=reading, successor=successor, allow_drill_close=True
        )
        return current if isinstance(recovered, AuthorityRefusal) else recovered
    history = read_history(client=client, repository=repository, item_id=reading.attempt.item_id)
    if isinstance(history, AuthorityRefusal):
        return history
    evidence = recorded_drill_evidence(
        client=client,
        item_id=reading.attempt.item_id,
        history=history,
        runner=runner,
        repo=repo,
        repository=repository,
    )
    if evidence is not None:
        return evidence
    committed = commit_transition(
        client=client, observed=reading, successor=successor, allow_drill_close=True
    )
    return committed


def _publish_lifecycle(
    *, client: BeadsClient, committed: IncidentReading
) -> DrillClose | AuthorityRefusal:
    current = require_current_generation(client=client, observed=committed)
    if isinstance(current, AuthorityRefusal):
        return current
    existing = client.show_issue(issue_id=committed.attempt.item_id)
    if existing.get("status") == "done" and existing.get("assignee") is None:
        return _closed(reading=committed)
    result = change_claim(
        client=client,
        work_item_id=committed.attempt.item_id,
        writer="incident-drill-close",
        intent="drill-close",
        claim_tokens=True,
        status=lifecycle_state_for(phase=_PHASE) or "",
        clear_assignee=True,
        still_as_decided=lambda row: row.get("status") == "active",
    )
    if result.outcome != "applied":
        return _refusal(code="incident-drill-close-lifecycle-refused", detail=result.outcome)
    return _closed(reading=committed)


def close_drill(
    *,
    client: BeadsClient,
    reading: IncidentReading,
    runner: CommandRunner,
    repo: Path,
    repository: str,
) -> DrillClose | AuthorityRefusal:
    """Close only a freshly forge-proven drill under the normal generation fence."""
    if reading.attempt.phase not in _ALLOWED:
        return _refusal(
            code="incident-not-a-recorded-drill", detail=f"phase {reading.attempt.phase}"
        )
    committed = _recover_or_commit(
        client=client, reading=reading, runner=runner, repo=repo, repository=repository
    )
    if isinstance(committed, AuthorityRefusal):
        return committed
    return _publish_lifecycle(client=client, committed=committed)
