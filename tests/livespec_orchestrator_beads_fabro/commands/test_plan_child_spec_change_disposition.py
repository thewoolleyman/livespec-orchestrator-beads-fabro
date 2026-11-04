"""Plan-child disposition reads the RECORDED tier, and fails closed without one.

Assertion 6 of `bd-ib-57ss2n`: "Plan-child disposition refuses a held
spec-change-tier child and admits an implementation follow-up." Its clause is
the plan-child-disposition bullet of `SPECIFICATION/constraints.md`, which
states the discriminator and the failure direction outright: the tier "MUST NOT
be read off `spec_commitment_hint`", it is "DECIDED by the spec-stated judgement
and recorded on the item at classification", and "An implementation MUST fail
CLOSED: where it cannot determine a child's autonomy tier from that recorded
classification, it MUST refuse the disposition and surface it".

FOUR CASES, AND EACH IS ANOTHER'S CONTROL, because the clause says the hint
"gates the wrong set in both directions":

- a child whose recorded classification is spec-change tier, HELD, refuses;
- a child whose recorded classification is spec-change tier whose topic has
  RATIFIED and been re-judged `stated` — a record reading tier `none` — is
  admitted, which is the implementation follow-up the clause names;
- a HINT-CARRYING child with a `none` record is admitted, which is the
  direction the retired predicate got wrong: a non-null
  `spec_commitment_hint` marks a follow-up to an ALREADY-RATIFIED change;
- a child with NO recorded classification is REFUSED, which is the fail-closed
  direction and the one a build is most likely to get backwards, because
  refusing an admissible disposition costs one escalation while admitting an
  inadmissible one silently disposes of a spec-change slice.

The first two are the pair that makes the module discriminating: a build still
reading the hint satisfies neither, and a build that had simply stopped reading
anything satisfies the second and third while admitting the first.
"""

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
from livespec_orchestrator_beads_fabro.commands._spec_change_tier import (
    decide_spec_change_tier,
    exempt_decision,
)
from livespec_orchestrator_beads_fabro.commands._spec_change_tier_record import (
    STAGE_FILING,
    spec_change_tier_comment,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem
from livespec_runtime.spec_stated import SpecStatedVerdict

_EPIC = "bd-ib-epic"
_CHILD = "bd-ib-child"
_AUTHOR = "role:plan-session"
_NOW = "2026-10-23T00:00:00Z"
_HEADING = "## A governing clause"
_HINT = "spec:contracts-dispatcher-admission"


@pytest.fixture(autouse=True)
def _fake_beads_env(monkeypatch: pytest.MonkeyPatch) -> object:
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    reset_fake_singleton()
    yield
    reset_fake_singleton()


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="bd-ib",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=True,
    )


def _item() -> WorkItem:
    return WorkItem(
        id=_CHILD,
        type="task",
        status="ready",
        title="A plan child",
        description="Some work under the plan.",
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee=None,
        depends_on=(),
        captured_at="2026-10-15T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
    )


def _held_record() -> str:
    return spec_change_tier_comment(
        item_id=_CHILD,
        stage=STAGE_FILING,
        decision=decide_spec_change_tier(
            item=_item(),
            classification="feature",
            verdict=SpecStatedVerdict(
                kind="unstated",
                stated_by=(),
                generalization_target=_HEADING,
                rationale="the ratified text does not state it",
            ),
        ),
        spec_version="1",
        digest="a-digest",
    )


def _released_record() -> str:
    return spec_change_tier_comment(
        item_id=_CHILD,
        stage=STAGE_FILING,
        decision=decide_spec_change_tier(
            item=_item(),
            classification="feature",
            verdict=SpecStatedVerdict(
                kind="stated",
                stated_by=(_HEADING,),
                generalization_target=None,
                rationale="the clause states it",
            ),
        ),
        spec_version="2",
        digest="a-digest",
    )


def _exempt_record() -> str:
    return spec_change_tier_comment(
        item_id=_CHILD,
        stage=STAGE_FILING,
        decision=exempt_decision(classification="bug"),
        spec_version="1",
        digest="a-digest",
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


def _seed(*, record: str | None, hint: str | None = None) -> None:
    _issue(issue_id=_EPIC, issue_type="epic")
    _issue(issue_id="bd-ib-other", issue_type="epic")
    _issue(issue_id=_CHILD, issue_type="task", spec_id=hint)
    _fake().add_dependency(from_id=_CHILD, to_id=_EPIC, edge_type=EDGE_PARENT_CHILD)
    if record is not None:
        _fake().add_comment(issue_id=_CHILD, body=record)


def _status() -> str:
    return str(_fake().show_issue(issue_id=_CHILD)["status"])


def _edges() -> list[dict[str, object]]:
    return list(_fake().show_issue(issue_id=_CHILD)["dependencies"])  # pyright: ignore[reportArgumentType]


def test_a_held_spec_change_tier_child_refuses_closure_and_reparenting() -> None:
    _seed(record=_held_record())

    with pytest.raises(PlanDispositionRefusedError) as closure:
        close_plan_child(
            config=_config(),
            epic_id=_EPIC,
            child_id=_CHILD,
            rationale="Tidying the epic.",
            author=_AUTHOR,
            now=_NOW,
        )
    assert _CHILD in str(closure.value)
    assert _status() != "closed"

    with pytest.raises(PlanDispositionRefusedError):
        reparent_plan_child(
            config=_config(),
            epic_id=_EPIC,
            child_id=_CHILD,
            new_parent_id="bd-ib-other",
            rationale="Tidying the epic.",
            author=_AUTHOR,
            now=_NOW,
        )
    assert {"depends_on_id": _EPIC, "type": EDGE_PARENT_CHILD} in _edges()


def test_a_released_follow_up_is_admitted() -> None:
    _seed(record=_released_record())

    close_plan_child(
        config=_config(),
        epic_id=_EPIC,
        child_id=_CHILD,
        rationale="The follow-up moved elsewhere.",
        author=_AUTHOR,
        now=_NOW,
    )
    assert _status() == "closed"


def test_a_hint_carrying_child_whose_record_releases_it_is_admitted() -> None:
    """The direction the retired predicate got wrong: a hint is not the tier."""
    _seed(record=_exempt_record(), hint=_HINT)

    close_plan_child(
        config=_config(),
        epic_id=_EPIC,
        child_id=_CHILD,
        rationale="A bug, disposed of by the plan session.",
        author=_AUTHOR,
        now=_NOW,
    )
    assert _status() == "closed"


def test_a_child_with_no_recorded_classification_is_refused() -> None:
    """Fail CLOSED: an undeterminable tier refuses rather than being guessed."""
    _seed(record=None)

    with pytest.raises(PlanDispositionRefusedError) as refusal:
        close_plan_child(
            config=_config(),
            epic_id=_EPIC,
            child_id=_CHILD,
            rationale="Tidying the epic.",
            author=_AUTHOR,
            now=_NOW,
        )
    assert _CHILD in str(refusal.value)
    assert "no recorded" in str(refusal.value)
    assert _status() != "closed"
