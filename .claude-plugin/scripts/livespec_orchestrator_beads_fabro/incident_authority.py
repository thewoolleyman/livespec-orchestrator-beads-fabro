"""Canonical incident authority API, backed only by authenticated ledger reads.

Use read-current immediately before a side effect. read-history proves a recorded
snapshot without authorizing current effects. Neither labels, invocation flags,
caller JSON, mutable metadata nor an ordinary progress comment can grant authority.
The writer must retain server-assigned conditional-close tokens for historical
proof. This reader does not bootstrap authority, fence a factory or grant workflow
publication authority; an absent sanctioned chain fails closed. Genesis decodes and
binds a first-publication request, then refuses it by name: no installed ledger
provider offers the required server-enforced first-root exclusion.
"""

# EXPEDITED_INCIDENT_RESPONSE flag: bd-ib-dzbwaq
from __future__ import annotations

from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro._incident_authority_types import (
    AuthorityRefusal,
    IncidentAttempt,
    IncidentReading,
)
from livespec_orchestrator_beads_fabro._incident_genesis import GenesisRequest, publish_genesis
from livespec_orchestrator_beads_fabro.effects._incident_authority_reader import read_authority
from livespec_orchestrator_beads_fabro.effects._incident_authority_transition import (
    commit_transition,
)

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro._beads_client import BeadsClient

__all__: list[str] = [
    "AuthorityRefusal",
    "GenesisRequest",
    "IncidentAttempt",
    "IncidentReading",
    "commit_incident_transition",
    "publish_incident_genesis",
    "read_incident_authority",
]


def read_incident_authority(
    *,
    client: BeadsClient,
    repository: str,
    item_id: str,
    query: dict[str, object],
    historical: bool = False,
) -> IncidentReading | AuthorityRefusal:
    """Read an immutable exact attempt or return its named trust-boundary refusal."""
    return read_authority(
        client=client, repository=repository, item_id=item_id, query=query, historical=historical
    )


def commit_incident_transition(
    *, client: BeadsClient, observed: IncidentReading, successor: IncidentAttempt
) -> IncidentReading | AuthorityRefusal:
    """Serialize an existing chain; entry and factory fencing remain separate."""
    return commit_transition(client=client, observed=observed, successor=successor)


def publish_incident_genesis(*, request: GenesisRequest) -> AuthorityRefusal:
    """Refuse first incident publication by name, with zero ledger writes."""
    return publish_genesis(request=request)
