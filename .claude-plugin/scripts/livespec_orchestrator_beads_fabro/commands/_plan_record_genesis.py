"""The plan-record migration's GENESIS leg: starting a live epic's chain.

Relay research note 007 names exactly two writes that may create a plan epic's
first authority token, and this is the second of them: the sanctioned
plan-record migration, a deliberate once-per-epic operator act. Every other
sanctioned writer leaves a chain-less epic on its legacy pointer path and
reports `plan-epoch-chain: missing`, whose own remedy names this migration — so
until this leg runs, the remedy every reader prints creates nothing.

IT IS ITS OWN MODULE BECAUSE IT IS THE ONE LEG THAT DECIDES NOTHING LOCALLY.
The slug, anchor and pointer legs each hold a judgement about existing state,
which is why `_plan_record_migration` exists to keep those judgements testable.
This leg hands every judgement to `create_genesis_token` — the refusal when a
chain already stands, and the read-back that narrows two operators migrating one
epic at the same moment — and only ROUTES what comes back.

NO EPIC IS JUDGED BY ITS CACHE HERE, deliberately. `create_genesis_token` reads
the cache itself and refuses before creating anything, so a pre-check in this
module would be a second reading of the same question, taken at a different
instant from the one the create actually acts on. The whole value of a refusal
that happens inside the primitive is that nothing can get between the two.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro.commands._plan_epoch_findings import ChainFinding
from livespec_orchestrator_beads_fabro.commands._plan_epoch_genesis import create_genesis_token

if TYPE_CHECKING:
    from collections.abc import Sequence

    from livespec_orchestrator_beads_fabro.types import StoreConfig

__all__: list[str] = ["GenesisLeg", "create_migration_genesis"]


@dataclass(frozen=True, kw_only=True)
class GenesisLeg:
    """What the genesis leg wrote for one tenant's live plan epics."""

    written: tuple[str, ...]


def create_migration_genesis(*, config: StoreConfig, epic_ids: Sequence[str]) -> GenesisLeg:
    """Start the chain of each named epic that has none, naming what it wrote.

    Each written entry names the TOKEN as well as the epic, because the token id
    is the only thing that distinguishes this write from the one a second
    operator's migration made in the same minute — and it is what an operator
    reading a chain-walk finding has to compare the epic's cache against.
    """
    written: list[str] = []
    for epic_id in epic_ids:
        outcome = create_genesis_token(config=config, epic_id=epic_id)
        if isinstance(outcome, ChainFinding):
            continue
        written.append(f"{epic_id} genesis token {outcome}")
    return GenesisLeg(written=tuple(written))
