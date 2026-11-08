"""Whether an item is an incident, and what its retained chain says it still owes.

Every closure route asks this before it closes an item. The item's own genesis
comment is what LOCATES the incident: a label, metadata key, flag or title
locates nothing, because any of those could be stripped and would then let an
expedited merge close the item. The repository the genesis names selects the
chain, and the canonical reader walks it. An item whose comments cannot be read,
whose genesis is malformed or ambiguous, or whose chain refuses is UNREADABLE,
which every route treats as an outstanding obligation, never as a normal item.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from livespec_orchestrator_beads_fabro._incident_authority_payload import (
    GENESIS_MARKER,
    decode_record,
)
from livespec_orchestrator_beads_fabro._incident_authority_types import (
    AuthorityRefusal,
    IncidentAttempt,
    IncidentReading,
)
from livespec_orchestrator_beads_fabro._incident_completion_rules import (
    IncidentCompletionEvidence,
    completion_obligations,
)
from livespec_orchestrator_beads_fabro.effects._incident_authority_reader import (
    read_history,
    read_incident_head,
)
from livespec_orchestrator_beads_fabro.effects._incident_genesis_fence import FENCED_GENESIS_KEYS
from livespec_orchestrator_beads_fabro.errors import (
    BeadsCommandError,
    BeadsConnectionError,
    BeadsCredentialMissingError,
    BeadsMappingError,
    BeadsTenantMissingError,
)

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro._beads_client import BeadsClient, BeadsRecord

__all__: list[str] = ["IncidentStanding", "read_incident_standing"]

_GENESIS_KEYS = frozenset(("schema", "repository", "item_id", "root_token_id"))
_OUTAGES = (
    BeadsCommandError,
    BeadsConnectionError,
    BeadsCredentialMissingError,
    BeadsMappingError,
    BeadsTenantMissingError,
)


@dataclass(frozen=True, kw_only=True)
class IncidentStanding:
    """One item's incident standing; an empty `outstanding` is what lets a route close it.

    `normal` is an item with no incident genesis. `incident` carries the walked
    chain and every obligation it owes with nothing yet observed, which is empty
    only once the chain recorded `closed`. `unreadable` names why the standing
    could not be established. `reading` is the chain's head as this read
    observed it: the generation a later side effect revalidates, so an effect
    against a generation the chain has since moved past is refused.
    """

    item_id: str
    kind: Literal["normal", "incident", "unreadable"]
    repository: str | None
    history: tuple[IncidentAttempt, ...]
    outstanding: tuple[str, ...]
    reading: IncidentReading | None = None


def _unreadable(*, item_id: str, reason: str, repository: str | None = None) -> IncidentStanding:
    return IncidentStanding(
        item_id=item_id,
        kind="unreadable",
        repository=repository,
        history=(),
        outstanding=(reason,),
    )


def _genesis_repositories(*, comments: list[BeadsRecord]) -> set[str] | None:
    """The repositories the item's genesis comments name; None when one is malformed."""
    repositories: set[str] = set()
    for comment in comments:
        text = comment.get("text")
        if not isinstance(text, str) or not text.startswith(GENESIS_MARKER):
            continue
        record = decode_record(text=text, marker=GENESIS_MARKER, keys=_GENESIS_KEYS) or (
            decode_record(text=text, marker=GENESIS_MARKER, keys=FENCED_GENESIS_KEYS)
        )
        repository = None if record is None else record.get("repository")
        if not isinstance(repository, str) or not repository:
            return None
        repositories.add(repository)
    return repositories


def read_incident_standing(*, client: BeadsClient, item_id: str) -> IncidentStanding:
    """Read `item_id`'s standing; a tenant outage is unreadable, never a normal item."""
    try:
        comments = client.list_comments(issue_id=item_id)
    except _OUTAGES as exc:
        return _unreadable(item_id=item_id, reason=f"incident-standing-unavailable:{exc}")
    repositories = _genesis_repositories(comments=comments)
    if repositories is None:
        return _unreadable(item_id=item_id, reason="incident-authority-invalid-genesis")
    if not repositories:
        return IncidentStanding(
            item_id=item_id, kind="normal", repository=None, history=(), outstanding=()
        )
    if len(repositories) != 1:
        return _unreadable(item_id=item_id, reason="incident-authority-ambiguous")
    return _chain_standing(client=client, item_id=item_id, repository=next(iter(repositories)))


def _chain_standing(*, client: BeadsClient, item_id: str, repository: str) -> IncidentStanding:
    """Walk the chain the genesis names: its history, head and outstanding obligations."""
    history = read_history(client=client, repository=repository, item_id=item_id)
    if isinstance(history, AuthorityRefusal):
        return _unreadable(
            item_id=item_id,
            reason=f"incident-authority-unreadable:{history.code}",
            repository=repository,
        )
    head = read_incident_head(client=client, repository=repository, item_id=item_id)
    if isinstance(head, AuthorityRefusal):
        return _unreadable(
            item_id=item_id,
            reason=f"incident-authority-unreadable:{head.code}",
            repository=repository,
        )
    return IncidentStanding(
        item_id=item_id,
        kind="incident",
        repository=repository,
        history=history,
        outstanding=completion_obligations(history=history, evidence=IncidentCompletionEvidence()),
        reading=head,
    )
