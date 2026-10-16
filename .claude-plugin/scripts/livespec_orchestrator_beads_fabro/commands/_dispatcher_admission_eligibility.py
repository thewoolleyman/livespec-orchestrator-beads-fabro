"""The MECHANICAL eligibility filter both admission legs pass through.

Split out of `_dispatcher_admission` by cohesion: that module SEQUENCES a
pass -- rework leg, then capacity, then the ready plan, then the writes --
while this one answers one question per candidate, "may this row be dispatched
at all?", and answers it identically for a marked rework row and a new `ready`
item. Keeping the two apart is what makes "both legs pass through the SAME
filter" a fact about the code rather than a convention two call sites keep.

THE ORDER OF THE REFUSALS IS DELIBERATE, cheapest and least item-specific
first. The least item-specific of all is COMMITTED CONFIGURATION, and it is
resolved ONCE PER PASS in `filter_eligible_candidates` rather than inside the
per-row ladder: an unreadable `dispatcher.adopted_assertion_count_ceiling` is
a fact about the repository that refuses every candidate identically, so
resolving it per row would re-read one file once per candidate to reach the
same answer. The dispatch's RENDERED ACP CANDIDATES are resolved there for
the same reason. The FIVE per-row refusals then run in this order:

1. An unexpired LEGACY provider-exhaustion record COVERING a candidate this
   dispatch's resolved ACP nodes render. A vendor ceiling this dispatch would
   run into is a fact about the factory, not the item -- but only about the
   part of the factory the item's nodes reach, which is why the record is
   scoped to those candidates rather than to a vendor list: a record covering
   none of them refuses nothing.
2. An exhausted success-critical ACP candidate chain. Also a fact about the
   factory, and it reads a verdict already computed for the whole pass.
3. The adopted assertion-count ceiling, which is the first condition that
   reads THIS row's ledger metadata -- a `bd show` per candidate once a
   ceiling is adopted -- and the only MUTATING one: an above-ceiling row
   carrying no valid `size_justification` is routed to `backlog` for
   decomposition with a ledger comment. It sits BELOW both factory-wide
   conditions for exactly that reason. Over a candidate wave arriving during
   a provider outage, grading it first spends N ledger round-trips and
   performs N lifecycle mutations on rows the next condition was about to
   refuse anyway -- and the mutation is the expensive half, because a refused
   dispatch is retried while a row moved to `backlog` has to be regroomed.
4. The item's own ledger labels.
5. The host-only routing refusal, which needs those labels.

Putting either factory-wide condition after the label read would report a
provider outage as "this item's labels could not be read" whenever both were
true -- a refusal naming the wrong subject, which is exactly the kind of
plausible wrong answer a reader has no way to catch.
"""

from __future__ import annotations

from pathlib import Path

from returns.pipeline import is_successful
from returns.unsafe import unsafe_perform_io

