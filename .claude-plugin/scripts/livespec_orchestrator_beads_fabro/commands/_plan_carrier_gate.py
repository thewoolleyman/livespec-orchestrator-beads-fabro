"""Whether any carrier of this plan's assertions is still open.

The plan Definition-of-Done clause records the carrier relation ONLY in the
epic's carrier-map scope event, and a closed carrier child does not by itself
discharge the plan assertion it carries — the plan's own Proof of Done record is
what discharges one. The converse is what this module answers: while a WORK-ITEM
carrier of one of those assertions is still OPEN, the plan's Proof of Done cannot
be true, so no plan-level step may be derived against it.

WHY THE STATUS COMES FROM THE SHARED RESULT READER AND NOT FROM A LOCAL LEDGER
CALL. Every carrier of a real plan is legitimately cross-tenant, and the
shared-authoritative-result-reader clause owns the rule that a cross-tenant read
uses the named repository's own configuration and credential seam and executes
from that repository's clone. A local `bd` call would read this project's tenant
and answer, for an id that tenant has never minted, that the carrier is not
closed — a confident negative taken on the wrong population, which would wait on
every carrier for ever.

WHY A READING THAT IS NOT `satisfied` COUNTS AS OPEN. The reader returns
`unsatisfied` for a carrier the ledger reports at another status and
`unobservable` for a read it could not take, and only `satisfied` establishes
that the carrier is closed. Treating an unobservable reading as closed would make
a broken or unreachable tenant the cheapest route to a plan proof record that
asserts work nobody could look at; treating it as open stalls the plan
diagnosably instead, and the `await` obligation the caller records reports the
same unobservable reading on the next resume.

WHY THE SCAN STOPS AT THE FIRST OPEN CARRIER. A derived pointer names ONE
required result, so a second open carrier changes nothing about the step this
plan owes next — and each further carrier costs a cross-tenant read. The carriers
are scanned in the order the maintainer wrote them, so the carrier waited on is
deterministic rather than whichever read answered first.

WHY THERE ARE TWO READINGS AND NOT ONE VERDICT. `first_open_carrier` PASSES OVER
a carrier whose repository nothing resolves — its status was never measured, and
an obligation naming an unresolvable repository is refused at the write and
unobservable at every read — so those carriers have to be reported separately or
they are silently treated as closed. `unplaceable_carrier_ids` is that report,
and it asks a CONFIGURATION question rather than a status one: which carriers of
this plan live somewhere this checkout has not been told about. The two readings
pull in opposite directions, which is why neither may be collapsed onto the
other: one must not block the open carrier behind an unplaceable one, and the
other must not let an unplaceable one pass as done.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro._beads_client import make_beads_client
from livespec_orchestrator_beads_fabro.commands._dispatcher_shell_runner import ShellCommandRunner
from livespec_orchestrator_beads_fabro.commands._plan_carrier_map import (
    last_carrier_map_carriers,
)
from livespec_orchestrator_beads_fabro.commands._plan_carrier_tenancy import (
    CarrierTenancy,
    carrier_tenancy,
    repository_for_carrier,
)
from livespec_orchestrator_beads_fabro.commands._plan_result_observation import (
    OBSERVATION_SATISFIED,
)
from livespec_orchestrator_beads_fabro.commands._plan_result_reader import read_result
from livespec_orchestrator_beads_fabro.commands._plan_result_reference import REPO_FIELD
from livespec_orchestrator_beads_fabro.commands._plan_result_targets import ITEM_STATUS_KIND

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.types import StoreConfig

__all__: list[str] = [
    "CLOSED_STATUS",
    "OpenCarrier",
    "carrier_status_target",
    "first_open_carrier",
    "plan_carrier_ids",
    "unplaceable_carrier_ids",
]

# The lifecycle status a carrier reaches when it is done. The livespec statuses
# are normalized onto beads' built-in closure, so this is the one word every
# tenant of this family records a finished item at.
CLOSED_STATUS = "closed"


@dataclass(frozen=True, kw_only=True)
class OpenCarrier:
    """One carrier that is not closed, with the repository it was read from.

    `repo` is the repository IDENTITY rather than its clone, because what a
    caller does with this is author an obligation, and an obligation names an
    identity the next reader resolves for itself.
    """

    item_id: str
    repo: str


def plan_carrier_ids(*, config: StoreConfig, epic_id: str) -> tuple[str, ...]:
    """Every carrier the epic's latest carrier-map scope event names, in order."""
    return last_carrier_map_carriers(
        comments=make_beads_client(config=config).list_comments(issue_id=epic_id)
    )


