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
from livespec_orchestrator_beads_fabro.commands._plan_disposition import (
    PlanDispositionRefusedError,
    close_plan_child,
    reparent_plan_child,
)
from livespec_orchestrator_beads_fabro.commands._spec_change_tier import exempt_decision
from livespec_orchestrator_beads_fabro.commands._spec_change_tier_record import (
    STAGE_FILING,
    spec_change_tier_comment,
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


def _seed_plan(*, spec_id: str | None = None, classified: bool = True) -> None:
    """Seed the plan, with a RECORDED classification unless a case withholds one.

    The disposition reads the recorded spec-change-tier classification and fails
    CLOSED without one, which the plan-child-disposition clause of
    `SPECIFICATION/constraints.md` requires: "where it cannot determine a child's
    autonomy tier from that recorded classification, it MUST refuse the
    disposition". So every case about the ordinary disposition has to seed one,
    and `classified=False` is how the one case about the absence withholds it.

    The record is an EXEMPT classification — a `bug`, tier `none` — because these
    cases are about the disposition rather than about the tier. The tier's own
    cases live in `test_plan_child_spec_change_disposition.py`.
    """
    reset_fake_singleton()
    _issue(issue_id="bd-ib-epic", issue_type="epic")
    _issue(issue_id="bd-ib-other", issue_type="epic")
    _issue(issue_id="bd-ib-child", issue_type="task", spec_id=spec_id)
    _fake().add_dependency(from_id="bd-ib-child", to_id="bd-ib-epic", edge_type=EDGE_PARENT_CHILD)
    if classified:
        _fake().add_comment(
            issue_id="bd-ib-child",
            body=spec_change_tier_comment(
                item_id="bd-ib-child",
                stage=STAGE_FILING,
                decision=exempt_decision(classification="bug"),
                spec_version="1",
                digest="a-digest",
            ),
        )


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


def test_an_unclassified_child_refuses_closure_and_records_nothing() -> None:
    """Fail CLOSED: a tier nothing has determined refuses rather than being guessed.

    This pair replaces two cases that asserted the RETIRED reading — a refusal
    keyed on `spec_commitment_hint`, which the plan-child-disposition clause of
    `SPECIFICATION/constraints.md` names as gating "the wrong set in both
    directions". The tier's own four cases, including the hint-carrying follow-up
    the retired predicate refused, live in
    `test_plan_child_spec_change_disposition.py`; what is left here is the
    absence, which is this module's own subject.

    The rationale comment is asserted ABSENT as well as the status unchanged,
    because the rationale is written BEFORE the mutation — so a refusal that
    fired after it would leave an explained intent for a disposition that never
    happened.
    """
    _seed_plan(classified=False)

    with pytest.raises(PlanDispositionRefusedError) as refusal:
        close_plan_child(
            config=_config(),
            epic_id="bd-ib-epic",
            child_id="bd-ib-child",
            rationale="Tidying the epic.",
            author=_AUTHOR,
            now=_NOW,
        )

    assert "bd-ib-child" in str(refusal.value)
    assert "no recorded" in str(refusal.value)
    assert _fake().show_issue(issue_id="bd-ib-child")["status"] != "closed"
    assert _comment_bodies(issue_id="bd-ib-child") == []


def test_an_unclassified_child_refuses_reparenting() -> None:
    _seed_plan(classified=False)

    with pytest.raises(PlanDispositionRefusedError):
        reparent_plan_child(
            config=_config(),
            epic_id="bd-ib-epic",
            child_id="bd-ib-child",
            new_parent_id="bd-ib-other",
            rationale="Tidying the epic.",
            author=_AUTHOR,
            now=_NOW,
        )

    edges = _fake().show_issue(issue_id="bd-ib-child")["dependencies"]
    assert {"depends_on_id": "bd-ib-epic", "type": EDGE_PARENT_CHILD} in edges


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


def test_a_real_spec_clause_commitment_no_longer_refuses_closure() -> None:
    """The true-positive arm this module used to carry has INVERTED, deliberately.

    It asserted that a child carrying a genuine `spec_commitment_hint` refuses,
    as "the true-positive arm" of the narrowing that distinguished a commitment
    from a plan anchor. The plan-child-disposition clause of
    `SPECIFICATION/constraints.md` now says that reading is wrong: a non-null
    hint marks an implementation FOLLOW-UP to an ALREADY-RATIFIED change, which
    is "ordinary dispatchable work whose disposition this bullet admits". So the
    commitment-carrying child is disposable here, exactly as the anchored one
    is, and both are admitted by the SAME recorded `none` classification rather
    than by anything read off that column.

    The arm that must not become a removal is still asserted, one module over:
    `test_plan_child_spec_change_disposition.py` refuses a HELD spec-change-tier
    child and refuses one whose tier cannot be determined at all.
    """
    _seed_plan(spec_id=_SPEC_CLAUSE_COMMITMENT)

    close_plan_child(
        config=_config(),
        epic_id="bd-ib-epic",
        child_id="bd-ib-child",
        rationale="A ratified follow-up, disposed of by the plan session.",
        author=_AUTHOR,
        now=_NOW,
    )

    assert _fake().show_issue(issue_id="bd-ib-child")["status"] == "closed"


def test_removing_an_absent_dependency_is_a_no_op() -> None:
    _seed_plan()

    _fake().remove_dependency(from_id="bd-ib-child", to_id="bd-ib-other")

    edges = _fake().show_issue(issue_id="bd-ib-child")["dependencies"]
    assert {"depends_on_id": "bd-ib-epic", "type": EDGE_PARENT_CHILD} in edges