from livespec_orchestrator_beads_fabro.commands._acp_availability_wait import AvailabilityWait
from livespec_orchestrator_beads_fabro.commands._acp_dispatch_coverage import RenderedCandidate
from livespec_orchestrator_beads_fabro.commands._acp_preflight_verdict import AcpPreflightVerdict
from livespec_orchestrator_beads_fabro.commands._dispatcher_acp_preflight import (
    acp_preflight_refusal,
    resolve_availability_wait,
    resolve_dispatch_candidates,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_completion import host_only_refusal
from livespec_orchestrator_beads_fabro.commands._dispatcher_credentials import read_dispatch_labels
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_factory_size_gate import (
    resolve_adopted_assertion_count_ceiling,
    route_factory_size_dispatch_entry,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile, utc_now_iso
from livespec_orchestrator_beads_fabro.commands._dispatcher_loop_outcomes import (
    failed_dispatch_outcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import store_config
from livespec_orchestrator_beads_fabro.commands._dispatcher_provider_exhaustion import (
    provider_exhaustion_refusal,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_session_headroom_gate import (
    journal_session_headroom,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "filter_eligible_candidates",
]


def filter_eligible_candidates(
    *,
    repo: Path,
    preflight: AcpPreflightVerdict,
    candidates: list[WorkItem],
    journal: JournalFile,
) -> tuple[list[WorkItem], list[DispatchOutcome]]:
    """Split a candidate list into the dispatchable rows and the refused ones.

    Every refusal is journaled by the helper that produced it, so the returned
    outcomes are a projection of what was already recorded rather than a second
    account of it.

    The adopted assertion-count ceiling is resolved HERE, before the per-row
    ladder, for the reason the module docstring gives: it is the one condition
    whose answer belongs to the repository rather than to any candidate. An
    unreadable one refuses the WHOLE wave -- one refusal per row, so the
    returned outcomes still describe the candidates the caller handed in,
    which is what the drain's accounting reads.
    """
    resolved_ceiling = resolve_adopted_assertion_count_ceiling(cwd=repo)
    if not is_successful(resolved_ceiling):
        detail = unsafe_perform_io(resolved_ceiling.failure()).detail
        return [], [
            failed_dispatch_outcome(
                journal=journal,
                work_item_id=item.id,
                stage="configuration",
                detail=detail,
            )
            for item in candidates
        ]
    adopted_ceiling = unsafe_perform_io(resolved_ceiling.unwrap())
    # The candidates this repository's ACP nodes render are committed
    # configuration too, and the legacy provider gate is scoped to them. They
    # are resolved ONCE here for the same reason the ceiling above is: the
    # answer belongs to the repository rather than to any candidate, so a
    # per-row resolution would re-read one manifest and one overlay table per
    # candidate to reach the identical set.
    rendered = resolve_dispatch_candidates(repo=repo)
    # ONE evaluation instant for the whole wave, and ONE scheduled
    # reevaluation derived from it. Both belong to the pass rather than to any
    # row: every candidate an emptied chain refuses waits for the SAME instant,
    # so deriving it per row would let two rows refused by one outage report
    # two different instants a later pass would then disagree about.
    now_iso = utc_now_iso()
    wait = resolve_availability_wait(repo=repo, verdict=preflight, now_iso=now_iso)
    # The ACCOUNTS this pass projects, which is the second axis the legacy
    # provider gate is scoped on. They belong to the pass for the same reason
    # the rendered candidates do: one admission evaluation takes at most one
    # reading per distinct projected credential, so every row of the wave is
    # graded against the very accounts that reading named.
    projected_identities = frozenset(
        reading.credential_identity for reading in preflight.headroom_assessments
    )
    admittable: list[WorkItem] = []
    refused: list[DispatchOutcome] = []
    for item in candidates:
        # The headroom reading is an OBSERVATION about this item's evaluation,
        # not a condition of it, so it is journaled before the refusal ladder
        # runs and for every candidate alike. The clause requires the reading
        # for each affected work-item whether or not it refused anything, and
        # recording it inside the ladder would lose it on exactly the admitted
        # case the journal exists to make auditable.
        journal_session_headroom(work_item_id=item.id, verdict=preflight, journal=journal)
        refusal = _refusal_for(
            repo=repo,
            preflight=preflight,
            item=item,
            journal=journal,
            adopted_ceiling=adopted_ceiling,
            rendered=rendered,
            projected_identities=projected_identities,
            now_iso=now_iso,
            wait=wait,
        )
        if refusal is None:
            admittable.append(item)
        else:
            refused.append(refusal)
    return admittable, refused


def _refusal_for(  # noqa: PLR0913 -- one kw-only condition ladder; every input is a pass-resolved fact, not a variant.
    *,
    repo: Path,
    preflight: AcpPreflightVerdict,
    item: WorkItem,
    journal: JournalFile,
    adopted_ceiling: int | None,
    rendered: tuple[RenderedCandidate, ...] | None,
    projected_identities: frozenset[str],
    now_iso: str,
    wait: AvailabilityWait | None,
) -> DispatchOutcome | None:
    """The first condition this row fails, or `None` when it passes all five."""
    exhaustion_refusal = provider_exhaustion_refusal(
        work_item_id=item.id,
        journal=journal,
        journal_path=getattr(journal, "path", None),
        now_iso=now_iso,
        candidates=rendered,
        projected_identities=projected_identities,
    )
    if exhaustion_refusal is not None:
        return exhaustion_refusal
    chain_refusal = acp_preflight_refusal(
        work_item_id=item.id, verdict=preflight, journal=journal, wait=wait
    )
    if chain_refusal is not None:
        return chain_refusal
    size_refusals = route_factory_size_dispatch_entry(
        adopted_ceiling=adopted_ceiling,
        path_factory=lambda: store_config(repo=repo),
        items=(item,),
        journal=journal,
    )
    if size_refusals:
        return size_refusals[0]
    raw_labels = read_dispatch_labels(repo=repo, item=item)
    if isinstance(raw_labels, str):
        return failed_dispatch_outcome(
            journal=journal,
            work_item_id=item.id,
            stage="ledger-labels",
            detail=raw_labels,
        )
    return host_only_refusal(repo=repo, item=item, journal=journal, raw_labels=raw_labels)
