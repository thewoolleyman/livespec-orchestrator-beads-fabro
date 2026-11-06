"""Canonical incident filing, and the current-generation gate every incident effect takes.

`file_incident` makes one identified item for a scope no item covers: a
single `bd create` that names the item's first claim token, then the status
and the retained deferral record. It is idempotent on the operation id, so a
retry after a lost reply recovers the same identity and a failed
initialization never files a second one. `require_current_generation`
re-reads the chain immediately before a side effect and names a stale
generation; `carrier_selection` binds branch and pull-request selection to
that re-read rather than to a snapshot.
"""

# EXPEDITED_INCIDENT_RESPONSE flag: bd-ib-dzbwaq
from __future__ import annotations

from dataclasses import asdict
from typing import TYPE_CHECKING, Any, cast

from livespec_orchestrator_beads_fabro._beads_client import IssueDraft
from livespec_orchestrator_beads_fabro._ids import new_work_item_id
from livespec_orchestrator_beads_fabro._incident_authority_types import (
    AuthorityRefusal,
    IncidentReading,
)
from livespec_orchestrator_beads_fabro._incident_entry import (
    ENTRY_LABEL,
    GENERATION_STALE,
    CarrierSelection,
    FilingReceipt,
    FilingRequest,
    deferred_admission_comment,
    filing_description,
    filing_digest,
    filing_identity,
    filing_metadata,
    select_carrier,
)
from livespec_orchestrator_beads_fabro._incident_genesis import GENESIS_CAPABILITY_UNAVAILABLE
from livespec_orchestrator_beads_fabro._store_claim_token_creation import (
    create_issue_naming_first_claim_token,
)
from livespec_orchestrator_beads_fabro._store_claim_tokens import CLAIM_TOKEN_METADATA_KEY
from livespec_orchestrator_beads_fabro._store_ready_dwell import utc_now_iso
from livespec_orchestrator_beads_fabro._store_statuses import beads_status_for
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

__all__: list[str] = ["carrier_selection", "file_incident", "require_current_generation"]

_OPERATION_CONFLICT = "incident-operation-conflict"
_IDENTITY_MISMATCH = "incident-authority-identity-mismatch"
_BACKLOG = "backlog"
_LEDGER_ERRORS = (
    BeadsCommandError,
    BeadsConnectionError,
    BeadsCredentialMissingError,
    BeadsMappingError,
    BeadsTenantMissingError,
)


def _refuse(*, code: str, detail: str) -> AuthorityRefusal:
    return AuthorityRefusal(code=code, detail=detail)


def _token_of(*, client: BeadsClient, item_id: str) -> str | None:
    raw = client.show_issue(issue_id=item_id).get("metadata")
    metadata = cast("dict[str, Any]", raw) if isinstance(raw, dict) else {}
    token = metadata.get(CLAIM_TOKEN_METADATA_KEY)
    return token if isinstance(token, str) and token.strip() else None


def _recorded(
    *, client: BeadsClient, request: FilingRequest
) -> FilingReceipt | AuthorityRefusal | None:
    """The item this operation already filed, its conflict, or None for a first filing."""
    digest = filing_digest(request=request)
    for record in client.list_issues():
        identity = filing_identity(record=record)
        if identity is None or identity[0] != request.operation_id:
            continue
        if identity[1] != digest:
            return _refuse(code=_OPERATION_CONFLICT, detail=request.operation_id)
        item_id = str(record["id"])
        token = _token_of(client=client, item_id=item_id)
        if token is None:
            return _refuse(code="incident-filing-claim-token-missing", detail=item_id)
        return FilingReceipt(
            item_id=item_id, claim_token_id=token, request_digest=digest, recovered=True
        )
    return None


def _file(
    *, client: BeadsClient, prefix: str, request: FilingRequest
) -> FilingReceipt | AuthorityRefusal:
    recorded = _recorded(client=client, request=request)
    if recorded is not None:
        return recorded
    item_id = new_work_item_id(prefix=prefix)
    create_issue_naming_first_claim_token(
        client=client,
        names_token=True,
        draft=IssueDraft(
            issue_id=item_id,
            issue_type="bug",
            title=request.title,
            description=filing_description(request=request),
            assignee=None,
            created_at=utc_now_iso(),
            labels=[ENTRY_LABEL],
            metadata=filing_metadata(request=request),
        ),
    )
    client.update_issue(issue_id=item_id, status=beads_status_for(status=_BACKLOG))
    client.add_comment(
        issue_id=item_id,
        body=deferred_admission_comment(
            item_id=item_id, operation_id=request.operation_id, principal=request.principal
        ),
    )
    token = _token_of(client=client, item_id=item_id)
    if token is None:
        return _refuse(code="incident-filing-claim-token-missing", detail=item_id)
    return FilingReceipt(
        item_id=item_id,
        claim_token_id=token,
        request_digest=filing_digest(request=request),
        recovered=False,
    )


def file_incident(
    *, client: BeadsClient, prefix: str, request: FilingRequest, claim_tokens: bool
) -> FilingReceipt | AuthorityRefusal:
    """File one minimal identified incident, recover an exact retry, or refuse by name."""
    if not claim_tokens:
        return _refuse(
            code=GENESIS_CAPABILITY_UNAVAILABLE,
            detail=(
                f"{request.operation_id}: the committed claim-token cutover is off, so a filed "
                "item could not be entered; no item was filed"
            ),
        )
    try:
        return _file(client=client, prefix=prefix, request=request)
    except _LEDGER_ERRORS as exc:
        return _refuse(code="incident-filing-unavailable", detail=str(exc))


def _read(
    *, client: BeadsClient, observed: IncidentReading, historical: bool
) -> IncidentReading | AuthorityRefusal:
    attempt = observed.attempt
    return read_authority(
        client=client,
        repository=attempt.repository,
        item_id=attempt.item_id,
        query={
            key: value
            for key, value in asdict(attempt).items()
            if key in {"attempt_id", "phase", "operation_id", "generation", "owner"}
        },
        historical=historical,
    )


def require_current_generation(
    *, client: BeadsClient, observed: IncidentReading
) -> IncidentReading | AuthorityRefusal:
    """Re-read the chain now; an observation the head has moved past is stale by name.

    Taken immediately before a proof write, a claim consumption or a
    completion, so a late old generation is refused before its side effect.
    """
    stale = _refuse(code=GENERATION_STALE, detail=observed.attempt.item_id)
    current = _read(client=client, observed=observed, historical=False)
    if isinstance(current, IncidentReading):
        return current if current == observed else stale
    if current.code != _IDENTITY_MISMATCH:
        return current
    recorded = _read(client=client, observed=observed, historical=True)
    return stale if isinstance(recorded, IncidentReading) else current


def carrier_selection(
    *, client: BeadsClient, reading: IncidentReading
) -> CarrierSelection | AuthorityRefusal:
    """Select the exact current carrier: its ref, published head and real PR number."""
    current = require_current_generation(client=client, observed=reading)
    if isinstance(current, AuthorityRefusal):
        return current
    return select_carrier(reading=current)
