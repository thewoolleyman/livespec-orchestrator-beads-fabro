"""The merged proof-only arm is authorized by the current acceptance park."""

from __future__ import annotations

import importlib
from pathlib import Path
from types import ModuleType

import pytest
from livespec_orchestrator_beads_fabro._store_comments import WorkItemComment
from livespec_orchestrator_beads_fabro.types import WorkItem, WorkItemStatus

_MODULE_NAME = "livespec_orchestrator_beads_fabro.commands._dispatcher_resume_observation"
_MODULE_PATH = Path(
    ".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/_dispatcher_resume_observation.py"
)
_ITEM_ID = "bd-ib-proof-park"


def _module() -> ModuleType:
    assert _MODULE_PATH.is_file()
    return importlib.import_module(_MODULE_NAME)


def _item(*, status: WorkItemStatus = "acceptance") -> WorkItem:
    return WorkItem(
        id=_ITEM_ID,
        type="task",
        status=status,
        title="A parked merged item",
        description="## Definition of Done\n\n- It is re-proven.\n",
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee=None,
        depends_on=(),
        captured_at="2026-11-04T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
    )


def _comment(*, pending: str) -> WorkItemComment:
    return WorkItemComment(
        text=f"Acceptance parking record — NEEDS_ATTENTION — pending: {pending}",
        author=None,
        created_at=None,
    )


def test_the_merged_proof_evidence_park_authorizes_the_proof_only_arm() -> None:
    """Scenario 257: only the latest proof-evidence park opens the merged arm."""
    module = _module()

    assert hasattr(module, "proof_only_resume")
    assert (
        module.proof_only_resume(
            item=_item(),
            pull_request_state="MERGED",
            comments=(_comment(pending="proof of done record for 'the assertion'"),),
        )
        is True
    )


@pytest.mark.parametrize(
    ("item", "state", "comments"),
    [
        (_item(status="ready"), "MERGED", ()),
        (_item(), "OPEN", ()),
        (_item(), "MERGED", "ledger comments unreadable"),
        (_item(), "MERGED", ()),
        (
            _item(),
            "MERGED",
            (
                _comment(pending="proof of done record for 'the assertion'"),
                _comment(pending="merged diff"),
            ),
        ),
    ],
)
def test_only_the_latest_merged_proof_evidence_park_authorizes_the_arm(
    item: WorkItem, state: str, comments: tuple[WorkItemComment, ...] | str
) -> None:
    """A stale, unreadable, or different park keeps the ordinary refusal in force."""
    module = _module()

    assert hasattr(module, "proof_only_resume")
    assert module.proof_only_resume(item=item, pull_request_state=state, comments=comments) is False
