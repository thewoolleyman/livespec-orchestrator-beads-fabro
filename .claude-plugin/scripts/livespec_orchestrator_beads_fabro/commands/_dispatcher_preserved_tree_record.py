"""The records a tree preservation leaves: one ledger comment and one journal row.

THE COMMENT IS THE ONLY THING THAT OUTLIVES THE RUN, which is why it exists at
all. The ref the publication creates is durable, but nothing points at it: the
dispatch result is read once, the journal lives in the `tmp/` tree of whichever
host ran the dispatch, and the factory prunes the run. A recovery three days
later starts from the work-item, so the ref has to be NAMED there or it is a
durable artifact nobody can find.

NAMES AND FIGURES ONLY, in both bodies, by the clause's own words, and here is
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
    PublishFailure,
)

__all__: list[str] = [
    "PRESERVED_TREE_MARKER",
    "PRESERVED_TREE_RECORD_STAGE",
    "PRESERVED_TREE_SKIPPED_STAGE",
    "PRESERVED_TREE_STAGE",
    "PRESERVED_TREE_UNPRESERVED_STAGE",
    "preserved_tree_body",
    "preserved_tree_journal_record",
    "unpreserved_tree_body",
]

PRESERVED_TREE_MARKER = "livespec-preserved-tree"

# The three journal stages, kept apart because they answer different questions.
# `PRESERVED_TREE_STAGE` is a ref that now exists, `..._UNPRESERVED_STAGE` is a
# publication that was attempted and failed, and `..._SKIPPED_STAGE` is one
# that was never owed. A single stage carrying an outcome field would make
# "nothing needed preserving" and "preservation failed" one row shape, and an
# operator scanning for lost work would have to read every row to tell them
# apart.
PRESERVED_TREE_STAGE = "preserved-tree"
PRESERVED_TREE_UNPRESERVED_STAGE = "preserved-tree-unpreserved"
PRESERVED_TREE_SKIPPED_STAGE = "preserved-tree-skipped"
# The write of the comment itself, which can fail independently of the
# publication and must not prevent the item's blocked transition.
PRESERVED_TREE_RECORD_STAGE = "preserved-tree-record-error"

# What each publication step was doing, so the failure body names an operation
# rather than a token. Keyed on the step constants `..._publish` exports, which
# is what keeps the two from drifting into two vocabularies for one closed set.
_STEP_PROSE = {
    "files-read": "reading the run's changed files from the factory",
    "blob": "creating a blob for one of the run's changed files on the forge",
    "tree": "creating the tree of the run's changes on the forge",
    "commit": "creating the preservation commit on the forge",
    "ref": "creating the preservation ref on the forge",
}

_RECOVERY = (
    "recover by checking out the base commit above and taking the ref's tree onto it as"
    " uncommitted work; the ref's commit ran no hook and passed no check suite, so it is"
    " a recovery artifact and not a commit to land"
)

# Where the step's own words went, said on the failure record's own face. The
# body here carries none of them (see the module docstring), so without this
# line the record reads as the whole account of a failure it deliberately
# under-describes, and its reader has no reason to go to the journal.
_WORDS_ARE_IN_THE_JOURNAL = (
    "the dispatch journal row for this stage names what the step reported;"
    " this record carries names and figures only"
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


def unpreserved_tree_body(
    *,
    work_item_id: str,
    run_id: str,
    factory: str,
    failure: PublishFailure,
) -> str:
    """The comment a failed publication leaves. PURE.

    It states the NEGATIVE outright rather than leaving it to be inferred from
    a missing ref line. A record that merely omitted the ref would read exactly
    like the success body with one line lost, and the reader would go looking
    for a ref that does not exist.

    It carries no excerpt of the step's own output; see the module docstring.
    The journal row beside it carries that.
    """
    return "\n".join(
        [
            PRESERVED_TREE_MARKER,
            "",
            f"work-item: {work_item_id}",
            f"run id: {run_id}",
            f"factory: {factory}",
            "preservation ref: none -- the tree was NOT preserved",
            f"failed step: {failure.step}",
            f"the step was: {_STEP_PROSE.get(failure.step, 'an unnamed publication step')}",
            "",
            _WORDS_ARE_IN_THE_JOURNAL,
        ]
    )


def preserved_tree_journal_record(
    *,
    work_item_id: str,
    run_id: str,
    factory: str,
    base_commit: str | None,
    published: PreservedTree | PublishFailure,
) -> dict[str, object]:
    """One journal row for an attempted publication, whichever way it went.

    EVERY KEY IS WRITTEN ON BOTH ARMS, nulls included, for the reason
    `_dispatcher_sandbox_image_source` gives about its own record: an omitted
    key is what a row from a build predating this clause looks like, so a
    reader could not tell "this publication named no ref" from "this build
    never attempted one". The `detail` is where the step's own words go.
    """
    common: dict[str, object] = {
        "work_item_id": work_item_id,
        "run_id": run_id,
        "factory": factory,
        "base_commit": base_commit,
    }
    if isinstance(published, PublishFailure):
        return {
            "stage": PRESERVED_TREE_UNPRESERVED_STAGE,
            **common,
            "preservation_ref": None,
            "preservation_commit": None,
            "changed_file_count": None,
            "failed_step": published.step,
            "detail": published.detail,
        }
    return {
        "stage": PRESERVED_TREE_STAGE,
        **common,
        "preservation_ref": published.ref,
        "preservation_commit": published.commit,
        "changed_file_count": published.file_count,
        "failed_step": None,
        "detail": None,
    }
