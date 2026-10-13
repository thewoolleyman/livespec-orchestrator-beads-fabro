"""Creating a plan epic's FIRST authority token — the one write that may.

Every later transition is made safe by closing the CURRENT token, so the first
token has no predecessor to close and cannot be created by an exclusion. Nor
can a deterministic create-if-absent stand in: relay research note 007
measured that a duplicate explicit-id create is an UPSERT which reopens a
closed record and erases its close reason, exiting 0 and printing no warning.

Genesis therefore happens only where one writer can exist by construction —
`create_thread`, whose epic id no other party has yet seen, and the sanctioned
plan-record migration, a deliberate once-per-epic operator act. Every other
sanctioned writer leaves a chainless epic alone: its legacy pointer stays
readable and `read_chain_head` reports the missing-tracking finding that names
that migration as the remedy.

THREE PROPERTIES AN EDITOR MUST NOT INVERT.

AN EPIC THAT ALREADY NAMES A CHAIN IS REFUSED BEFORE ANYTHING IS CREATED. A
chain is an exclusion only while every writer closes the SAME token, so two
chains on one epic admit two simultaneous winners — the exact failure the
design exists to prevent. Refusing before the create is what makes a mistaken
second migration harmless rather than merely reported.

THE WRITE IS READ BACK, and a genesis that lost is reported rather than
assumed. Two operators migrating one epic at the same moment is the residual
risk this narrows; the cache write is a client-side read-modify-write, so a
later one simply replaces the earlier (relay research note 004: concurrent
distinct-key metadata writes lost an update in 3 of 12 trials, both exiting 0).

THE LOSER DELETES THE TOKEN IT CREATED. An orphan token nothing names is worse
than none: it is invisible to every list surface, so nothing would ever
reconcile it, and a later reader handed its id would follow a chain the epic
does not have.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro._beads_client import make_beads_client
from livespec_orchestrator_beads_fabro.commands._plan_epoch_chain_head import epic_chain_cache
from livespec_orchestrator_beads_fabro.commands._plan_epoch_findings import (
    genesis_already_named_finding,
    genesis_unconfirmed_finding,
)
from livespec_orchestrator_beads_fabro.commands._plan_epoch_projection import write_chain_cache
from livespec_orchestrator_beads_fabro.commands._plan_epoch_tokens import (
    create_token,
    discard_token,
)

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.commands._plan_epoch_findings import ChainFinding
    from livespec_orchestrator_beads_fabro.types import StoreConfig

__all__: list[str] = [
    "create_genesis_token",
    "write_chain_cache",
]


def create_genesis_token(*, config: StoreConfig, epic_id: str) -> str | ChainFinding:
    """Create one epic's genesis token and record it, or report why it did not."""
    client = make_beads_client(config=config)
    standing = epic_chain_cache(client=client, epic_id=epic_id)
    if standing is not None:
        return genesis_already_named_finding(epic_id=epic_id, token_id=standing.current)
    genesis = create_token(client=client)
    write_chain_cache(client=client, epic_id=epic_id, latest_closed=None, current=genesis)
    confirmed = epic_chain_cache(client=client, epic_id=epic_id)
    if confirmed is None or confirmed.current != genesis:
        discard_token(client=client, token_id=genesis)
        return genesis_unconfirmed_finding(
            epic_id=epic_id,
            token_id=genesis,
            observed=None if confirmed is None else confirmed.current,
        )
    return genesis
