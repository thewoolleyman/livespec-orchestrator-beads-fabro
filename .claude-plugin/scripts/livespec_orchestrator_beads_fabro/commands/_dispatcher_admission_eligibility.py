"""The MECHANICAL eligibility filter both admission legs pass through.

Split out of `_dispatcher_admission` by cohesion: that module SEQUENCES a
pass -- rework leg, then capacity, then the ready plan, then the writes --
while this one answers one question per candidate, "may this row be dispatched
at all?", and answers it identically for a marked rework row and a new `ready`
item. Keeping the two apart is what makes "both legs pass through the SAME
filter" a fact about the code rather than a convention two call sites keep.

THE ORDER OF THE FOUR REFUSALS IS DELIBERATE, cheapest and least
item-specific first:

1. An unexpired LEGACY provider-exhaustion record. A vendor ceiling this
   dispatch would run into is a fact about the factory, not the item.
2. An exhausted success-critical ACP candidate chain. Also a fact about the
   factory, and it reads a verdict already computed for the whole pass.
3. The item's own ledger labels, which is the first read that can fail for a
   reason belonging to THIS row.
4. The host-only routing refusal, which needs those labels.

Putting either factory-wide condition after the label read would report a
provider outage as "this item's labels could not be read" whenever both were
true -- a refusal naming the wrong subject, which is exactly the kind of
plausible wrong answer a reader has no way to catch.
"""

from __future__ import annotations

from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._acp_preflight_verdict import AcpPreflightVerdict
from livespec_orchestrator_beads_fabro.commands._dispatcher_acp_preflight import (
    acp_preflight_refusal,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_completion import host_only_refusal
from livespec_orchestrator_beads_fabro.commands._dispatcher_credentials import read_dispatch_labels
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile, utc_now_iso
from livespec_orchestrator_beads_fabro.commands._dispatcher_loop_outcomes import (
    failed_dispatch_outcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_provider_exhaustion import (
    provider_exhaustion_refusal,
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
    """
    admittable: list[WorkItem] = []
    refused: list[DispatchOutcome] = []
    for item in candidates:
        refusal = _refusal_for(repo=repo, preflight=preflight, item=item, journal=journal)
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
) -> DispatchOutcome | None:
    """The first condition this row fails, or `None` when it passes all four."""
    exhaustion_refusal = provider_exhaustion_refusal(
        work_item_id=item.id,
        journal=journal,
        journal_path=getattr(journal, "path", None),
        now_iso=utc_now_iso(),
    )
    if exhaustion_refusal is not None:
        return exhaustion_refusal
    chain_refusal = acp_preflight_refusal(work_item_id=item.id, verdict=preflight, journal=journal)
    if chain_refusal is not None:
        return chain_refusal
    raw_labels = read_dispatch_labels(repo=repo, item=item)
    if isinstance(raw_labels, str):
        return failed_dispatch_outcome(
            journal=journal,
            work_item_id=item.id,
            stage="ledger-labels",
            detail=raw_labels,
        )
    return host_only_refusal(repo=repo, item=item, journal=journal, raw_labels=raw_labels)
