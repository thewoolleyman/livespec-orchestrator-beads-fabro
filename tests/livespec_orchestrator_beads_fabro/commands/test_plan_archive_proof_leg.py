"""The archive gate's THIRD leg: a plan cannot archive unproved.

Binds the first assertion of `bd-ib-wbdgil` and the archive-on-completion proof
leg of `SPECIFICATION/contracts.md` (v115): "`archive_thread` MUST refuse while
the proof leg is unmet, naming each unproved plan assertion, and MUST leave the
plan directory and the epic unchanged."

WHY THE TWO OTHER LEGS ARE SATISFIED HERE RATHER THAN LEFT OUT. A plan with an
undisposed child, or with no completeness-review evidence, already refuses —
for a reason that has nothing to do with proof. A case that left either leg
unmet would pass against a build carrying no proof leg at all, which is exactly
the state this test exists to falsify. So the child is closed, the evidence is
recorded through the real primitive, and the ONLY thing missing is the verified
plan Proof of Done record.

WHY THE DIRECTORY AND THE EPIC ARE BOTH ASSERTED. The refusal is only half the
clause; "leaves the plan directory and the epic unchanged" is the other half,
and the two fail independently. `archive_thread` moves the directory and closes
the epic in the same call, so a proof leg placed AFTER either side effect would
raise the right error over a plan it had already archived — and the exception
alone cannot tell that apart from a refusal that changed nothing.
"""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import (
    FakeBeadsClient,
    IssueDraft,
    make_beads_client,
    reset_fake_singleton,
)
from livespec_orchestrator_beads_fabro.commands._plan_definition_of_done import (
    PlanDefinitionOfDone,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig

_SLUG = "proof-leg-thread"
_ASSERTION = "The operator drives the delivered command and sees it work."


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="bd-ib",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
    )


def _fake() -> FakeBeadsClient:
    client = make_beads_client(config=_config())
    assert isinstance(client, FakeBeadsClient)
    return client


def test_closed_children_and_a_coverage_review_do_not_archive_an_unproved_plan(
    tmp_path: Path,
) -> None:
    reset_fake_singleton()
    plan = importlib.import_module("livespec_orchestrator_beads_fabro.commands.plan")
    created = plan.create_thread(
        project_root=tmp_path,
        config=_config(),
        slug=_SLUG,
        title="Proof leg thread",
        research_filename="initial.md",
        research_text="research\n",
        now="2026-10-04T00:00:00Z",
        definition_of_done=PlanDefinitionOfDone(
            statement="Done when the operator has driven it and seen it work.",
            assertions=(_ASSERTION,),
        ),
    )
    epic_id = created["epic_id"]
    _ = _fake().create_issue(
        draft=IssueDraft(
            issue_id="bd-ib-proofchild",
            issue_type="task",
            title="child",
            description="child work",
            assignee=None,
            created_at="2026-10-04T00:00:00Z",
            parent_id=epic_id,
            metadata={"rank": "a1"},
            labels=["origin:freeform"],
        )
    )
    _fake().close_issue(issue_id="bd-ib-proofchild", reason="completed")
    plan.record_completeness_review_evidence(
        config=_config(),
        epic_id=epic_id,
        evidence_id="review-evidence-1",
        reviewer_identity="fresh-independent-reviewer",
        separate_reviewer=True,
        attests_complete_requirement_coverage=True,
        body="Every requirement carrier under the plan is covered.",
        now="2026-10-05T00:00:00Z",
    )

    with pytest.raises(plan.PlanArchiveRefusedError) as refused:
        plan.archive_thread(
            project_root=tmp_path,
            config=_config(),
            slug=_SLUG,
            epic_id=epic_id,
            completeness_review_comment_id="review-evidence-1",
        )

    # The refusal NAMES the unproved assertion rather than merely reporting that
    # proof is owed: a message naming only the epic sends its reader back to
    # count bullets in the description to learn which assertion went unproved.
    assert _ASSERTION in str(refused.value)
    assert (tmp_path / "plan" / _SLUG).is_dir()
    assert not (tmp_path / "plan" / "archive").exists()
    assert _fake().show_issue(issue_id=epic_id)["status"] != "closed"
