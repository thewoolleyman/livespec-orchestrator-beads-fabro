"""The item-comment read and the governing receipt render as their own modules.

Both were split out of the gate and the record, which sit at the file size ceiling,
and each keeps the behaviour it had there: an unreadable ledger answers `None` rather
than an empty tuple, and a receipt renders the lines the reuse rule scans for.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands import _dispatcher_dod_item_comments as comments
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_governing_record import (
    GoverningHeadingReceipt,
    governing_record_lines,
)
from livespec_orchestrator_beads_fabro.commands._dod_governing_heading import (
    GoverningHeadingVerdict,
)
from livespec_orchestrator_beads_fabro.errors import BeadsCommandError
from livespec_orchestrator_beads_fabro.types import StoreConfig


@dataclass(frozen=True)
class _Comment:
    text: str


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="bd-ib",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
        repo_root=Path(),
    )


def test_item_comment_bodies_answers_the_texts_oldest_first(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        comments,
        "read_work_item_comments",
        lambda *, path, work_item_id: [_Comment("first"), _Comment("second")],  # noqa: ARG005
    )

    assert comments.item_comment_bodies(path=_config(), work_item_id="x") == ("first", "second")


def test_item_comment_bodies_answers_none_when_the_ledger_cannot_be_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _unreadable(*, path: StoreConfig, work_item_id: str) -> list[_Comment]:  # noqa: ARG001
        raise BeadsCommandError(command="bd comments", exit_code=1, stderr="down")

    monkeypatch.setattr(comments, "read_work_item_comments", _unreadable)

    assert comments.item_comment_bodies(path=_config(), work_item_id="x") is None


def test_governing_record_lines_name_kind_digest_provenance_and_headings() -> None:
    receipt = GoverningHeadingReceipt(
        verdict=GoverningHeadingVerdict(
            kind="partial",
            stated_by=("## A",),
            generalization_target="## B",
            provenance_complete=False,
        ),
        subject_digest="sha256:abc",
    )

    assert governing_record_lines(governing=receipt) == [
        "governing-heading-kind: partial",
        "governing-heading-subject-digest: sha256:abc",
        "governing-heading-provenance: incomplete",
        "governing-heading: ## A",
        "governing-heading-generalization-target: ## B",
    ]
