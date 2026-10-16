"""The whole tree-preservation decision for ONE terminated run, as data.

Four modules answer one question each and this joins them: the trigger decides
WHETHER a tree is unpreserved, the base reader says WHAT the published commit
is parented on, the publication performs the forge work, and the record module
renders what is written down. None of them knows what the others concluded, and
the ORDER in which their answers compose is this module's whole subject --
which is why it is here rather than inlined at the call site, where it would be
reachable only through a factory, a forge and a tenant.

IT WRITES NOTHING. The ledger comment, the journal append, and the reads that
supply `event_records` and `journal_records` all belong to
`_dispatcher_preserved_tree_escalation`; what comes back from here is the body
to write (or the reason it must not be written) beside the row to journal. That
is what makes every arm of the ratified clause exercisable without a double for
the forge, the factory or the tenant -- including the two arms no fixture could
otherwise reach, an unreadable event stream and a body carrying a template
opener.

THE DETECTOR RUNS HERE, BEFORE THE WRITE, and that placement is the clause's
own: a ledger comment is append-only -- `bd comments` offers add and list, with
no edit and no delete -- and an opener in one refuses EVERY later dispatch of
that item, permanently. So a body is graded before it can be appended, and a
finding withholds the BODY while leaving the journal row standing. Withholding
the row too would lose the one record that says a ref exists.

THE FAILURE DETAIL NEVER REACHES A BODY, which is why the detector almost never
fires. A factory or forge refusal is free-form server text and is exactly where
an opener arrives; `unpreserved_tree_body` carries names and figures only and
the detail goes to the journal row, which is rewritable. The detector is
therefore a backstop against the OTHER inputs -- a work-item id, a run id, a
ref -- rather than the primary defence.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, cast

from livespec_orchestrator_beads_fabro.commands._dispatcher_goal import (
    minijinja_openers_in_text,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_preserved_tree_base import (
    run_base_commit,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_preserved_tree_publish import (
    STEP_TREE,
    PreservedTree,
    PublishFailure,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_preserved_tree_record import (
    PRESERVED_TREE_MARKER,
    PRESERVED_TREE_SKIPPED_STAGE,
    preserved_tree_body,
    preserved_tree_journal_record,
    unpreserved_tree_body,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_preserved_tree_trigger import (
    PreservationTrigger,
    preservation_trigger,
)

__all__: list[str] = [
    "PreservedTreeDisposition",
    "Publication",
    "TerminatedRun",
    "dispose_preserved_tree",
]

# The step a publication that never started is attributed to. An unestablished
# base is a failure of the TREE step and not a sixth step of its own: the
# ratified clause names a closed set -- the files read, a blob, the tree, the
# commit, or the ref -- and the base commit is the one input the tree is taken
# onto, which is the same thing `publish_preserved_tree` reports when the forge
# names no tree for a base it WAS given.
_NO_BASE_STEP = STEP_TREE
_NO_BASE_DETAIL = (
    "the dispatch journal names no staged base commit for this item, so the run's"
    " changed files have no parent commit to be taken onto"
)


class Publication(Protocol):
    """The publication seam, so the decision is exercisable without a forge."""

    def __call__(self, *, base_commit: str) -> PreservedTree | PublishFailure:
        """Publish the run's changed files as one commit over `base_commit`."""
        ...


@dataclass(frozen=True, kw_only=True)
class TerminatedRun:
    """One ended run, as much of it as the disposition reads.

    `event_records` is THREE-VALUED and the third value is the one that matters:
    a tuple of records read, an empty tuple for a stream that carried none, and
    `None` for a stream that could not be read at all. The clause makes the
    third behave like the second rather than like an observed absence, so it is
    carried as its own value instead of being flattened into `()`.
    """

    work_item_id: str
    run_id: str
    factory: str
    failure_text: str
    event_records: tuple[dict[str, object], ...] | None


@dataclass(frozen=True, kw_only=True)
class PreservedTreeDisposition:
    """What to write down, and whether the comment may be written at all.

    `body` is None in two completely different situations and the caller must
    not conflate them: nothing was owed (the run preserved nothing, or its
    terminal patch already carries the tree), or a body was rendered and then
    WITHHELD by the detector. `withheld_reason` is what tells them apart, and
    it is what the journal carries for the second.
    """

    body: str | None
    withheld_reason: str | None
    record: dict[str, object]


