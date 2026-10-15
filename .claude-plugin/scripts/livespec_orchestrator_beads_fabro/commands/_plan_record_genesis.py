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

AN ALREADY-NAMED CHAIN IS A SKIP AND NOT A REFUSAL. Running this migration
twice is an ordinary operator act, and the second run's whole claim is that it
changed nothing; reporting it among the refusals would make idempotence read as
a tenant full of ambiguous state a human still has to resolve by hand. Nor may
it be silent: an epic the leg passed over for a good reason and one it never
considered owe opposite conclusions, and only the entry distinguishes them.

EVERY OTHER FINDING IS A REFUSAL, and the routing keys on the already-named
CODE rather than excluding a list of known-bad ones. The already-named outcome
is the one whose remedy is to do NOTHING; an unconfirmed genesis asks the
operator to re-read the epic, because another writer may have migrated it in
the same minute, and `refused` is where an operator looks for what one run
could not settle. Keying on the no-op code is also what makes a finding added
LATER refuse by default rather than vanish into the no-op bucket.

A REFUSAL CARRIES THE REMEDY AS WELL AS THE DETAIL, in the same
`<code>: <detail> — <remedy>` form every other chain-finding refusal in this
package takes. `_plan_epoch_findings` holds the rule: every finding withholds
something, so a diagnosis nobody can act on satisfies neither half of the
clause it serves.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro.commands._plan_epoch_findings import (
    GENESIS_ALREADY_NAMED,
    ChainFinding,
)
from livespec_orchestrator_beads_fabro.commands._plan_epoch_genesis import create_genesis_token

if TYPE_CHECKING:
    from collections.abc import Sequence

    from livespec_orchestrator_beads_fabro.types import StoreConfig

__all__: list[str] = ["GenesisLeg", "create_migration_genesis"]


@dataclass(frozen=True, kw_only=True)
class GenesisLeg:
    """What the genesis leg wrote, what it left alone, and what it could not settle."""

    written: tuple[str, ...]
    skipped: tuple[str, ...]
    refused: tuple[str, ...]


def create_migration_genesis(*, config: StoreConfig, epic_ids: Sequence[str]) -> GenesisLeg:
    """Start the chain of each named epic that has none, naming every outcome.

    Each written entry names the TOKEN as well as the epic, because the token id
    is the only thing that distinguishes this write from the one a second
    operator's migration made in the same minute — and it is what an operator
    reading a chain-walk finding has to compare the epic's cache against. The
    skipped entry is the finding's own detail for the same reason: it already
    names the standing token, and re-wording it here would be a second account
    of one measurement.
    """
    written: list[str] = []
    skipped: list[str] = []
    refused: list[str] = []
    for epic_id in epic_ids:
        outcome = create_genesis_token(config=config, epic_id=epic_id)
        if isinstance(outcome, ChainFinding):
            bucket = skipped if outcome.code == GENESIS_ALREADY_NAMED else refused
            bucket.append(_entry(finding=outcome))
            continue
        written.append(f"{epic_id} genesis token {outcome}")
    return GenesisLeg(written=tuple(written), skipped=tuple(skipped), refused=tuple(refused))


def _entry(*, finding: ChainFinding) -> str:
    """Render one finding for the report, carrying its remedy where one applies.

    The already-named remedy is literally "nothing to do", which is what the
    `skipped` bucket already says, so repeating it there would be noise in the
    one place an operator scans fastest. Every other finding is refused, and a
    refusal without its remedy leaves the operator nowhere to go.
    """
    if finding.code == GENESIS_ALREADY_NAMED:
        return finding.detail
    return f"{finding.code}: {finding.detail} — {finding.remedy}"
