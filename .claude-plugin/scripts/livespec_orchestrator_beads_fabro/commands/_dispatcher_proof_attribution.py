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
id before the run starts, and every run record names the Fabro run id. Both are
read NEWEST-WINS for the item, which is what keeps the widening FAIL-CLOSED: a
record from an EARLIER dispatch of the same item is still not this merge's
evidence, because an earlier dispatch's identifiers are not in the accepted set.

THE TWO READERS ARE REUSED, NOT RE-DERIVED. `dispatch_id_for` already resolves an
item's dispatch id off these records for the TDD calibration span, and
`newest_journaled_run_id` already resolves its newest Fabro run id for the run
reconciler — each with the last-wins rule stated above. A third hand-rolled scan
of the same file could only disagree with them, and the disagreement would be
invisible because every reading would still be a plausible id.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_reflection_journal import (
    read_journal_records,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_tdd_probe import dispatch_id_for
from livespec_orchestrator_beads_fabro.commands._run_attribution import newest_journaled_run_id

__all__: list[str] = [
    "MergingDispatch",
    "merging_dispatch",
]


@dataclass(frozen=True, kw_only=True)
class MergingDispatch:
    """The identifiers a record may carry and still belong to the merging dispatch."""

    fabro_run_id: str | None
    dispatch_id: str | None

    @property
    def run_ids(self) -> tuple[str, ...]:
        """Every accepted identifier, Fabro run id first, with duplicates dropped.

        An EMPTY tuple is the UNATTRIBUTABLE answer, and it is deliberately not
        the same as "accept any record": `latest_proof_record` matches nothing
        against an empty set, because a dispatch nobody can identify must not
        inherit whichever verified record happens to be newest.
        """
        named = (self.fabro_run_id, self.dispatch_id)
        return tuple(dict.fromkeys(one for one in named if one is not None))


def merging_dispatch(
    *, work_item_id: str, fabro_run_id: str | None, journal_path: Path
) -> MergingDispatch:
    """Resolve both identifiers of the dispatch whose pull request merged.

    `fabro_run_id` is the outcome's own, and it WINS when the outcome carries one:
    on the dispatch path the run the outcome describes IS the run that merged,
    while the journal's newest is only what the reconcile path has to fall back
    on. An absent journal reads as a journal naming nothing, so a caller holding a
    path that was never written degrades to the outcome's own identifier rather
    than raising.
    """
    records = read_journal_records(journal_path=journal_path)
    return MergingDispatch(
        fabro_run_id=(
            fabro_run_id
            if fabro_run_id is not None
            else newest_journaled_run_id(records=records, work_item_id=work_item_id)
        ),
        dispatch_id=dispatch_id_for(records=records, work_item_id=work_item_id),
    )
