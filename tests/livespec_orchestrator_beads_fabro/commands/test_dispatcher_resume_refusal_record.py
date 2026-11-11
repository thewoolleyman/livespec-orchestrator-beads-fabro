"""The ledger comment a refused automatic overtaken-arming resume leaves behind.

Scenario 184's record-file arm: "When the resume refuses, the item MUST rest at
`blocked` ... and the ledger comment and the outcome detail MUST name the
refusal." The comment opens with the overtaken-arming marker line and is
written on the same fail-soft terms as the ending's ordinary record.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_base_advance_record as writer,
)
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_resume_refusal_record as record,
)
from livespec_orchestrator_beads_fabro.errors import BeadsCommandError

_ITEM_ID = "bd-ib-mfl2qa"
_REFUSALS = ("the pull request is closed", "a live run is attached")


@dataclass(kw_only=True)
class _Journal:
    records: list[dict[str, object]] = field(default_factory=list)

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


def test_the_body_opens_with_the_marker_and_names_every_refusal() -> None:
    body = record.resume_refusal_comment_body(
        work_item_id=_ITEM_ID, pr_number=184, pr_head="head1111", refusals=_REFUSALS
    )

    lines = body.split("\n")
    assert lines[0] == "livespec-base-advanced-after-arming"
    assert f"work-item: {_ITEM_ID}" in lines
    assert "pull request: 184" in lines
    assert "pull request head: head1111" in lines
    assert "- the pull request is closed" in lines
    assert "- a live run is attached" in lines
    assert "resolve-blocked:<work-item>:ready" in body


@pytest.mark.parametrize("head", [None, "not identifier shaped!"])
def test_a_head_that_is_unreported_or_not_identifier_shaped_is_left_out(head: str | None) -> None:
    body = record.resume_refusal_comment_body(
        work_item_id=_ITEM_ID, pr_number=None, pr_head=head, refusals=_REFUSALS
    )

    assert "pull request head: (not reported by the forge view)" in body
    assert "pull request: (not reported by the forge view)" in body
    assert "not identifier shaped" not in body


def test_a_written_comment_is_journaled(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    written: list[tuple[str, str]] = []
    monkeypatch.setattr(writer, "store_config", lambda **_: object())
    monkeypatch.setattr(
        writer,
        "append_work_item_comment",
        lambda *, work_item_id, body, **_: written.append((work_item_id, body)),
    )
    journal = _Journal()

    record.record_resume_refusal(
        repo=tmp_path,
        work_item_id=_ITEM_ID,
        pr_number=184,
        pr_head="head1111",
        refusals=_REFUSALS,
        journal=journal,  # pyright: ignore[reportArgumentType]
    )

    assert [one[0] for one in written] == [_ITEM_ID]
    assert journal.records == [
        {"stage": "base-advanced-after-arming-record", "work_item_id": _ITEM_ID, "pr_number": 184}
    ]


def test_a_comment_that_cannot_be_written_is_journaled_not_raised(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail(**_: object) -> None:
        raise BeadsCommandError(command="bd comments add", exit_code=1, stderr="ledger down")

    monkeypatch.setattr(writer, "store_config", lambda **_: object())
    monkeypatch.setattr(writer, "append_work_item_comment", fail)
    journal = _Journal()

    record.record_resume_refusal(
        repo=tmp_path,
        work_item_id=_ITEM_ID,
        pr_number=184,
        pr_head="head1111",
        refusals=_REFUSALS,
        journal=journal,  # pyright: ignore[reportArgumentType]
    )

    assert journal.records == [
        {
            "stage": "base-advanced-after-arming-error",
            "work_item_id": _ITEM_ID,
            "reason": "BeadsCommandError",
        }
    ]


def test_a_refusal_carrying_a_template_opener_is_journaled_and_never_written(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    written: list[object] = []
    monkeypatch.setattr(writer, "store_config", lambda **_: object())
    monkeypatch.setattr(writer, "append_work_item_comment", lambda **kw: written.append(kw))
    journal = _Journal()

    record.record_resume_refusal(
        repo=tmp_path,
        work_item_id=_ITEM_ID,
        pr_number=184,
        pr_head=None,
        refusals=("{" + "{ opener }}",),
        journal=journal,  # pyright: ignore[reportArgumentType]
    )

    assert written == []
    assert journal.records[0]["stage"] == "base-advanced-after-arming-refused"
    assert journal.records[0]["work_item_id"] == _ITEM_ID
