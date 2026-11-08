"""Canonical incident authority API, backed only by authenticated ledger reads.

Use read-current immediately before a side effect. read-history proves a recorded
snapshot without authorizing current effects. Neither labels, invocation flags,
caller JSON, mutable metadata nor an ordinary progress comment can grant authority.
The writer must retain server-assigned conditional-close tokens for historical
proof. This reader does not fence a factory or grant workflow publication
authority; an absent sanctioned chain fails closed. Genesis publishes a first root
through the server-enforced close of the item's current dispatch claim token and
takes host ownership in that same guarded write, fencing queued or live factory
work; it refuses by name wherever that exclusion is not installed. Entry files a
scope no item covers once (`file_incident`), binds claim recovery and carrier
selection to the exact current generation (`incident_claim_decided`,
`carrier_selection`), and names a stale generation (`require_current_generation`).
"""

# EXPEDITED_INCIDENT_RESPONSE flag: bd-ib-dzbwaq
from __future__ import annotations

import time
from collections.abc import Callable
from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro._incident_authority_types import (
    AuthorityRefusal,
    IncidentAttempt,
    IncidentReading,
)
from livespec_orchestrator_beads_fabro._incident_entry import (
    CarrierSelection,
    FilingReceipt,
    FilingRequest,
    decode_filing_request,
    incident_claim_decided,
)
from livespec_orchestrator_beads_fabro._incident_genesis import GenesisReceipt, GenesisRequest
from livespec_orchestrator_beads_fabro.effects._incident_authority_reader import (
    read_authority,
    read_history,
    read_incident_head,
)
from livespec_orchestrator_beads_fabro.effects._incident_authority_transition import (
    commit_transition,
)
from livespec_orchestrator_beads_fabro.effects._incident_entry_writer import (
    carrier_selection,
    file_incident,
    require_current_generation,
)
from livespec_orchestrator_beads_fabro.effects._incident_genesis_recovery import Observations
from livespec_orchestrator_beads_fabro.effects._incident_genesis_writer import publish_genesis

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro._beads_client import BeadsClient

__all__: list[str] = [
    "AuthorityRefusal",
    "CarrierSelection",
    "FilingReceipt",
    "FilingRequest",
    "GenesisReceipt",
    "GenesisRequest",
    "IncidentAttempt",
    "IncidentReading",
    "carrier_selection",
    "commit_incident_transition",
    "decode_filing_request",
    "file_incident",
    "incident_claim_decided",
    "publish_incident_genesis",
    "read_incident_authority",
    "read_incident_head",
    "read_incident_history",
    "require_current_generation",
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


def read_incident_history(
    *, client: BeadsClient, repository: str, item_id: str
) -> tuple[IncidentAttempt, ...] | AuthorityRefusal:
    """Every retained attempt of one item, oldest first: provenance that authorizes nothing."""
    return read_history(client=client, repository=repository, item_id=item_id)


def commit_incident_transition(
    *, client: BeadsClient, observed: IncidentReading, successor: IncidentAttempt
) -> IncidentReading | AuthorityRefusal:
    """Serialize an existing chain; entry and factory fencing remain separate."""
    return commit_transition(client=client, observed=observed, successor=successor)


def publish_incident_genesis(
    *,
    client: BeadsClient,
    request: GenesisRequest,
    claim_tokens: bool,
    clock: Callable[[], float] = time.monotonic,
    observations: Observations | None = None,
) -> GenesisReceipt | AuthorityRefusal:
    """Publish a first root by winning the item's current claim token, or refuse by name.

    Canonical entry over an identified item: the win moves the item to `active`
    under the incident owner and retains the prior factory claim.
    """
    return publish_genesis(
        client=client,
        request=request,
        claim_tokens=claim_tokens,
        clock=clock,
        observations=observations,
    )