def carrier_status_target(*, carrier: OpenCarrier) -> dict[str, object]:
    """The typed TARGET an obligation on one carrier's closure names.

    Rendered HERE rather than at each caller so the target a derived step waits
    on is the same target this gate read the carrier's status through. Two
    renderings of one obligation are how an `await` comes to be recorded against
    a target whose openness nobody actually measured.

    The repository identity is deliberately NOT included, exactly as every other
    derived step's target omits it: a reference is a repository plus one target,
    and the repository is the caller's to name — this gate reads from the one it
    resolved, and the advance stamps the one its pointer must carry.
    """
    return {ITEM_STATUS_KIND: {"item_id": carrier.item_id, "status": CLOSED_STATUS}}


def first_open_carrier(*, config: StoreConfig, epic_id: str) -> OpenCarrier | None:
    """The first carrier of this plan that is not closed, or `None` when none is.

    A carrier whose repository the result reader cannot resolve is PASSED OVER
    here rather than reported as open: its status was never measured, so it is
    not a carrier this gate can say anything about, and an obligation naming an
    unresolvable repository is one no later resume could observe either.
    """
    carriers = plan_carrier_ids(config=config, epic_id=epic_id)
    if not carriers:
        return None
    tenancy = carrier_tenancy(config=config)
    for carrier_id in carriers:
        repository = repository_for_carrier(tenancy=tenancy, carrier_id=carrier_id)
        if repository is None:
            continue
        carrier = OpenCarrier(item_id=carrier_id, repo=repository.name)
        if not _carrier_closed(tenancy=tenancy, carrier=carrier):
            return carrier
    return None


def unplaceable_carrier_ids(*, config: StoreConfig, epic_id: str) -> tuple[str, ...]:
    """Every carrier of this plan whose repository no configured target resolves.

    THE COMPANION OF `first_open_carrier`'S PASS-OVER, and it exists because
    that pass-over is only half an answer. A carrier nothing can place has a
    status nobody measured, so the gate cannot wait on it — an obligation naming
    a repository nothing resolves is refused at the write and would be
    `unobservable` at every read — and it equally cannot be treated as closed,
    because the carrier map names it as carrying one of the plan's own
    assertions. So the carriers that were passed over have to be REPORTED, and
    this is the reading that reports them.

    NO STATUS IS READ, which is the whole point rather than an economy: there is
    no tenant to read one from. The question this answers is a configuration
    question — which carriers of this plan live somewhere this checkout has not
    been told about — and its answer is what a human decides on.
    """
    carriers = plan_carrier_ids(config=config, epic_id=epic_id)
    if not carriers:
        return ()
    tenancy = carrier_tenancy(config=config)
    return tuple(
        carrier_id
        for carrier_id in carriers
        if repository_for_carrier(tenancy=tenancy, carrier_id=carrier_id) is None
    )


def _carrier_closed(*, tenancy: CarrierTenancy, carrier: OpenCarrier) -> bool:
    """Whether the ledger ESTABLISHES that one carrier is closed.

    Only a `satisfied` reading does. The module docstring carries why an
    unobservable reading is not closed.
    """
    observation = read_result(
        project_root=tenancy.project_root,
        reference={REPO_FIELD: carrier.repo, **carrier_status_target(carrier=carrier)},
        runner=ShellCommandRunner(),
    )
    return observation.status == OBSERVATION_SATISFIED
