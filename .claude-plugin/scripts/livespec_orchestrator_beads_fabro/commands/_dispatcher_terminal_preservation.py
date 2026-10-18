"""Both preservations a terminated run's work is owed, in the clause's own order.

A run that ends without merging leaves work in two different places, and the
ratified text treats them as two obligations rather than one. The POINTER names
the terminal patch the run itself carried -- its size and digest -- so that a
pointer reporting no checkpointed diff artifact is not read as no work. The TREE
is what nothing else carries: when the engine's checkpoint commit failed and no
terminal patch was observed, the changed files exist only inside the stopped
container on the factory, and a forge ref is the only durable thing they can
become.

THEY ARE SEPARATE LEGS BECAUSE THEY FAIL SEPARATELY. The pointer is a reading of
the run record; the tree is a factory read plus four forge writes. Folding them
into one attempt would let a refused forge blob suppress the pointer that would
otherwise still have been written, which is the one direction neither clause
permits: each is the other's fallback account of the same lost work.

ORDER IS THE RATIFIED ONE AND NOT A CONVENIENCE. Both run BEFORE the item's
blocked transition, because the tree clause says its comment is written "before
the item's blocked transition" -- the comment is the only durable pointer at the
ref, since the dispatch result is read once, the journal lives in the `tmp/` tree
of whichever host ran the dispatch, and the factory prunes the run. The pointer
goes first because it is the cheaper and more widely-owed of the two, so a tree
leg that hangs on an unreachable factory cannot cost the pointer its write.

EVERY ARM IS FAIL-SOFT, WHICH IS RATIFIED RATHER THAN LENIENT: "a failed
preservation MUST NOT change the dispatch outcome or its exit code". The run has
already ended and the item rests at `blocked` / `needs-human` either way, so
there is no decision left for a raised error to inform -- and converting an ended
run into a dispatch failure after the fact would misreport a dispatch that did
exactly what it was asked to.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_preserve_reference import (
    preserve_checkpointed_work_reference,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_preserved_tree_escalation import (
    PreservationInputs,
    preserve_checkpoint_failed_tree,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_reflection_journal import (
    read_journal_records,
)
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "PRESERVED_TREE_ERROR_STAGE",
    "PRESERVE_BY_REFERENCE_ERROR_STAGE",
    "preserve_terminated_run_work",
]

# One stage per leg, because the two have different remedies: a refused pointer
# leaves the run record unread, while a refused tree leaves changed files on a
# factory that will prune them. A shared stage carrying a leg field would make
# the pair indistinguishable to a reader filtering the journal by stage.
PRESERVE_BY_REFERENCE_ERROR_STAGE = "preserve-by-reference-error"
PRESERVED_TREE_ERROR_STAGE = "preserved-tree-error"


def preserve_terminated_run_work(
    *,
    args: argparse.Namespace,
    repo: Path,
    item: WorkItem,
    outcome: DispatchOutcome,
    journal: JournalFile,
) -> None:
    """Preserve this terminated run's work by pointer, then by tree."""
    _preserve_pointer(args=args, repo=repo, item=item, outcome=outcome, journal=journal)
    _preserve_tree(args=args, repo=repo, item=item, outcome=outcome, journal=journal)


def _preserve_pointer(
    *,
    args: argparse.Namespace,
    repo: Path,
    item: WorkItem,
    outcome: DispatchOutcome,
    journal: JournalFile,
) -> None:
    """The durable pointer at the run's own terminal patch and its digest."""
    preserved = attempt(
        action=lambda: preserve_checkpointed_work_reference(
            args=args,
            repo=repo,
            item=item,
            outcome=outcome,
            journal=journal,
        ),
        exceptions=(OSError,),
    )
    if isinstance(preserved, AttemptFailure):
        journal.append(
            record={
                "stage": PRESERVE_BY_REFERENCE_ERROR_STAGE,
                "work_item_id": item.id,
                "reason": type(preserved.error).__name__,
                "outcome_stage": outcome.stage,
                "outcome_status": outcome.status,
            }
        )


def _preserve_tree(
    *,
    args: argparse.Namespace,
    repo: Path,
    item: WorkItem,
    outcome: DispatchOutcome,
    journal: JournalFile,
) -> None:
    """The run's changed files as a commit on a preservation ref, when owed.

    The journal is READ BACK off the path this dispatch has been appending to,
    rather than accumulated in memory, because the base commit the preservation
    commit must be parented on was written by the source-staging step much
    earlier in this same dispatch -- and `JournalFile` is a writer, so the
    records only exist on disk. Re-deriving that base with `git rev-parse` would
    answer about THIS host's head rather than the commit the sandbox cloned,
    which on a long drain is routinely a different commit.
    """
    preserved = attempt(
        action=lambda: preserve_checkpoint_failed_tree(
            args=args,
            repo=repo,
            item=item,
            outcome=outcome,
            journal=journal,
            inputs=PreservationInputs(
                journal_records=read_journal_records(journal_path=journal.path),
            ),
        ),
        exceptions=(OSError,),
    )
    if isinstance(preserved, AttemptFailure):
        journal.append(
            record={
                "stage": PRESERVED_TREE_ERROR_STAGE,
                "work_item_id": item.id,
                "reason": type(preserved.error).__name__,
                "outcome_stage": outcome.stage,
                "outcome_status": outcome.status,
            }
        )
