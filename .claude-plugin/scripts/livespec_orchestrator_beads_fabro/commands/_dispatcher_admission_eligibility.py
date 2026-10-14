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
the same reason. The SIX per-row refusals then run in this order:

1. An unexpired LEGACY provider-exhaustion record COVERING a candidate this
   dispatch's resolved ACP nodes render. A vendor ceiling this dispatch would
   run into is a fact about the factory, not the item -- but only about the
   part of the factory the item's nodes reach, which is why the record is
   scoped to those candidates rather than to a vendor list: a record covering
   none of them refuses nothing.
2. An admission-required node the SESSION-HEADROOM filter emptied. Also a fact
   about the factory -- this pass's one reading of the projected credential --
   and it sits ABOVE the generic chain refusal because the two carry different
   fields: a reading mints no hold, so it has no hold identity or expiry to
   name, and the generic refusal would report the wait with those fields simply
   absent rather than with the assessment that governed it.
3. An exhausted success-critical ACP candidate chain. Also a fact about the
   factory, and it reads a verdict already computed for the whole pass.
4. The adopted assertion-count ceiling, which is the first condition that
   reads THIS row's ledger metadata -- a `bd show` per candidate once a
   ceiling is adopted -- and the only MUTATING one: an above-ceiling row
   carrying no valid `size_justification` is routed to `backlog` for
   decomposition with a ledger comment. It sits BELOW both factory-wide
   conditions for exactly that reason. Over a candidate wave arriving during
   a provider outage, grading it first spends N ledger round-trips and
   performs N lifecycle mutations on rows the next condition was about to
   refuse anyway -- and the mutation is the expensive half, because a refused
   dispatch is retried while a row moved to `backlog` has to be regroomed.
5. The item's own ledger labels.
6. The host-only routing refusal, which needs those labels.

The session-headroom READING is journaled before any of the six, because the
clause journals it "for each affected work-item" whether or not it skipped
anything -- a floor of `0` is observable through that line and nowhere else.

Putting either factory-wide condition after the label read would report a
provider outage as "this item's labels could not be read" whenever both were
true -- a refusal naming the wrong subject, which is exactly the kind of
plausible wrong answer a reader has no way to catch.
"""

from __future__ import annotations

from pathlib import Path

from returns.pipeline import is_successful
from returns.unsafe import unsafe_perform_io

from livespec_orchestrator_beads_fabro.commands._acp_dispatch_coverage import RenderedCandidate
from livespec_orchestrator_beads_fabro.commands._acp_preflight_verdict import AcpPreflightVerdict
from livespec_orchestrator_beads_fabro.commands._dispatcher_acp_preflight import (
    resolve_dispatch_candidates,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_acp_preflight_refusal import (
    acp_preflight_refusal,
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
from livespec_orchestrator_beads_fabro.commands._dispatcher_session_headroom_records import (
    append_session_headroom_records,
    session_headroom_refusal,
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
    admittable: list[WorkItem] = []
    refused: list[DispatchOutcome] = []
    for item in candidates:
        refusal = _refusal_for(
            repo=repo,
            preflight=preflight,
            item=item,
            journal=journal,
            adopted_ceiling=adopted_ceiling,
            rendered=rendered,
        )
        if refusal is None:
            admittable.append(item)
        else:
            refused.append(refusal)
    return admittable, refused


def _refusal_for(
    *,
    repo: Path,
    preflight: AcpPreflightVerdict,
    item: WorkItem,
    journal: JournalFile,
    adopted_ceiling: int | None,
    rendered: tuple[RenderedCandidate, ...] | None,
) -> DispatchOutcome | None:
    """The first condition this row fails, or `None` when it passes all six."""
    now_iso = utc_now_iso()
    # BEFORE every refusal, because the clause journals the reading "for each
    # affected work-item" whether or not anything was skipped, and because a
    # floor of 0 is observable only through this line. It writes nothing for a
    # verdict carrying no reading, so the no-op path is untouched.
    append_session_headroom_records(work_item_id=item.id, verdict=preflight, journal=journal)
    exhaustion_refusal = provider_exhaustion_refusal(
        work_item_id=item.id,
        journal=journal,
        journal_path=getattr(journal, "path", None),
        now_iso=now_iso,
        candidates=rendered,
    )
    if exhaustion_refusal is not None:
        return exhaustion_refusal
    # ABOVE the chain-exhaustion refusal, because a node emptied by a headroom
    # reading owes DIFFERENT fields than one emptied by observed holds -- a
    # reading that minted no hold has no hold identity or expiry to name, and
    # the generic refusal would report it with those fields absent rather than
    # with the assessment that governed it. It returns `None` for a chain the
    # reading did not empty, so a genuine hold exhaustion still falls through.
    headroom = session_headroom_refusal(
        repo=repo,
        work_item_id=item.id,
        verdict=preflight,
        journal=journal,
        now_iso=now_iso,
    )
    if headroom is not None:
        return headroom
    chain_refusal = acp_preflight_refusal(work_item_id=item.id, verdict=preflight, journal=journal)
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
