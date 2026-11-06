"""Authenticated Beads reads for the canonical retained incident token chain.

The open successor is re-read before returning so an observed ownership change
cannot be hidden by a stale item metadata projection. Conditional closes happen
server-side, through public bd; no reader writes, initializes or repairs authority.
"""

# EXPEDITED_INCIDENT_RESPONSE flag: bd-ib-dzbwaq
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from livespec_orchestrator_beads_fabro._incident_authority_payload import (
    GENESIS_MARKER,
    TOKEN_TITLE,
    TRANSITION_MARKER,
    decode_attempt,
    decode_record,
    query_matches,
    unsupported_carrier,
)
from livespec_orchestrator_beads_fabro._incident_authority_types import (
    AuthorityRefusal,
    IncidentAttempt,
    IncidentReading,
)
from livespec_orchestrator_beads_fabro._incident_carrier import CARRIER_UNSUPPORTED
from livespec_orchestrator_beads_fabro.effects._incident_genesis_fence import (
    FENCED_GENESIS_KEYS,
    fenced_root_holds,
)
from livespec_orchestrator_beads_fabro.errors import (
    BeadsCommandError,
    BeadsConnectionError,
    BeadsCredentialMissingError,
    BeadsMappingError,
    BeadsTenantMissingError,
)

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro._beads_client import BeadsClient

__all__: list[str] = ["read_authority", "read_repository_history"]
_GENESIS_KEYS = frozenset(("schema", "repository", "item_id", "root_token_id"))
_TRANSITION_KEYS = frozenset(
    ("schema", "repository", "item_id", "prior_token_id", "next_token_id", "attempt")
)
_MAX_TOKENS = 256
_UNAVAILABLE = (
    BeadsCommandError,
    BeadsConnectionError,
    BeadsCredentialMissingError,
    BeadsMappingError,
    BeadsTenantMissingError,
)


def _refuse(*, code: str, detail: str) -> AuthorityRefusal:
    return AuthorityRefusal(code=code, detail=detail)


def _genesis(*, client: BeadsClient, repository: str, item_id: str) -> str | AuthorityRefusal:
    item = client.show_issue(issue_id=item_id)
    if item.get("id") != item_id:
        return _refuse(code="incident-authority-item-mismatch", detail=item_id)
    roots: set[str] = set()
    for comment in client.list_comments(issue_id=item_id):
        text = comment.get("text")
        if not isinstance(text, str) or not text.startswith(GENESIS_MARKER):
            continue
        record = decode_record(
            text=text, marker=GENESIS_MARKER, keys=_GENESIS_KEYS
        ) or decode_record(text=text, marker=GENESIS_MARKER, keys=FENCED_GENESIS_KEYS)
        if (
            record is None
            or record["repository"] != repository
            or record["item_id"] != item_id
            or not isinstance(record["root_token_id"], str)
            or not record["root_token_id"]
            or not fenced_root_holds(client=client, record=record, repository=repository)
        ):
            return _refuse(code="incident-authority-invalid-genesis", detail=item_id)
        roots.add(record["root_token_id"])
    if len(roots) != 1:
        return _refuse(
            code="incident-authority-ambiguous" if roots else "incident-authority-missing",
            detail=item_id,
        )
    return next(iter(roots))


def _transition(
    *,
    record: dict[str, Any],
    token: str,
    repository: str,
    item_id: str,
    generation: int,
    used_operations: set[str],
) -> tuple[IncidentAttempt, str] | AuthorityRefusal:
    payload = decode_record(
        text=record.get("close_reason"), marker=TRANSITION_MARKER, keys=_TRANSITION_KEYS
    )
    if (
        payload is None
        or payload["repository"] != repository
        or payload["item_id"] != item_id
        or payload["prior_token_id"] != token
        or not isinstance(payload["next_token_id"], str)
        or not payload["next_token_id"]
    ):
        return _refuse(code="incident-authority-invalid-transition", detail=token)
    if unsupported_carrier(value=payload["attempt"]):
        return _refuse(code=CARRIER_UNSUPPORTED, detail=token)
    attempt = decode_attempt(value=payload["attempt"])
    if (
        attempt is None
        or attempt.repository != repository
        or attempt.item_id != item_id
        or attempt.generation != generation
    ):
        return _refuse(code="incident-authority-invalid-attempt", detail=token)
    if attempt.operation_id in used_operations:
        return _refuse(code="incident-authority-reused-operation", detail=attempt.operation_id)
    return attempt, payload["next_token_id"]


def _walk(
    *, client: BeadsClient, repository: str, item_id: str, root: str
) -> tuple[list[tuple[str, IncidentAttempt]], str] | AuthorityRefusal:
    seen: set[str] = set()
    history: list[tuple[str, IncidentAttempt]] = []
    token = root
    for _ in range(_MAX_TOKENS):
        if token in seen:
            return _refuse(code="incident-authority-cycle", detail=token)
        seen.add(token)
        record = client.show_issue(issue_id=token)
        if record.get("id") != token or record.get("title") != TOKEN_TITLE:
            return _refuse(code="incident-authority-invalid-token", detail=token)
        if record.get("status") == "backlog":
            return history, token
        if record.get("status") != "closed":
            return _refuse(code="incident-authority-invalid-token-state", detail=token)
        transition = _transition(
            record=record,
            token=token,
            repository=repository,
            item_id=item_id,
            generation=len(history) + 1,
            used_operations={prior.operation_id for _, prior in history},
        )
        if isinstance(transition, AuthorityRefusal):
            return transition
        attempt, successor = transition
        history.append((token, attempt))
        token = successor
    return _refuse(code="incident-authority-history-limit", detail=root)


