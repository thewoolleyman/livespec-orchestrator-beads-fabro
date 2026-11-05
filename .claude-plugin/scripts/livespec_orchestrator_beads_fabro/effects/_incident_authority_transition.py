"""Server conditional-close transitions on an existing incident authority.

This is a generation writer, not canonical entry or a factory-fence capability.
It never initializes authority, mutates lifecycle state or grants host takeover.
A close exit code is never a winner verdict; the committed reason is read back.
"""

# EXPEDITED_INCIDENT_RESPONSE flag: bd-ib-dzbwaq
from __future__ import annotations

import json
from dataclasses import asdict
from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro._incident_authority_payload import (
    TOKEN_TITLE,
    TRANSITION_MARKER,
    attempt_record,
    decode_attempt,
)
from livespec_orchestrator_beads_fabro._incident_authority_types import (
    AuthorityRefusal,
    IncidentAttempt,
    IncidentReading,
)
from livespec_orchestrator_beads_fabro._incident_carrier import carrier_successor_allowed
from livespec_orchestrator_beads_fabro.effects import parse_json
from livespec_orchestrator_beads_fabro.effects._incident_authority_reader import read_authority
from livespec_orchestrator_beads_fabro.errors import (
    BeadsCommandError,
    BeadsConnectionError,
    BeadsCredentialMissingError,
    BeadsMappingError,
    BeadsTenantMissingError,
)

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro._beads_client import BeadsClient

__all__: list[str] = ["commit_transition"]


def _read(
    *, client: BeadsClient, attempt: IncidentAttempt, historical: bool
) -> IncidentReading | AuthorityRefusal:
    query = {
        key: value
        for key, value in asdict(attempt).items()
        if key in {"attempt_id", "phase", "operation_id", "generation", "owner"}
    }
    return read_authority(
        client=client,
        repository=attempt.repository,
        item_id=attempt.item_id,
        query=query,
        historical=historical,
    )


def _valid_successor(*, before: IncidentAttempt, after: IncidentAttempt) -> bool:
    return (
        before.repository == after.repository
        and before.item_id == after.item_id
        and after.generation == before.generation + 1
        and before.operation_id != after.operation_id
        and set(before.original_paths).issubset(after.original_paths)
        and carrier_successor_allowed(
            before=before.carrier,
            after=after.carrier,
            before_pr=before.pr_number,
            after_pr=after.pr_number,
        )
    )


def _close(
    *, client: BeadsClient, observed: IncidentReading, successor: IncidentAttempt
) -> IncidentReading | AuthorityRefusal:
    candidate = client.create_no_history_issue(
        title=TOKEN_TITLE,
        description="Retained immutable incident authority transition. Not a work item.",
    )
    payload = {
        "schema": 1,
        "repository": successor.repository,
        "item_id": successor.item_id,
        "prior_token_id": observed.current_token_id,
        "next_token_id": candidate,
        "attempt": attempt_record(attempt=successor),
    }
    reason = TRANSITION_MARKER + json.dumps(payload, sort_keys=True, separators=(",", ":"))
    client.close_issue_without_verdict(issue_id=observed.current_token_id, reason=reason)
    standing = client.show_issue(issue_id=observed.current_token_id)
    if standing.get("status") != "closed" or not isinstance(standing.get("close_reason"), str):
        return AuthorityRefusal(code="incident-transition-outcome-unknown", detail=candidate)
    if standing["close_reason"] != reason:
        client.delete_issue(issue_id=candidate)
        return AuthorityRefusal(
            code="incident-transition-lost-race", detail=observed.current_token_id
        )
    return _read(client=client, attempt=successor, historical=False)


def _commit(
    *, client: BeadsClient, observed: IncidentReading, successor: IncidentAttempt
) -> IncidentReading | AuthorityRefusal:
    decoded = decode_attempt(value=parse_json(text=json.dumps(attempt_record(attempt=successor))))
    if decoded is None or not _valid_successor(before=observed.attempt, after=decoded):
        return AuthorityRefusal(
            code="incident-transition-invalid-successor", detail=observed.attempt.item_id
        )
    recovered = _read(client=client, attempt=decoded, historical=True)
    if isinstance(recovered, IncidentReading):
        return (
            recovered
            if recovered.attempt == decoded
            else AuthorityRefusal(
                code="incident-transition-operation-conflict", detail=decoded.operation_id
            )
        )
    current = _read(client=client, attempt=observed.attempt, historical=False)
    if isinstance(current, AuthorityRefusal):
        return current
    if current != observed or not observed.is_current:
        return AuthorityRefusal(
            code="incident-transition-stale-observation", detail=observed.attempt.item_id
        )
    if decoded.operation_id in current.operation_ids:
        return AuthorityRefusal(
            code="incident-transition-operation-reused", detail=decoded.operation_id
        )
    return _close(client=client, observed=observed, successor=decoded)


def commit_transition(
    *, client: BeadsClient, observed: IncidentReading, successor: IncidentAttempt
) -> IncidentReading | AuthorityRefusal:
    """Commit one next generation, or recover a retry without another effect."""
    try:
        return _commit(client=client, observed=observed, successor=successor)
    except (
        BeadsCommandError,
        BeadsConnectionError,
        BeadsCredentialMissingError,
        BeadsMappingError,
        BeadsTenantMissingError,
    ) as exc:
        # Keep an unknown candidate: deleting it could sever our own successful
        # transition after a failed readback. A retry recovers the original.
        return AuthorityRefusal(code="incident-transition-unavailable", detail=str(exc))
