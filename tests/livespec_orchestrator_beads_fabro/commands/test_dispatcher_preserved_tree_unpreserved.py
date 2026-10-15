"""The durable record a FAILED tree preservation leaves, and where its words go."""

from __future__ import annotations

import importlib

from livespec_orchestrator_beads_fabro.commands._dispatcher_goal import (
    minijinja_openers_in_text,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_preserved_tree_publish import (
    STEP_BLOB,
    STEP_FILES_READ,
    PreservedTree,
    PublishFailure,
)

_MODULE = "livespec_orchestrator_beads_fabro.commands._dispatcher_preserved_tree_record"

_RUN_ID = "01M4YJGC55V86C9V1X07QG3Y2H"
_FACTORY = "hp"
_BASE_COMMIT = "5d511335aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
# An engine refusal quoting a shell command, which is exactly where a MiniJinja
# opener arrives -- the one thing a ledger comment may never carry, because an
# opener in one refuses every later dispatch of the item, permanently.
_POISONED_DETAIL = "the factory refused: {{ item.id }} while running `just check`"


def test_a_failed_preservation_states_the_tree_was_not_preserved_and_names_the_step() -> None:
    record = importlib.import_module(_MODULE)
    # The name is not exported at Red, so this is a genuine assertion failure
    # rather than an AttributeError reaching for a function that is not there.
    assert "unpreserved_tree_body" in record.__all__
    body = record.unpreserved_tree_body(
        work_item_id="bd-ib-na2xvm",
        run_id=_RUN_ID,
        factory=_FACTORY,
        failure=PublishFailure(step=STEP_FILES_READ, detail=_POISONED_DETAIL),
    )
    assert body.splitlines()[0] == record.PRESERVED_TREE_MARKER
    assert "NOT preserved" in body
    assert f"failed step: {STEP_FILES_READ}" in body
    for named in (_RUN_ID, _FACTORY, "bd-ib-na2xvm"):
        assert named in body, named
    # Names and figures only: the step's own words are the journal's, not this
    # record's -- and this is the case that proves it, since carrying them
    # would put an opener into an append-only comment.
    assert "just check" not in body
    assert minijinja_openers_in_text(source="unpreserved-tree", text=body) == ()


def test_the_journal_row_carries_the_failed_step_and_its_own_words() -> None:
    record = importlib.import_module(_MODULE)
    assert "preserved_tree_journal_record" in record.__all__
    failed = record.preserved_tree_journal_record(
        work_item_id="bd-ib-na2xvm",
        run_id=_RUN_ID,
        factory=_FACTORY,
        base_commit=_BASE_COMMIT,
        published=PublishFailure(step=STEP_BLOB, detail=_POISONED_DETAIL),
    )
    assert failed["stage"] == record.PRESERVED_TREE_UNPRESERVED_STAGE
    assert failed["failed_step"] == STEP_BLOB
    assert failed["detail"] == _POISONED_DETAIL
    assert failed["preservation_ref"] is None
    published = record.preserved_tree_journal_record(
        work_item_id="bd-ib-na2xvm",
        run_id=_RUN_ID,
        factory=_FACTORY,
        base_commit=_BASE_COMMIT,
        published=PreservedTree(
            ref="refs/livespec/preserved-publish/x/y", commit="y", file_count=2
        ),
    )
    assert published["stage"] == record.PRESERVED_TREE_STAGE
    # Both arms write the SAME key set, nulls included: an omitted key is what a
    # row from a build predating this clause looks like, so a reader could not
    # tell "named no ref" from "never attempted one".
    assert set(published) == set(failed)
    assert published["failed_step"] is None
    assert published["changed_file_count"] == 2
