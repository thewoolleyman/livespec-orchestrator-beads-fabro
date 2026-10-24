"""A session disposes a plan child itself, and refuses only the spec-change tier."""

from __future__ import annotations

import pytest
from livespec_orchestrator_beads_fabro._beads_client import (
    EDGE_PARENT_CHILD,
    FakeBeadsClient,
    IssueDraft,
    make_beads_client,
    reset_fake_singleton,
)
from livespec_orchestrator_beads_fabro.commands import _plan_disposition
from livespec_orchestrator_beads_fabro.commands._plan_disposition import (
    close_plan_child,
    reparent_plan_child,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig

_NOW = "2026-08-20T00:00:00Z"
_AUTHOR = "unattended-plan-operation-plan"

# The two values that share the `spec_id` column and must NOT be treated
# alike. The commitment fixture is purpose-built to be the shape the Spec
# Reader parses out of proposed-change front-matter — a bare obligation
# slug — so the refusal it triggers is the refusal this guard is for.
_SPEC_CLAUSE_COMMITMENT = "contracts-dispatcher-admission"
_PLAN_ANCHOR_MARKER = "plan:codex-yolo-sandbox"


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


def _issue(*, issue_id: str, issue_type: str, spec_id: str | None = None) -> None:
    _ = _fake().create_issue(
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


def _seed_plan(*, spec_id: str | None = None) -> None:
    reset_fake_singleton()
    _issue(issue_id="bd-ib-epic", issue_type="epic")
    _issue(issue_id="bd-ib-other", issue_type="epic")
    _issue(issue_id="bd-ib-child", issue_type="task", spec_id=spec_id)
    _fake().add_dependency(from_id="bd-ib-child", to_id="bd-ib-epic", edge_type=EDGE_PARENT_CHILD)


def _comment_bodies(*, issue_id: str) -> list[str]:
    return [str(comment["text"]) for comment in _fake().list_comments(issue_id=issue_id)]


def test_closing_a_plan_child_needs_no_human_valve_and_records_the_rationale() -> None:
    _seed_plan()

    close_plan_child(
        config=_config(),
        epic_id="bd-ib-epic",
        child_id="bd-ib-child",
        rationale="Superseded by the scope event; the work moved into bd-ib-epic.2.",
        author=_AUTHOR,
        now=_NOW,
    )

    assert _fake().show_issue(issue_id="bd-ib-child")["status"] == "closed"
    child_comment = "\n".join(_comment_bodies(issue_id="bd-ib-child"))
    assert "plan-child-disposition" in child_comment
    assert "closed" in child_comment
    assert "Superseded by the scope event" in child_comment
    assert "bd-ib-child" in "\n".join(_comment_bodies(issue_id="bd-ib-epic"))


def test_reparenting_a_plan_child_moves_the_edge_and_records_the_rationale() -> None:
    _seed_plan()

    reparent_plan_child(
        config=_config(),
        epic_id="bd-ib-epic",
        child_id="bd-ib-child",
        new_parent_id="bd-ib-other",
        rationale="Scope creep: this belongs to the sibling thread's epic.",
        author=_AUTHOR,
        now=_NOW,
    )

    edges = _fake().show_issue(issue_id="bd-ib-child")["dependencies"]
    assert {"depends_on_id": "bd-ib-other", "type": EDGE_PARENT_CHILD} in edges
    assert {"depends_on_id": "bd-ib-epic", "type": EDGE_PARENT_CHILD} not in edges
    assert _fake().show_issue(issue_id="bd-ib-child")["status"] != "closed"
    child_comment = "\n".join(_comment_bodies(issue_id="bd-ib-child"))
    assert "re-parented to bd-ib-other" in child_comment
    assert "Scope creep" in child_comment


def test_reparenting_leaves_an_unrelated_edge_alone() -> None:
    _seed_plan()
    _issue(issue_id="bd-ib-blocker", issue_type="task")
    _fake().add_dependency(from_id="bd-ib-child", to_id="bd-ib-blocker", edge_type="blocks")

    reparent_plan_child(
        config=_config(),
        epic_id="bd-ib-epic",
        child_id="bd-ib-child",
        new_parent_id="bd-ib-other",
        rationale="Scope creep.",
        author=_AUTHOR,
        now=_NOW,
    )

    edges = _fake().show_issue(issue_id="bd-ib-child")["dependencies"]
    assert {"depends_on_id": "bd-ib-blocker", "type": "blocks"} in edges


def _unreadable_sidecar(*, path: StoreConfig, work_item_id: str) -> tuple[str, ...] | None:
    """A comment read that could not be taken, which is not an empty one."""
    _ = (path, work_item_id)
    return None


def test_a_commitment_bearing_child_is_disposable() -> None:
    """A `spec_commitment_hint` marks a RATIFIED follow-up, never the tier.

    This case asserted the opposite until `bd-ib-yykjko`: the autonomy-tier
    bullet says the tier is "never read off `spec_commitment_hint` (which marks
    an implementation follow-up to an already ratified change)" and ends
    "Plan-child disposition ... admits an implementation follow-up", so the one
    child the old predicate refused is the one the clause names as disposable.
    The refusal that replaces it is keyed on the recorded spec-change-tier
    classification, and lives in
    `test_spec_commitment_hint_is_not_the_tier.py`.
    """
    _seed_plan(spec_id="spec:contracts-dispatcher-admission")

    close_plan_child(
        config=_config(),
        epic_id="bd-ib-epic",
        child_id="bd-ib-child",
        rationale="Tidying the epic.",
        author=_AUTHOR,
        now=_NOW,
    )

    assert _fake().show_issue(issue_id="bd-ib-child")["status"] == "closed"


def test_a_plan_anchored_child_is_disposable() -> None:
    """The negative arm: `create_thread` stamps this, and it is not a commitment."""
    _seed_plan(spec_id=_PLAN_ANCHOR_MARKER)

    close_plan_child(
        config=_config(),
        epic_id="bd-ib-epic",
        child_id="bd-ib-child",
        rationale="The plan landed; its anchor child is done.",
        author=_AUTHOR,
        now=_NOW,
    )

    assert _fake().show_issue(issue_id="bd-ib-child")["status"] == "closed"


def test_a_plan_anchored_child_is_reparentable() -> None:
    _seed_plan(spec_id=_PLAN_ANCHOR_MARKER)

    reparent_plan_child(
        config=_config(),
        epic_id="bd-ib-epic",
        child_id="bd-ib-child",
        new_parent_id="bd-ib-other",
        rationale="Scope creep: this belongs to the sibling thread's epic.",
        author=_AUTHOR,
        now=_NOW,
    )

    edges = _fake().show_issue(issue_id="bd-ib-child")["dependencies"]
    assert {"depends_on_id": "bd-ib-other", "type": EDGE_PARENT_CHILD} in edges


def test_a_real_spec_clause_commitment_is_disposable_too() -> None:
    """The bare-slug commitment shape, admitted for the same reason.

    It is kept beside the prefixed shape above because the two were the whole
    point of the retired predicate's narrowing, and the clause now admits both:
    neither spelling of a RATIFIED commitment says anything about the tier.
    """
    _seed_plan(spec_id=_SPEC_CLAUSE_COMMITMENT)

    close_plan_child(
        config=_config(),
        epic_id="bd-ib-epic",
        child_id="bd-ib-child",
        rationale="Tidying the epic.",
        author=_AUTHOR,
        now=_NOW,
    )

    assert _fake().show_issue(issue_id="bd-ib-child")["status"] == "closed"


def test_removing_an_absent_dependency_is_a_no_op() -> None:
    _seed_plan()

    _fake().remove_dependency(from_id="bd-ib-child", to_id="bd-ib-other")

    edges = _fake().show_issue(issue_id="bd-ib-child")["dependencies"]
    assert {"depends_on_id": "bd-ib-epic", "type": EDGE_PARENT_CHILD} in edges


def test_a_child_whose_comments_cannot_be_read_is_still_disposable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unreadable sidecar admits the disposition rather than refusing it.

    The recorded classification is the only thing that can establish the tier,
    so a read that could not be taken is the absence of evidence that a hold
    stands. Refusing there would reinstate the archive deadlock this module
    exists to break, on nothing but a transient ledger fault.
    """
    _seed_plan()
    monkeypatch.setattr(_plan_disposition, "item_comment_bodies", _unreadable_sidecar)

    close_plan_child(
        config=_config(),
        epic_id="bd-ib-epic",
        child_id="bd-ib-child",
        rationale="The sidecar is unreachable; the child is still ours to close.",
        author=_AUTHOR,
        now=_NOW,
    )

    assert _fake().show_issue(issue_id="bd-ib-child")["status"] == "closed"
