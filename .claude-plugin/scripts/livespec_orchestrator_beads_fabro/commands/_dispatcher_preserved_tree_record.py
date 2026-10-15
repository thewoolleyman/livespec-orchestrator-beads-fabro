"""The records a tree preservation leaves: one ledger comment and one journal row.

THE COMMENT IS THE ONLY THING THAT OUTLIVES THE RUN, which is why it exists at
all. The ref the publication creates is durable, but nothing points at it: the
dispatch result is read once, the journal lives in the `tmp/` tree of whichever
host ran the dispatch, and the factory prunes the run. A recovery three days
later starts from the work-item, so the ref has to be NAMED there or it is a
durable artifact nobody can find.

NAMES AND FIGURES ONLY, by the ratified clause's own words, and this module is
where that rule is kept. A forge or factory refusal arrives as free-form server
text, and this record cannot be repaired once appended -- `bd comments` offers
add and list, with no edit and no delete. So a body here names what happened
and the server's own words go to the JOURNAL row, which is rewritable and is
where the sibling checkpoint-failure clause already puts its bounded excerpt.
Keeping the excerpt out is not tidiness: an engine message quoting a shell
command is exactly where a MiniJinja opener arrives, and an opener in a ledger
comment refuses EVERY later dispatch of the item, permanently.

EVERY BODY HERE IS PURE, so every claim it makes is testable without a forge, a
factory or a tenant. `_dispatcher_preserved_tree_disposition` owns the detector
pass and the write.
"""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._dispatcher_preserved_tree_publish import (
    PreservedTree,
)

__all__: list[str] = [
    "PRESERVED_TREE_MARKER",
    "PRESERVED_TREE_RECORD_STAGE",
    "PRESERVED_TREE_SKIPPED_STAGE",
    "PRESERVED_TREE_STAGE",
    "preserved_tree_body",
]

PRESERVED_TREE_MARKER = "livespec-preserved-tree"

# The journal stages, kept apart because they answer different questions.
# `PRESERVED_TREE_STAGE` is a ref that now exists and `..._SKIPPED_STAGE` is a
# publication that was never owed. A single stage carrying an outcome field
# would make "nothing needed preserving" and "preservation failed" one row
# shape, and an operator scanning for lost work would have to read every row to
# tell them apart.
PRESERVED_TREE_STAGE = "preserved-tree"
PRESERVED_TREE_SKIPPED_STAGE = "preserved-tree-skipped"
# The write of the comment itself, which can fail independently of the
# publication and must not prevent the item's blocked transition.
PRESERVED_TREE_RECORD_STAGE = "preserved-tree-record-error"

_RECOVERY = (
    "recover by checking out the base commit above and taking the ref's tree onto it as"
    " uncommitted work; the ref's commit ran no hook and passed no check suite, so it is"
    " a recovery artifact and not a commit to land"
)


def preserved_tree_body(
    *,
    work_item_id: str,
    run_id: str,
    factory: str,
    base_commit: str,
    preserved: PreservedTree,
) -> str:
    """The comment a successful publication leaves. PURE.

    The BASE COMMIT is named beside the ref even though the clause lists only
    four things, because without it the ref is unusable: the published commit
    is not a commit to land, so a recovery has to check out the parent and
    apply the tree, and the parent is the one name that makes those two one
    act. Naming it here also means the record survives the journal.
    """
    return "\n".join(
        [
            PRESERVED_TREE_MARKER,
            "",
            f"work-item: {work_item_id}",
            f"run id: {run_id}",
            f"factory: {factory}",
            f"preservation ref: {preserved.ref}",
            f"commit id: {preserved.commit}",
            f"base commit: {base_commit}",
            f"changed files published: {preserved.file_count}",
            "",
            _RECOVERY,
        ]
    )
