"""`spec_commitment_hint` marks a RATIFIED follow-up, never the spec-change tier.

The absorbed defect (`bd-ib-yykjko`): two predicates in this package read that
field as though it MEANT spec-change tier. The autonomy-tier bullet says the
opposite in as many words — the tier is "DECIDED by the spec-stated judgement
..., never declared by the filer and never read off `spec_commitment_hint`
(which marks an implementation follow-up to an already ratified change)" — and
closes with "Plan-child disposition refuses a held spec-change-tier child and
admits an implementation follow-up."

So both predicates are INVERTED: the one item they each singled out is the one
item the tier is never about.

THE TWO CLAIMS ARE EACH OTHER'S CONTROL. "A hint-carrying child is disposable"
is satisfied by a build with the refusal removed entirely, and "a held child is
refused" is satisfied by one that refuses everything — so each is asserted
beside the other over one store, differing in nothing but what the child
carries.

THE ADMISSION FLOOR IS GRADED THROUGH `effective_admission_policy`, because
that is where the other inverted predicate changes an outcome: a hint-carrying
item was pinned to the manual floor whatever its own label said, which holds a
ratified follow-up out of the auto lane for ever.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import (
    EDGE_PARENT_CHILD,
    IssueDraft,
    make_beads_client,
    reset_fake_singleton,
)
from livespec_orchestrator_beads_fabro._store_comments import append_work_item_comment
from livespec_orchestrator_beads_fabro.commands._dispatcher_policy_overrides import (
    effective_admission_policy,
)
from livespec_orchestrator_beads_fabro.commands._plan_disposition import (
    PlanDispositionRefusedError,
    close_plan_child,
    reparent_plan_child,
)
from livespec_orchestrator_beads_fabro.commands._spec_change_tier import (
    SpecChangeTierVerdict,
    spec_change_tier_comment,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem
from returns.unsafe import unsafe_perform_io

_NOW = "2026-10-24T00:00:00Z"
_AUTHOR = "spec-implementation-lockstep"
_EPIC = "bd-ib-epic"
_CHILD = "bd-ib-child"
_TOPIC = "spec-stated-judgement-and-spec-change-tier"
_COMMITMENT = "contracts-dispatcher-admission"


@pytest.fixture(autouse=True)
def _hermetic_fake_backend() -> object:
    reset_fake_singleton()
    yield
    reset_fake_singleton()


def _config(*, repo: Path | None = None) -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="bd-ib",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
        repo_root=repo,
    )


def _issue(*, issue_id: str, issue_type: str, spec_id: str | None = None) -> None:
    _ = make_beads_client(config=_config()).create_issue(
        draft=IssueDraft(
            issue_id=issue_id,
            issue_type=issue_type,
            title=issue_id,
            description=issue_id,
            assignee=None,
            created_at=_NOW,
            metadata={"rank": "a1"},
            labels=["origin:freeform"],
            spec_id=spec_id,
        )
    )


def _seed_plan(*, spec_id: str | None = None, held: bool = False) -> None:
    _issue(issue_id=_EPIC, issue_type="epic")
    _issue(issue_id=_CHILD, issue_type="task", spec_id=spec_id)
    make_beads_client(config=_config()).add_dependency(
        from_id=_CHILD, to_id=_EPIC, edge_type=EDGE_PARENT_CHILD
    )
    if held:
        append_work_item_comment(
            path=_config(),
            work_item_id=_CHILD,
            body=spec_change_tier_comment(
                item_id=_CHILD,
                stage="pre-admission",
                verdict=SpecChangeTierVerdict(
                    item_class="feature",
                    stated_kind="unstated",
                    linked_proposal_topic=_TOPIC,
                ),
            ),
        )


def _close(*, repo: Path) -> None:
    close_plan_child(
        config=_config(repo=repo),
        epic_id=_EPIC,
        child_id=_CHILD,
        rationale="absorbed by a sibling slice",
        author=_AUTHOR,
        now=_NOW,
    )


def _item(*, spec_commitment_hint: str | None, admission_policy: str) -> WorkItem:
    return WorkItem(
        id=_CHILD,
        type="feature",
        status="pending-approval",
        title="A follow-up to an already ratified change",
        description="Prose.",
        origin="freeform",
        gap_id=None,
        rank="a1",
        assignee=None,
        depends_on=(),
        captured_at=_NOW,
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        spec_commitment_hint=spec_commitment_hint,
        admission_policy=admission_policy,  # pyright: ignore[reportArgumentType]
    )


def test_a_commitment_hint_no_longer_pins_an_item_to_the_manual_admission_floor(
    tmp_path: Path,
) -> None:
    """The first inverted predicate: a ratified follow-up kept its own policy.

    Asserted beside an item carrying NO hint, so "the policy came back" is not
    satisfied by a resolver that ignores the item's own label either.
    """
    carrying = _item(spec_commitment_hint=_COMMITMENT, admission_policy="auto")
    plain = _item(spec_commitment_hint=None, admission_policy="auto")

    assert unsafe_perform_io(effective_admission_policy(item=carrying, cwd=tmp_path).unwrap()) == (
        "auto"
    )
    assert unsafe_perform_io(effective_admission_policy(item=plain, cwd=tmp_path).unwrap()) == (
        "auto"
    )


def test_a_plan_child_carrying_a_commitment_hint_is_disposable(tmp_path: Path) -> None:
    """The second inverted predicate: the follow-up the clause says to ADMIT."""
    _seed_plan(spec_id=_COMMITMENT)

    _close(repo=tmp_path)

    assert make_beads_client(config=_config()).show_issue(issue_id=_CHILD)["status"] == "closed"


def test_a_plan_child_held_by_the_spec_change_tier_refuses_closure(tmp_path: Path) -> None:
    """The refusal the clause does require, keyed on the recorded classification."""
    _seed_plan(held=True)

    with pytest.raises(PlanDispositionRefusedError):
        _close(repo=tmp_path)

    assert make_beads_client(config=_config()).show_issue(issue_id=_CHILD)["status"] != "closed"


def test_a_plan_child_held_by_the_spec_change_tier_refuses_reparenting(tmp_path: Path) -> None:
    """Both disposition verbs, because either one would move the held child."""
    _seed_plan(held=True)
    _issue(issue_id="bd-ib-other", issue_type="epic")

    with pytest.raises(PlanDispositionRefusedError):
        reparent_plan_child(
            config=_config(repo=tmp_path),
            epic_id=_EPIC,
            child_id=_CHILD,
            new_parent_id="bd-ib-other",
            rationale="belongs elsewhere",
            author=_AUTHOR,
            now=_NOW,
        )


def test_a_child_whose_linked_topic_has_ratified_is_disposable(tmp_path: Path) -> None:
    """A released child is an implementation follow-up like any other."""
    _seed_plan(held=True)
    directory = tmp_path / "SPECIFICATION" / "history" / "v205" / "proposed_changes"
    directory.mkdir(parents=True)
    _ = (directory / f"{_TOPIC}-revision.md").write_text(
        f"---\nproposal: {_TOPIC}.md\ndecision: accept\n---\n", encoding="utf-8"
    )

    _close(repo=tmp_path)

    assert make_beads_client(config=_config()).show_issue(issue_id=_CHILD)["status"] == "closed"


def test_a_child_carrying_no_classification_at_all_is_disposable(tmp_path: Path) -> None:
    """The control: the ordinary plan child, which the deadlock used to catch."""
    _seed_plan()

    _close(repo=tmp_path)

    assert make_beads_client(config=_config()).show_issue(issue_id=_CHILD)["status"] == "closed"
