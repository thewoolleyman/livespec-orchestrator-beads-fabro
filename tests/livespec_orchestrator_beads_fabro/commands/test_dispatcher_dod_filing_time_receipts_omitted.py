"""A filing-time tier record and mechanical finding comment are not brief.

`SPECIFICATION/scenarios.md` Scenario 239 ("A filing-time tier record and
mechanical finding are omitted after a revision ratifies the referenced
heading"): each reports a judgement taken against one specification version, so
a later taking must not read it as operator brief.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_dod_governing_reuse as reuse,
)
from livespec_orchestrator_beads_fabro.commands import _dispatcher_dod_judgement as judgement
from livespec_orchestrator_beads_fabro.commands import _dispatcher_goal as goal
from livespec_orchestrator_beads_fabro.store import WorkItemComment
from livespec_orchestrator_beads_fabro.types import WorkItem

_TIER = (
    "livespec-spec-change-tier\n\nwork-item: bd-ib-7zzm42\nstage: filing\n"
    "spec-version: 123\nrationale: STALE-TIER-RATIONALE"
)
_MECHANICAL = (
    "definition-of-done finding (mechanical): STALE-MECHANICAL-FINDING "
    "the References heading does not resolve"
)
_RIDER = "Rider: RIDER-AFTER-FILING narrows the first assertion."


def _item() -> WorkItem:
    return WorkItem(
        id="bd-ib-7zzm42",
        type="feature",
        status="pending-approval",
        title="A stale filing-time record is not brief",
        description=(
            "## Definition of Done\n\n"
            "- The judgement runs before an item moves to ready.\n\n"
            "References: ## Scenario 174 — The judgement runs before admission\n"
        ),
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee=None,
        depends_on=(),
        captured_at="2026-11-03T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="auto",
        acceptance_policy="ai-only",
    )


@pytest.mark.parametrize("receipt", [_TIER, _MECHANICAL])
def test_subject_goal_and_digests_omit_the_receipt_and_keep_the_rider(
    receipt: str, tmp_path: Path
) -> None:
    item = _item()
    with_receipt = (_RIDER, receipt)
    without = (_RIDER,)

    subject = judgement.judgement_subject(item=item, cwd=tmp_path, comments=with_receipt)
    rendered = goal.render_goal(
        item=item,
        repo=tmp_path,
        branch="feat/bd-ib-7zzm42",
        comments=tuple(
            WorkItemComment(text=text, author=None, created_at=None) for text in with_receipt
        ),
    )

    assert "RIDER-AFTER-FILING" in subject
    assert "RIDER-AFTER-FILING" in rendered
    assert "STALE-TIER-RATIONALE" not in subject + rendered
    assert "STALE-MECHANICAL-FINDING" not in subject + rendered
    assert judgement.judgement_subject_digest(
        item=item, cwd=tmp_path, comments=with_receipt
    ) == judgement.judgement_subject_digest(item=item, cwd=tmp_path, comments=without)
    assert reuse.governing_heading_subject_digest(
        item=item, comments=with_receipt
    ) == reuse.governing_heading_subject_digest(item=item, comments=without)


def test_a_comment_that_merely_mentions_a_receipt_marker_stays_a_rider(tmp_path: Path) -> None:
    quoting = "Operator note: the livespec-spec-change-tier record above is stale."

    subject = judgement.judgement_subject(item=_item(), cwd=tmp_path, comments=(quoting,))

    assert quoting in subject
