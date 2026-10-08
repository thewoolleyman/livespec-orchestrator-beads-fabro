"""The run identifiers one merging dispatch answers to.

A Proof of Done record names its run on its first line, and the Dispatcher knows
the dispatch that merged under TWO identifiers rather than one. The Fabro run id
exists only once `fabro run` has launched; the `dispatch_id` is minted BEFORE the
launch, and it is the value a prepare step writes into the sandbox clone's own
`livespec.factoryRunId` git config (`_dispatcher_factory_provenance`). The
capture stage resolves its run id from `$FABRO_RUN_ID` and falls back to that git
config — and `$FABRO_RUN_ID` is unset inside the stage, so the fallback is what
every published record is stamped with.

WHY THIS MODULE EXISTS. The acceptance pass used to ask `latest_proof_record` for
the Fabro run id alone, so a record stamped with the dispatch id was not this
merge's evidence and every assertion came back UNEVIDENCED. Measured 2026-10-04
on PR #2538 (work-item `bd-ib-mxqrr4`): both records name
`f195238b76b942698485a780611fe1ef`, the dispatch id, while the pass asked for
`01M3WH8Z10278S5V4SV9WRYW20`; the journal recorded `acceptance_verdict
NEEDS_ATTENTION` and `proof-pointer-skipped` with reason "no verified Proof of
Done record for the merging run". The record was right and the question was too
narrow — which is why the repair widens the QUESTION rather than the stage's
fallback. The proof-evidence-leg clause of `SPECIFICATION/contracts.md` (v115)
ratifies the widening: "the pass MUST accept either identifier the Dispatcher can
attribute to the merging dispatch".

WHY THE JOURNAL IS THE SOURCE AND NOT THE OUTCOME ALONE. `reconcile-merged`
re-runs the pass later and from another process, against a `DispatchOutcome` it
built itself out of a resolved merged pull request — so that outcome carries no
Fabro run id at all, and no outcome has ever carried the dispatch id. The
dispatch journal carries both: the `dispatch-id` stage record names the dispatch
id before the run starts, and every run record names the Fabro run id.

WHY EVERY JOURNALED DISPATCH IS ACCEPTED AND NOT ONLY THE NEWEST. This module
read both identifiers NEWEST-WINS until 2026-10-05, in the belief that the newest
journal row names the dispatch that merged. It does not. The dispatch that merged
is the one that PUBLISHED THE MERGED HEAD, and a run that dies AFTER publishing is
recovered by a LATER dispatch, which the journal then records after it — so the
publishing dispatch's identifiers are the ones the newest-wins reading throws
away. Measured 2026-10-05 on `bd-ib-qm4luz`: run 01M44F9E56XCEWZNMVJX4M14Z6
published pull request 2581, captured and verified its Proof of Done there and was
approved, then died at the `pr` stage; pull request 2581 merged with its required
checks green, and `reconcile-merged` parked the item NEEDS_ATTENTION reporting
"records read for run e6a5f80fef944709a8b8062c7660c67f or
1b09f96002d24d25ab372219cb9751ae" — the identifiers of the LATEST journaled
dispatch, neither of which the merged head's own verified record carries.

THE WIDENING IS STILL FAIL-CLOSED, and the journal is where it closes. A record
whose run identifier belongs to NO dispatch this item was journaled under is
another item's record, or no dispatch's at all, and is not attributed; the
accepted set is never "whatever verified record is newest on the pull request".
Nothing weaker than the journal could draw that line, which is why the set is
resolved from the file rather than from the record under judgment.

THE READERS ARE REUSED, NOT RE-DERIVED. `dispatch_ids_for` and
`journaled_run_ids` are the PLURAL readers owned by the two modules that already
own these record shapes — the TDD calibration probe and the run reconciler — and
each singular reader is derived from its own plural, so the newest identifier is
always a member of the accepted set. A fourth hand-rolled scan of the same file
could only disagree with them, and the disagreement would be invisible because
every reading would still be a plausible id.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_reflection_journal import (
    read_journal_records,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_resume_journal import (
    resume_linked_run_ids,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_tdd_probe import dispatch_ids_for
from livespec_orchestrator_beads_fabro.commands._run_attribution import journaled_run_ids

__all__: list[str] = [
    "MergingDispatch",
    "merging_dispatch",
]


@dataclass(frozen=True, kw_only=True)
class MergingDispatch:
    """The identifiers a record may carry and still belong to the merging dispatch."""

    fabro_run_id: str | None
    dispatch_id: str | None
    # Every OTHER identifier the journal names for this item: the earlier
    # dispatches, any one of which may be the dispatch that published the merged
    # head. Defaulted to empty so the two fields above remain the whole of a
    # hand-built value, which is what every caller holding only an outcome
    # constructs; an empty tuple reduces the accepted set to the newest dispatch,
    # which is the pre-widening behaviour and still the right answer for an item
    # dispatched once.
    journaled_ids: tuple[str, ...] = ()

    @property
    def run_ids(self) -> tuple[str, ...]:
        """Every accepted identifier, the newest dispatch first, duplicates dropped.

        An EMPTY tuple is the UNATTRIBUTABLE answer, and it is deliberately not
        the same as "accept any record": `latest_proof_record` matches nothing
        against an empty set, because a dispatch nobody can identify must not
        inherit whichever verified record happens to be newest.

        The newest dispatch's own identifiers lead, because the reason line the
        pass renders from this tuple is read most often on a refusal and the
        dispatch now terminating is what an operator is looking for first.
        """
        named = (self.fabro_run_id, self.dispatch_id, *self.journaled_ids)
        return tuple(dict.fromkeys(one for one in named if one is not None))


def merging_dispatch(
    *, work_item_id: str, fabro_run_id: str | None, journal_path: Path
) -> MergingDispatch:
    """Resolve every identifier a record may carry and still belong to this merge.

    `fabro_run_id` is the outcome's own, and it leads when the outcome carries
    one: on the dispatch path the run the outcome describes IS the run now
    terminating, while the journal's newest is only what the reconcile path has to
    fall back on. It no longer NARROWS the accepted set, because the run that
    published a merged head need not be the run now terminating. An absent journal
    reads as a journal naming nothing, so a caller holding a path that was never
    written degrades to the outcome's own identifier rather than raising.
    """
    records = read_journal_records(journal_path=journal_path)
    runs = journaled_run_ids(records=records, work_item_id=work_item_id)
    dispatches = dispatch_ids_for(records=records, work_item_id=work_item_id)
    # The RESUME chain is read even though the two readers above already return
    # every identifier THIS checkout journaled a dispatch under, because a resume
    # record names identifiers a dispatch record need not: the earlier run may
    # have been dispatched from another checkout, whose journal is invisible here
    # (the publish-branch reclaim's "only a re-dispatch asks" bullet records the
    # same blind spot). Dropping them would read the earlier run's verified record
    # as another item's and report every assertion unevidenced -- the exact
    # failure this module was built to repair, arriving through the resume door
    # instead of the newest-wins one.
    resumed = resume_linked_run_ids(records=records, work_item_id=work_item_id)
    return MergingDispatch(
        fabro_run_id=fabro_run_id if fabro_run_id is not None else (runs[-1] if runs else None),
        dispatch_id=dispatches[-1] if dispatches else None,
        journaled_ids=(*runs, *dispatches, *resumed),
    )