def dispose_preserved_tree(
    *,
    run: TerminatedRun,
    journal_records: tuple[dict[str, object], ...],
    publish: Publication,
) -> PreservedTreeDisposition:
    """Decide, publish when owed, and render what gets written down."""
    trigger = preservation_trigger(
        failure_text=run.failure_text,
        records=None
        if run.event_records is None
        else cast("tuple[dict[str, Any], ...]", run.event_records),
    )
    if not trigger.preserves:
        return PreservedTreeDisposition(
            body=None,
            withheld_reason=None,
            record=_skipped_record(run=run, trigger=trigger),
        )
    base = run_base_commit(records=journal_records, work_item_id=run.work_item_id)
    if base is None:
        return _unpreserved(
            run=run, base=None, failure=PublishFailure(step=_NO_BASE_STEP, detail=_NO_BASE_DETAIL)
        )
    published = publish(base_commit=base)
    if isinstance(published, PublishFailure):
        return _unpreserved(run=run, base=base, failure=published)
    return _preserved(run=run, base=base, preserved=published)


def _preserved(
    *, run: TerminatedRun, base: str, preserved: PreservedTree
) -> PreservedTreeDisposition:
    """The success arm, reached only once the base is established.

    `base` is a plain `str` here rather than an optional one, which is the whole
    reason this arm is its own function: the success body NAMES the base, and a
    shared renderer taking an optional would need a fallback for a state it can
    never be in -- an unreachable default that would publish the empty string as
    a base commit if the reasoning behind it ever stopped holding.
    """
    return _graded(
        body=preserved_tree_body(
            work_item_id=run.work_item_id,
            run_id=run.run_id,
            factory=run.factory,
            base_commit=base,
            preserved=preserved,
        ),
        record=_record(run=run, base=base, published=preserved),
    )


def _unpreserved(
    *, run: TerminatedRun, base: str | None, failure: PublishFailure
) -> PreservedTreeDisposition:
    """The failure arm, which is reached with the base established or not."""
    return _graded(
        body=unpreserved_tree_body(
            work_item_id=run.work_item_id,
            run_id=run.run_id,
            factory=run.factory,
            failure=failure,
        ),
        record=_record(run=run, base=base, published=failure),
    )


def _record(
    *, run: TerminatedRun, base: str | None, published: PreservedTree | PublishFailure
) -> dict[str, object]:
    """One journal row for the attempt, through the record module's own builder."""
    return preserved_tree_journal_record(
        work_item_id=run.work_item_id,
        run_id=run.run_id,
        factory=run.factory,
        base_commit=base,
        published=published,
    )


def _graded(*, body: str, record: dict[str, object]) -> PreservedTreeDisposition:
    """Withhold the body when the detector finds an opener in it; keep the row."""
    findings = minijinja_openers_in_text(source=PRESERVED_TREE_MARKER, text=body)
    if not findings:
        return PreservedTreeDisposition(body=body, withheld_reason=None, record=record)
    reason = (
        f"the rendered {PRESERVED_TREE_MARKER} comment carries"
        f" {len(findings)} MiniJinja opener(s), which would refuse every later dispatch"
        " of this item, so the comment was withheld"
    )
    return PreservedTreeDisposition(body=None, withheld_reason=reason, record=record)


def _skipped_record(*, run: TerminatedRun, trigger: PreservationTrigger) -> dict[str, object]:
    """The row a publication that was never owed leaves.

    It carries the terminal patch's size and digest, because a SUPPRESSION that
    recorded neither is indistinguishable from a reading that never looked for
    a patch -- and the suppression is exactly the case where the clause requires
    the figures to stand on their own. Both are null when nothing was measured,
    which includes the run that failed no checkpoint at all: inventing a zero
    there would assert the run carried no work.
    """
    return {
        "stage": PRESERVED_TREE_SKIPPED_STAGE,
        "work_item_id": run.work_item_id,
        "run_id": run.run_id,
        "factory": run.factory,
        "node": trigger.node,
        "reason": trigger.reason,
        "terminal_patch_bytes": trigger.terminal_patch_bytes,
        "terminal_patch_sha256": trigger.terminal_patch_sha256,
    }
