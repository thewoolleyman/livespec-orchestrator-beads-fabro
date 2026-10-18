"""The CLAIM lane of a reconciliation pass, as its own concern.

`_dispatcher_reconcile_runs` owns the RUN lane: it walks each factory's
inventory and terminates the runs the ledger disowns. This owns the other half
of the same invariant — the claims whose runs are gone — and it sits apart for
the reason every other split in this tree does: the two lanes answer different
questions about one reading, and only one of them may write a work-item's
status. Keeping the claim lane's seam here is what lets a reader see that the
run lane's comments-only ledger surface is untouched.

IT CONSUMES THE READING RATHER THAN TAKING ONE. The lane is handed what the run
lane already measured — the `fabro ps -a --json` listing, keyed by the factory
that answered it — because two listings a moment apart disagree about any run
that ended between them, and the two lanes must not describe one factory two
ways.

EVERY DECLARED FACTORY GETS AN ENTRY, including the ones absent from that
mapping, which is the one thing easy to leave out. A claim naming a factory
this pass could not reach must be held as `factory-unobservable`; with no entry
for that factory the claim would grade `claim-unattributable` instead, which
names a different remedy — "this factory is no longer declared" rather than
"the factory did not answer". So `observed` carries only the factories that
ANSWERED, and `factories` carries the declared set: the difference between the
two is exactly the unsurveyed population.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from livespec_orchestrator_beads_fabro.commands._config import FactoryTarget
from livespec_orchestrator_beads_fabro.commands._dispatcher_dispatching_host import (
    dispatching_host,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_factory_bin import factory_fabro_bin
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import utc_now_iso
from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_runs_inputs import (
    ReconcileInputs,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_stranded_claim_records import (
    HeldClaim,
    RecoveredClaim,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_stranded_claim_survey import (
    FactoryInventory,
    StrandedClaimInputs,
    survey_stranded_claims,
)

__all__: list[str] = [
    "ClaimLaneResult",
    "reconcile_claim_lane",
]


@dataclass(frozen=True, kw_only=True)
class ClaimLaneResult:
    """The claim half's result, or the empty one when the lane is not wired."""

    recovered: tuple[RecoveredClaim, ...] = ()
    held: tuple[HeldClaim, ...] = ()


def reconcile_claim_lane(
    *,
    inputs: ReconcileInputs,
    factories: tuple[FactoryTarget, ...],
    observed: Mapping[str, Mapping[str, str | None]],
    dry_run: bool,
) -> ClaimLaneResult:
    """Survey the ledger's dispatch claims against the inventory just read.

    The lane is skipped when the caller supplied no claim journal, which is the
    narrow observation-only callers' case: a recovery has to read the journal
    back before it may write to it, so there is nothing it could do with a
    write-only seam.
    """
    journal = inputs.claim_journal
    if journal is None:
        return ClaimLaneResult()
    survey = survey_stranded_claims(
        inputs=StrandedClaimInputs(
            inventories=tuple(
                _inventory(inputs=inputs, factory=factory, observed=observed)
                for factory in factories
            ),
            repo=inputs.repo,
            items=tuple(inputs.items),
            journal=journal,
            runner=inputs.runner,
            this_host=(inputs.claim_host if inputs.claim_host is not None else dispatching_host()),
            now_iso=utc_now_iso(),
            dry_run=dry_run,
        )
    )
    return ClaimLaneResult(recovered=survey.recovered, held=survey.held)


def _inventory(
    *,
    inputs: ReconcileInputs,
    factory: FactoryTarget,
    observed: Mapping[str, Mapping[str, str | None]],
) -> FactoryInventory:
    """One declared factory's entry, whether or not this pass surveyed it.

    `factory_fabro_bin` rather than a port: the claim lane needs only WHICH
    client this factory declares, and opening a port for a factory with no
    server url would construct the bare Fabro target the reconciler is
    forbidden to build — a target that surveys whichever server the client
    happens to default to.
    """
    listing = observed.get(factory.name)
    return FactoryInventory(
        name=factory.name,
        server_url=factory.server,
        fabro_bin=factory_fabro_bin(factory=factory, fallback=inputs.fabro_bin),
        surveyed=listing is not None,
        status_kinds={} if listing is None else dict(listing),
    )
