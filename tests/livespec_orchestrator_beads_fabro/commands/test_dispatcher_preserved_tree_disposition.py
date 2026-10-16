"""What one terminated run's tree preservation decides, records and never claims."""

from __future__ import annotations

from dataclasses import dataclass, field

from livespec_orchestrator_beads_fabro.commands._dispatcher_preserved_tree_base import SOURCE_STAGE
from livespec_orchestrator_beads_fabro.commands._dispatcher_preserved_tree_disposition import (
    PreservedTreeDisposition,
    TerminatedRun,
    dispose_preserved_tree,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_preserved_tree_publish import (
    STEP_FILES_READ,
    STEP_TREE,
    PreservedTree,
    PublishFailure,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_preserved_tree_record import (
    PRESERVED_TREE_MARKER,
    PRESERVED_TREE_SKIPPED_STAGE,
    PRESERVED_TREE_STAGE,
    PRESERVED_TREE_UNPRESERVED_STAGE,
)

_ITEM = "bd-ib-na2xvm"
_RUN = "01M4YJGC55V86C9V1X07QG3Y2H"
_FACTORY = "hp"
_BASE = "5d511335aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
_REF = f"refs/livespec/preserved-publish/{_ITEM}/abc123"

# The engine's own wording for the ending, as measured on the incident run.
_CHECKPOINT_FAILED = "git checkpoint commit failed for node implement: git add failed (exit 127)"
_PRESERVED = PreservedTree(ref=_REF, commit="abc123", file_count=48)
_PATCH = "diff --git a/x b/x\n"


def _staged(*, work_item_id: str = _ITEM) -> tuple[dict[str, object], ...]:
    return ({"stage": SOURCE_STAGE, "work_item_id": work_item_id, "staged_at": _BASE},)


@dataclass(kw_only=True)
class _Publication:
    """A publication double that records every base it was asked to publish over."""

    result: PreservedTree | PublishFailure
    bases: list[str] = field(default_factory=list[str])

    def __call__(self, *, base_commit: str) -> PreservedTree | PublishFailure:
        self.bases.append(base_commit)
        return self.result


def _disposed(
    *,
    result: PreservedTree | PublishFailure = _PRESERVED,
    failure_text: str = _CHECKPOINT_FAILED,
    event_records: tuple[dict[str, object], ...] | None = (),
    journal_records: tuple[dict[str, object], ...] | None = None,
    work_item_id: str = _ITEM,
) -> tuple[PreservedTreeDisposition, _Publication]:
    publication = _Publication(result=result)
    disposition = dispose_preserved_tree(
        run=TerminatedRun(
            work_item_id=work_item_id,
            run_id=_RUN,
            factory=_FACTORY,
            failure_text=failure_text,
            event_records=event_records,
        ),
        journal_records=_staged(work_item_id=work_item_id)
        if journal_records is None
        else journal_records,
        publish=publication,
    )
    return disposition, publication


def test_a_checkpoint_failed_run_with_no_terminal_patch_publishes_its_tree() -> None:
    disposed, publication = _disposed()
    assert publication.bases == [_BASE]
    assert disposed.body is not None
    assert disposed.body.splitlines()[0] == PRESERVED_TREE_MARKER
    for named in (_RUN, _FACTORY, _REF, "abc123"):
        assert named in disposed.body, named
    assert disposed.record["stage"] == PRESERVED_TREE_STAGE
    assert disposed.record["preservation_ref"] == _REF
    assert disposed.record["base_commit"] == _BASE
    assert disposed.withheld_reason is None


def test_a_run_whose_terminal_event_carries_a_patch_is_not_published() -> None:
    # The suppression records the patch's size and digest, because a suppression
    # that recorded neither is indistinguishable from a reading that never
    # looked for a patch at all.
    disposed, publication = _disposed(
        event_records=({"type": "run.failed", "terminal_patch": _PATCH},)
    )
    assert publication.bases == []
    assert disposed.body is None
    assert disposed.record["stage"] == PRESERVED_TREE_SKIPPED_STAGE
    assert disposed.record["terminal_patch_bytes"] == len(_PATCH)
    assert isinstance(disposed.record["terminal_patch_sha256"], str)


def test_a_run_whose_events_cannot_be_read_is_still_published() -> None:
    # An unreadable stream makes a terminal patch UNOBSERVED rather than absent,
    # and the clause makes the publication mandatory there: a duplicate
    # preservation is recoverable, a missed one is not.
    disposed, publication = _disposed(event_records=None)
    assert publication.bases == [_BASE]
    assert disposed.record["stage"] == PRESERVED_TREE_STAGE


def test_a_run_that_failed_no_checkpoint_is_not_published() -> None:
    disposed, publication = _disposed(failure_text="the pr stage could not push the branch")
    assert publication.bases == []
    assert disposed.body is None
    assert disposed.record["stage"] == PRESERVED_TREE_SKIPPED_STAGE
    # Both figures are null, because nothing looked for a patch on a run whose
    # ending was never a checkpoint failure.
    assert disposed.record["terminal_patch_bytes"] is None
    assert disposed.record["terminal_patch_sha256"] is None


def test_a_failed_publication_says_so_and_names_the_step() -> None:
    disposed, _ = _disposed(
        result=PublishFailure(step=STEP_FILES_READ, detail="the factory returned status 401")
    )
    assert disposed.body is not None
    assert disposed.body.splitlines()[0] == PRESERVED_TREE_MARKER
    assert "NOT preserved" in disposed.body
    assert f"failed step: {STEP_FILES_READ}" in disposed.body
    assert disposed.record["stage"] == PRESERVED_TREE_UNPRESERVED_STAGE
    assert disposed.record["failed_step"] == STEP_FILES_READ
    assert disposed.record["detail"] == "the factory returned status 401"


def test_an_unestablished_base_commit_is_reported_and_nothing_is_published() -> None:
    # Publishing over a guessed parent would produce a tree whose diff is
    # against a commit the run never saw, which reads as a large successful
    # implement stage. So the base is a precondition, not a default.
    disposed, publication = _disposed(journal_records=())
    assert publication.bases == []
    assert disposed.body is not None
    assert "NOT preserved" in disposed.body
    assert f"failed step: {STEP_TREE}" in disposed.body
    assert disposed.record["stage"] == PRESERVED_TREE_UNPRESERVED_STAGE
    assert disposed.record["base_commit"] is None


def test_the_step_s_own_words_reach_the_journal_and_never_the_comment() -> None:
    # A factory or forge refusal is free-form server text, and that is exactly
    # where a MiniJinja opener arrives. The body carries names and figures only,
    # so a poisoned detail is journaled and the comment stays writable.
    opener = "{" + "{ item.id }" + "}"
    disposed, _ = _disposed(
        result=PublishFailure(step=STEP_FILES_READ, detail=f"the factory said {opener}")
    )
    assert disposed.body is not None
    assert opener not in disposed.body
    assert disposed.withheld_reason is None
    assert disposed.record["detail"] == f"the factory said {opener}"


def test_a_body_that_would_carry_an_opener_is_withheld_with_its_reason() -> None:
    # The detector runs BEFORE the write because a comment cannot be repaired
    # once appended, and an opener in one refuses every later dispatch of the
    # item permanently. A finding withholds the body and leaves the journal row,
    # which must not prevent the blocked transition.
    opener = "{" + "{ item.id }" + "}"
    disposed, publication = _disposed(work_item_id=f"bd-ib{opener}")
    assert publication.bases == [_BASE]
    assert disposed.body is None
    assert disposed.withheld_reason is not None
    assert "opener" in disposed.withheld_reason
    # The publication still happened and its row still stands.
    assert disposed.record["stage"] == PRESERVED_TREE_STAGE
