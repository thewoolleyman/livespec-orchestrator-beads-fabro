"""The pre-dispatch screen refuses an item carrying a workflow-edit approval label.

Work-item `bd-ib-tgygh6`. `livespec-dev-tooling-zqrg7d` carried
`approval:workflow-edit-additive` while its text named no workflow path, so the
scope-text heuristic admitted it and the run ended stage-failed and BLOCKED. The
label is the declaration the heuristic cannot see, so the screen reads it
directly and refuses with a host-route detail that names the item and the label.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_completion import host_only_refusal
from livespec_orchestrator_beads_fabro.commands._dispatcher_host_only import (
    WORKFLOW_SCOPE_OVERRIDE_LABEL,
    host_only_refusal_detail,
    is_host_only_item,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.types import WorkItem

_LABELS = ("approval:workflow-edit", "approval:workflow-edit-additive")


def _item() -> WorkItem:
    return WorkItem(
        id="bd-ib-labelled",
        type="task",
        status="ready",
        title="Add a lint step",
        description="Do the thing; no path is named here.",
        origin="freeform",
        gap_id=None,
        rank="a2",
        assignee=None,
        depends_on=(),
        captured_at="2026-11-10T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="auto",
        acceptance_policy="ai-only",
    )


@pytest.mark.parametrize("label", _LABELS)
def test_each_workflow_edit_approval_label_makes_the_item_host_only(label: str) -> None:
    assert is_host_only_item(item=_item(), raw_labels=(label,)) is True


def test_unrelated_labels_leave_the_item_dispatchable() -> None:
    labels = ("approval:other", "workflow-edit", "approval:workflow-editor")
    assert is_host_only_item(item=_item(), raw_labels=labels) is False


def test_the_citation_only_override_does_not_lift_the_label_refusal() -> None:
    labels = (WORKFLOW_SCOPE_OVERRIDE_LABEL, "approval:workflow-edit")
    assert is_host_only_item(item=_item(), raw_labels=labels) is True


@pytest.mark.parametrize("label", _LABELS)
def test_the_refusal_names_the_item_and_the_label_that_matched(label: str, tmp_path: Path) -> None:
    journal = JournalFile(path=tmp_path / "journal.jsonl")

    outcome = host_only_refusal(
        repo=tmp_path,
        item=_item(),
        journal=journal,
        raw_labels=("other", label),
    )

    assert outcome is not None
    assert outcome.stage == "host-only-refused"
    assert outcome.status == "failed"
    assert "bd-ib-labelled" in outcome.detail
    assert f"`{label}`" in outcome.detail
    assert "host-route" in outcome.detail
    other = next(candidate for candidate in _LABELS if candidate != label)
    assert f"`{other}`" not in outcome.detail


def test_the_detail_names_every_matched_label() -> None:
    detail = host_only_refusal_detail(item_id="bd-ib-labelled", raw_labels=_LABELS)

    assert all(f"`{label}`" in detail for label in _LABELS)


def test_the_detail_without_labels_is_unchanged() -> None:
    detail = host_only_refusal_detail(item_id="bd-ib-labelled")

    assert detail == host_only_refusal_detail(item_id="bd-ib-labelled", raw_labels=("other",))
    assert "approval:workflow-edit" not in detail


def test_a_factory_safety_item_is_still_refused_without_labels() -> None:
    item = replace(_item(), factory_safety="mutates-host-machinery")

    assert is_host_only_item(item=item, raw_labels=()) is True
