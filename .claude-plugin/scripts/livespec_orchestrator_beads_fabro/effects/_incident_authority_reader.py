"""Authenticated Beads reads for the canonical retained incident token chain.

The open successor is re-read before returning so an observed ownership change
cannot be hidden by a stale item metadata projection. Conditional closes happen
server-side, through public bd; no reader writes, initializes or repairs authority.

A current read does not re-read the chain from genesis. The item's head hint names
the latest closed token the transition writer recorded, and the walk starts there
and follows the tokens' own links to the open successor, so the records read are
bounded by the hint's lag rather than by the number of generations. The hint is a
start point and never authority: a stale hint only lengthens the forward walk, and
an absent, open or unreadable one reads the whole chain from the genesis root. A
historical read, and the history read, always walk the whole chain.
"""

# EXPEDITED_INCIDENT_RESPONSE flag: bd-ib-dzbwaq
from __future__ import annotations

from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro._incident_authority_payload import (
    TOKEN_TITLE,
    query_matches,
)
from livespec_orchestrator_beads_fabro._incident_authority_types import (
    AuthorityRefusal,
    IncidentAttempt,
    IncidentReading,
)
from livespec_orchestrator_beads_fabro.effects._incident_authority_chain import (
    read_chain,
    read_genesis,
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

__all__: list[str] = ["read_authority", "read_history", "read_incident_head"]


def _refuse(*, code: str, detail: str) -> AuthorityRefusal:
    return AuthorityRefusal(code=code, detail=detail)


def _select(
    *,
    client: BeadsClient,
    repository: str,
    item_id: str,
    query: dict[str, object],
    historical: bool,
) -> IncidentReading | AuthorityRefusal:
    genesis = read_genesis(client=client, repository=repository, item_id=item_id)
    if isinstance(genesis, AuthorityRefusal):
        return genesis
    chain = read_chain(
        client=client,
        repository=repository,
        item_id=item_id,
        genesis=genesis,
        hinted=not historical,
    )
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
    committed = matches[0][0]
    return _reading(client=client, history=history, current=current, committed=committed)


def _reading(
    *,
    client: BeadsClient,
    history: list[tuple[str, IncidentAttempt]],
    current: str,
    committed: str,
) -> IncidentReading | AuthorityRefusal:
    # A close is the server-side generation fence. Re-check the successor AFTER
    # decoding/selecting; an old invocation can never silently follow a new head.
    standing = client.show_issue(issue_id=current)
    if standing.get("status") != "backlog" or standing.get("title") != TOKEN_TITLE:
        return _refuse(code="incident-authority-changed", detail=current)
    attempt = next(snapshot for token, snapshot in history if token == committed)
    return IncidentReading(
        attempt=attempt,
        committed_token_id=committed,
        current_token_id=current,
        is_current=history[-1][0] == committed,
        operation_ids=tuple(snapshot.operation_id for _, snapshot in history),
    )


_OUTAGES = (
    BeadsCommandError,
    BeadsConnectionError,
    BeadsCredentialMissingError,
    BeadsMappingError,
    BeadsTenantMissingError,
)


def _head(
    *, client: BeadsClient, repository: str, item_id: str
) -> IncidentReading | AuthorityRefusal:
    genesis = read_genesis(client=client, repository=repository, item_id=item_id)
    if isinstance(genesis, AuthorityRefusal):
        return genesis
    chain = read_chain(
        client=client, repository=repository, item_id=item_id, genesis=genesis, hinted=True
    )
    if isinstance(chain, AuthorityRefusal):
        return chain
    history, current = chain
    if not history:
        return _refuse(code="incident-authority-identity-mismatch", detail=item_id)
    return _reading(client=client, history=history, current=current, committed=history[-1][0])


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
    except _OUTAGES as exc:
        return _refuse(code="incident-authority-unavailable", detail=str(exc))


def read_history(
    *, client: BeadsClient, repository: str, item_id: str
) -> tuple[IncidentAttempt, ...] | AuthorityRefusal:
    """Every committed attempt of the retained chain, oldest first, or a named refusal.

    History authorizes no current effect: it is the provenance a consumer binds
    exact PR, head and landed identities against after labels and environment
    are gone. A chain that cannot be walked refuses by name; an outage is
    unavailable, never an empty history.
    """
    try:
        genesis = read_genesis(client=client, repository=repository, item_id=item_id)
        if isinstance(genesis, AuthorityRefusal):
            return genesis
        chain = read_chain(
            client=client, repository=repository, item_id=item_id, genesis=genesis, hinted=False
        )
    except _OUTAGES as exc:
        return _refuse(code="incident-authority-unavailable", detail=str(exc))
    if isinstance(chain, AuthorityRefusal):
        return chain
    history, _current = chain
    return tuple(attempt for _, attempt in history)


def read_incident_head(
    *, client: BeadsClient, repository: str, item_id: str
) -> IncidentReading | AuthorityRefusal:
    """The chain's current generation, selected by the chain itself rather than a query.

    For a consumer that knows only the item: merged-PR resolution and proof
    publication. The reading is current at the instant of the read; a writer
    still revalidates it immediately before its side effect.
    """
    try:
        return _head(client=client, repository=repository, item_id=item_id)
    except _OUTAGES as exc:
        return _refuse(code="incident-authority-unavailable", detail=str(exc))