def _select(
    *,
    client: BeadsClient,
    repository: str,
    item_id: str,
    query: dict[str, object],
    historical: bool,
) -> IncidentReading | AuthorityRefusal:
    root = _genesis(client=client, repository=repository, item_id=item_id)
    if isinstance(root, AuthorityRefusal):
        return root
    chain = _walk(client=client, repository=repository, item_id=item_id, root=root)
    if isinstance(chain, AuthorityRefusal):
        return chain
    history, current = chain
    candidates = history if historical else history[-1:]
    matches = [
        (token, attempt)
        for token, attempt in candidates
        if query_matches(attempt=attempt, query=query)
    ]
    if len(matches) != 1:
        return _refuse(code="incident-authority-identity-mismatch", detail=item_id)
    committed, attempt = matches[0]
    # A close is the server-side generation fence. Re-check the successor AFTER
    # decoding/selecting; an old invocation can never silently follow a new head.
    standing = client.show_issue(issue_id=current)
    if standing.get("status") != "backlog" or standing.get("title") != TOKEN_TITLE:
        return _refuse(code="incident-authority-changed", detail=current)
    return IncidentReading(
        attempt=attempt,
        committed_token_id=committed,
        current_token_id=current,
        is_current=history[-1][0] == committed,
        operation_ids=tuple(snapshot.operation_id for _, snapshot in history),
    )


def read_authority(
    *,
    client: BeadsClient,
    repository: str,
    item_id: str,
    query: dict[str, object],
    historical: bool,
) -> IncidentReading | AuthorityRefusal:
    """A tenant outage is unavailable, never an empty or normal-mode authority."""
    try:
        return _select(
            client=client,
            repository=repository,
            item_id=item_id,
            query=query,
            historical=historical,
        )
    except _UNAVAILABLE as exc:
        return _refuse(code="incident-authority-unavailable", detail=str(exc))


def _history(
    *, client: BeadsClient, repository: str, item_id: str
) -> tuple[IncidentReading, ...] | AuthorityRefusal:
    root = _genesis(client=client, repository=repository, item_id=item_id)
    if isinstance(root, AuthorityRefusal):
        return root
    chain = _walk(client=client, repository=repository, item_id=item_id, root=root)
    if isinstance(chain, AuthorityRefusal):
        return chain
    history, current = chain
    standing = client.show_issue(issue_id=current)
    if standing.get("status") != "backlog" or standing.get("title") != TOKEN_TITLE:
        return _refuse(code="incident-authority-changed", detail=current)
    operations = tuple(attempt.operation_id for _, attempt in history)
    return tuple(
        IncidentReading(
            attempt=attempt,
            committed_token_id=token,
            current_token_id=current,
            is_current=index == len(history) - 1,
            operation_ids=operations,
        )
        for index, (token, attempt) in enumerate(history)
    )


def _genesis_record(*, text: object) -> dict[str, Any] | None:
    return decode_record(text=text, marker=GENESIS_MARKER, keys=_GENESIS_KEYS) or decode_record(
        text=text, marker=GENESIS_MARKER, keys=FENCED_GENESIS_KEYS
    )


def _located_items(*, client: BeadsClient, repository: str | None) -> list[tuple[str, str]]:
    """Locate incident items from genesis comments; the authenticated walk decides.

    Token records are no-history records that `list_issues` does not return, so the
    items themselves are the only enumerable locator.
    """
    located: set[tuple[str, str]] = set()
    for record in client.list_issues():
        item_id = record.get("id")
        if not isinstance(item_id, str) or record.get("title") == TOKEN_TITLE:
            continue
        if record.get("comment_count") == 0:
            continue
        for comment in client.list_comments(issue_id=item_id):
            genesis = _genesis_record(text=comment.get("text"))
            found = None if genesis is None else genesis["repository"]
            if isinstance(found, str) and repository in {None, found}:
                located.add((found, item_id))
    return sorted(located)


def read_repository_history(
    *, client: BeadsClient, repository: str | None
) -> tuple[IncidentReading, ...] | AuthorityRefusal:
    """Every committed attempt of every incident in a tenant, or one named refusal.

    Genesis comments only LOCATE candidate incidents; each candidate is then
    authenticated through its genesis and token chain. Any unreadable or invalid
    chain refuses the whole read, so a broken ledger is never an empty one.
    """
    try:
        readings: list[IncidentReading] = []
        for found, item_id in _located_items(client=client, repository=repository):
            history = _history(client=client, repository=found, item_id=item_id)
            if isinstance(history, AuthorityRefusal):
                return history
            readings.extend(history)
        return tuple(readings)
    except _UNAVAILABLE as exc:
        return _refuse(code="incident-authority-unavailable", detail=str(exc))
