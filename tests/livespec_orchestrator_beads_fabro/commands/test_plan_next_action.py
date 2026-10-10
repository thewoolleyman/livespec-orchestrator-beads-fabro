"""Typed `next_action` metadata is the resume authority, not a handoff marker line."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from livespec_orchestrator_beads_fabro._beads_client import (
    FakeBeadsClient,
    IssueDraft,
    make_beads_client,
    reset_fake_singleton,
)
from livespec_orchestrator_beads_fabro.commands import _plan_next_action
from livespec_orchestrator_beads_fabro.commands._plan_next_action import (
    LAST_SESSION_METADATA_KEY,
    NEXT_ACTION_KINDS,
    NEXT_ACTION_METADATA_KEY,
    NextAction,
    dispatchable_action_id,
    next_action_metadata,
    parse_next_action,
    read_next_action,
    resume_directive,
    set_next_action,
)
from livespec_orchestrator_beads_fabro.commands.plan import (
    append_handoff,
    append_supervisor_handoff,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig

if TYPE_CHECKING:
    import pytest

_EPIC_ID = "bd-ib-w3nwz5"


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


# A conforming plan epic description. The Definition of Done section is
# load-bearing for every test here: without it, each resume reports
# `plan-definition-of-done: missing` and an unattended one REWRITES the pointer
# to `kind: human`, so these tests would be exercising the gap path instead of
# the typed-pointer decision they are about. That path has its own module,
# `test_plan_resume_definition_of_done_gap.py`.
_SEEDED_DESCRIPTION = (
    "Plan anchor for plan/console-control-plane-primitives.\n"
    "\n"
    "## Definition of Done\n"
    "\n"
    "- The console serves the control-plane primitives an operator reaches.\n"
)


def _seed_epic(*, epic_id: str = _EPIC_ID) -> None:
    reset_fake_singleton()
    _ = _fake().create_issue(
        draft=IssueDraft(
            issue_id=epic_id,
            issue_type="epic",
            title="plan",
            description=_SEEDED_DESCRIPTION,
            assignee=None,
            created_at="2026-09-04T00:00:00Z",
            metadata={"rank": "a1", "plan_slug": "console-control-plane-primitives"},
            labels=["origin:freeform"],
        )
    )


def _epic_metadata(*, epic_id: str = _EPIC_ID) -> dict[str, Any]:
    metadata = _fake().show_issue(issue_id=epic_id)["metadata"]
    assert isinstance(metadata, dict)
    return metadata


def _impl_action() -> NextAction:
    return NextAction(
        kind="impl",
        ref="bd-ib-w3nwz5.1",
        text="Dispatch b1 through the factory.",
    )


_RESULT = {
    "repo": "repo",
    "item_status": {"item_id": _EPIC_ID, "status": "closed"},
}
_BUDGET = {
    "deadline": "2099-09-04T18:00:00Z",
    "max_handoffs": 3,
    "epoch": "epoch-1",
    "handoff_count": 1,
}


def _tracked_action(*, kind: str, ref: str) -> NextAction:
    return NextAction(
        kind=kind,
        ref=ref,
        text="Take the recorded plan action.",
        required_result=_RESULT,
        budget=_BUDGET,
    )


def _assert_all_tracked_kinds_write_five_key_pointers() -> None:
    for kind, ref in (
        ("impl", "bd-ib-w3nwz5.1"),
        ("spec-op", "propose-change:typed-next-action"),
        ("proof", f"capture:{_EPIC_ID}"),
        ("proof", f"verify:{_EPIC_ID}"),
        ("review", _EPIC_ID),
        ("archive", _EPIC_ID),
        ("await", "run:run-1"),
        ("await", "gate:gate-1"),
        ("await", "item:bd-ib-w3nwz5.1"),
        ("await", f"epic:{_EPIC_ID}"),
    ):
        action = _tracked_action(kind=kind, ref=ref)
        assert (
            set_next_action(
                config=_config(),
                epic_id=_EPIC_ID,
                action=action,
                session="tracked-writer",
                now="2026-09-04T18:00:00Z",
            )
            is None
        )
        assert read_next_action(config=_config(), epic_id=_EPIC_ID) == action
        pointer = _epic_metadata()[NEXT_ACTION_METADATA_KEY]
        assert sorted(pointer) == ["budget", "kind", "ref", "required_result", "text"]
    for action in (
        NextAction(
            kind="human",
            ref="attention-item",
            text="Ask the maintainer.",
            required_result=None,
            budget=None,
        ),
        NextAction(
            kind="none",
            ref="",
            text="The plan has no remaining action.",
            required_result=None,
            budget=None,
        ),
    ):
        assert (
            set_next_action(
                config=_config(),
                epic_id=_EPIC_ID,
                action=action,
                session="tracked-writer",
                now="2026-09-04T18:00:00Z",
            )
            is None
        )
        assert read_next_action(config=_config(), epic_id=_EPIC_ID) == action
        pointer = _epic_metadata()[NEXT_ACTION_METADATA_KEY]
        assert sorted(pointer) == ["budget", "kind", "ref", "required_result", "text"]


def _assert_handoff_writers_accept_tracked_actions() -> None:
    proof = _tracked_action(kind="proof", ref=f"capture:{_EPIC_ID}")
    assert (
        append_handoff(
            config=_config(),
            epic_id=_EPIC_ID,
            body="Capture plan proof.",
            author="plan-session",
            now="2026-09-04T18:01:00Z",
            next_action=proof,
        )
        is None
    )
    review = _tracked_action(kind="review", ref=_EPIC_ID)
    assert (
        append_supervisor_handoff(
            config=_config(),
            epic_id=_EPIC_ID,
            slug="console-control-plane-primitives",
            body="Commission the completeness review.",
            now="2026-09-04T18:02:00Z",
            next_action=review,
        )
        is None
    )
    assert read_next_action(config=_config(), epic_id=_EPIC_ID) == review


def _invalid_tracked_actions() -> tuple[NextAction, ...]:
    return (
        _tracked_action(kind="surprise", ref="bd-ib-w3nwz5.1"),
        _tracked_action(kind="impl", ref=""),
        _tracked_action(kind="spec-op", ref="propose-change"),
        _tracked_action(kind="proof", ref=f"capture:wrong-{_EPIC_ID}"),
        _tracked_action(kind="review", ref="bd-ib-other"),
        _tracked_action(kind="archive", ref="bd-ib-other"),
        _tracked_action(kind="await", ref="timer:one-hour"),
        _tracked_action(kind="await", ref="run:"),
        NextAction(
            kind="proof",
            ref=f"capture:{_EPIC_ID}",
            text="Capture proof without tracking.",
        ),
        NextAction(
            kind="await",
            ref="run:run-1",
            text="Wait for the run.",
            required_result={},
            budget=_BUDGET,
        ),
        NextAction(
            kind="impl",
            ref="bd-ib-w3nwz5.1",
            text="Dispatch it.",
            required_result=_RESULT,
        ),
        NextAction(
            kind="impl",
            ref="bd-ib-w3nwz5.1",
            text="Dispatch it.",
            required_result=_RESULT,
            budget="tomorrow",
        ),
        NextAction(
            kind="impl",
            ref="bd-ib-w3nwz5.1",
            text="Dispatch it.",
            required_result=_RESULT,
            budget={**_BUDGET, "deadline": 1},
        ),
        NextAction(
            kind="impl",
            ref="bd-ib-w3nwz5.1",
            text="Dispatch it.",
            required_result=_RESULT,
            budget={**_BUDGET, "deadline": "tomorrow"},
        ),
        NextAction(
            kind="impl",
            ref="bd-ib-w3nwz5.1",
            text="Dispatch it.",
            required_result=_RESULT,
            budget={**_BUDGET, "deadline": "2099-09-04T18:00:00"},
        ),
        NextAction(
            kind="impl",
            ref="bd-ib-w3nwz5.1",
            text="Dispatch it.",
            required_result=_RESULT,
            budget={**_BUDGET, "deadline": "2099-09-04T19:00:00+01:00"},
        ),
        NextAction(
            kind="impl",
            ref="bd-ib-w3nwz5.1",
            text="Dispatch it.",
            required_result=_RESULT,
            budget={**_BUDGET, "max_handoffs": True},
        ),
        NextAction(
            kind="impl",
            ref="bd-ib-w3nwz5.1",
            text="Dispatch it.",
            required_result=_RESULT,
            budget={**_BUDGET, "max_handoffs": "3"},
        ),
        NextAction(
            kind="impl",
            ref="bd-ib-w3nwz5.1",
            text="Dispatch it.",
            required_result=_RESULT,
            budget={**_BUDGET, "max_handoffs": 0},
        ),
        NextAction(
            kind="human",
            ref="attention-item",
            text="Ask the maintainer.",
            required_result=_RESULT,
            budget=_BUDGET,
        ),
        NextAction(
            kind="none",
            ref="not-empty",
            text="Record no next step.",
            required_result=None,
            budget=None,
        ),
    )


def _assert_invalid_writes_are_refused_without_mutation() -> None:
    baseline = dict(_epic_metadata())
    for action in _invalid_tracked_actions():
        refused = set_next_action(
            config=_config(),
            epic_id=_EPIC_ID,
            action=action,
            session="refused-writer",
            now="2026-09-04T18:03:00Z",
        )
        assert hasattr(_plan_next_action, "NextActionRefusal")
        refusal_type = _plan_next_action.__dict__["NextActionRefusal"]
        assert isinstance(refused, refusal_type)
        assert _epic_metadata() == baseline
    one_tracking_field = {
        "kind": "impl",
        "ref": "bd-ib-w3nwz5.1",
        "text": "Dispatch it.",
        "required_result": _RESULT,
    }
    assert parse_next_action(value=one_tracking_field) is None


def test_set_next_action_writes_the_typed_pointer_and_last_session() -> None:
    _seed_epic()

    set_next_action(
        config=_config(),
        epic_id=_EPIC_ID,
        action=_impl_action(),
        session="console-control-plane-primitives",
        now="2026-09-04T18:00:00Z",
    )

    metadata = _epic_metadata()
    assert metadata[NEXT_ACTION_METADATA_KEY] == {
        "kind": "impl",
        "ref": "bd-ib-w3nwz5.1",
        "text": "Dispatch b1 through the factory.",
    }
    assert metadata[LAST_SESSION_METADATA_KEY] == (
        "console-control-plane-primitives at 2026-09-04T18:00:00Z"
    )


def test_set_next_action_updates_in_place_and_preserves_other_metadata() -> None:
    _seed_epic()
    set_next_action(
        config=_config(),
        epic_id=_EPIC_ID,
        action=_impl_action(),
        session="first-session",
        now="2026-09-04T18:00:00Z",
    )

    set_next_action(
        config=_config(),
        epic_id=_EPIC_ID,
        action=NextAction(kind="none", ref="", text="Nothing is recorded."),
        session="second-session",
        now="2026-09-04T19:00:00Z",
    )

    metadata = _epic_metadata()
    assert metadata[NEXT_ACTION_METADATA_KEY] == {
        "kind": "none",
        "ref": "",
        "text": "Nothing is recorded.",
    }
    assert metadata[LAST_SESSION_METADATA_KEY] == "second-session at 2026-09-04T19:00:00Z"
    assert metadata["rank"] == "a1"
    assert metadata["plan_slug"] == "console-control-plane-primitives"


def test_read_next_action_round_trips_the_typed_pointer() -> None:
    _seed_epic()
    set_next_action(
        config=_config(),
        epic_id=_EPIC_ID,
        action=_impl_action(),
        session="console-control-plane-primitives",
        now="2026-09-04T18:00:00Z",
    )

    assert read_next_action(config=_config(), epic_id=_EPIC_ID) == _impl_action()


def test_read_next_action_reports_an_epic_that_carries_none() -> None:
    _seed_epic()

    assert read_next_action(config=_config(), epic_id=_EPIC_ID) is None


def test_next_action_metadata_overlays_all_three_keys_onto_existing_metadata() -> None:
    overlaid = next_action_metadata(
        existing_metadata={"rank": "a1", "audit": {"captured_at": "2026-09-04T00:00:00Z"}},
        action=_impl_action(),
        session="console-control-plane-primitives",
        now="2026-09-04T18:00:00Z",
    )

    assert sorted(overlaid[NEXT_ACTION_METADATA_KEY]) == ["kind", "ref", "text"]
    assert overlaid["audit"] == {"captured_at": "2026-09-04T00:00:00Z"}


def test_parse_next_action_accepts_a_well_typed_value() -> None:
    parsed = parse_next_action(
        value={"kind": "spec-op", "ref": "propose-change:typed-next-action", "text": "Propose it."}
    )

    assert parsed == NextAction(
        kind="spec-op",
        ref="propose-change:typed-next-action",
        text="Propose it.",
    )


def test_parse_next_action_rejects_an_absent_or_ill_typed_value() -> None:
    assert parse_next_action(value=None) is None
    assert parse_next_action(value="impl:bd-ib-w3nwz5.1") is None
    assert parse_next_action(value={"ref": "bd-ib-w3nwz5.1", "text": "Dispatch."}) is None
    assert parse_next_action(value={"kind": "impl", "text": "Dispatch."}) is None
    assert parse_next_action(value={"kind": "impl", "ref": "bd-ib-w3nwz5.1"}) is None
    assert parse_next_action(value={"kind": 1, "ref": "x", "text": "y"}) is None


def test_the_eight_kinds_and_all_writers_enforce_the_tracked_pointer_contract() -> None:
    assert NEXT_ACTION_KINDS == (
        "impl",
        "spec-op",
        "proof",
        "review",
        "archive",
        "await",
        "human",
        "none",
    )
    _seed_epic()
    _assert_all_tracked_kinds_write_five_key_pointers()
    _assert_handoff_writers_accept_tracked_actions()
    _assert_invalid_writes_are_refused_without_mutation()


def test_dispatchable_action_id_composes_the_drive_action_for_impl() -> None:
    assert dispatchable_action_id(action=_impl_action()) == "impl:bd-ib-w3nwz5.1"


def test_dispatchable_action_id_carries_a_spec_op_ref_through_unchanged() -> None:
    action = NextAction(
        kind="spec-op",
        ref="propose-change:plan-slug-anchor-and-typed-next-action",
        text="Propose the change.",
    )

    assert (
        dispatchable_action_id(action=action)
        == "propose-change:plan-slug-anchor-and-typed-next-action"
    )


def test_dispatchable_action_id_refuses_a_human_or_empty_ref_action() -> None:
    human = NextAction(kind="human", ref="", text="Confirm the anchor filename.")
    empty_ref = NextAction(kind="impl", ref="   ", text="Dispatch something.")

    assert dispatchable_action_id(action=human) is None
    assert dispatchable_action_id(action=empty_ref) is None


def test_unattended_resume_takes_an_impl_next_action_without_asking() -> None:
    _seed_epic()
    set_next_action(
        config=_config(),
        epic_id=_EPIC_ID,
        action=_impl_action(),
        session="console-control-plane-primitives",
        now="2026-09-04T18:00:00Z",
    )

    directive = resume_directive(config=_config(), epic_id=_EPIC_ID, unattended=True)

    assert not directive.ask
    assert directive.next_action == "impl:bd-ib-w3nwz5.1"
    assert directive.reason == "unattended resume takes the typed next_action"


def test_unattended_resume_takes_a_spec_op_next_action_without_asking() -> None:
    _seed_epic()
    set_next_action(
        config=_config(),
        epic_id=_EPIC_ID,
        action=NextAction(
            kind="spec-op",
            ref="propose-change:plan-slug-anchor-and-typed-next-action",
            text="Propose the change.",
        ),
        session="console-control-plane-primitives",
        now="2026-09-04T18:00:00Z",
    )

    directive = resume_directive(config=_config(), epic_id=_EPIC_ID, unattended=True)

    assert not directive.ask
    assert directive.next_action == "propose-change:plan-slug-anchor-and-typed-next-action"


def test_unattended_resume_raises_the_picker_for_a_human_next_action() -> None:
    _seed_epic()
    set_next_action(
        config=_config(),
        epic_id=_EPIC_ID,
        action=NextAction(kind="human", ref="", text="Confirm the anchor filename."),
        session="console-control-plane-primitives",
        now="2026-09-04T18:00:00Z",
    )

    directive = resume_directive(config=_config(), epic_id=_EPIC_ID, unattended=True)

    assert directive.ask
    assert directive.next_action is None
    assert directive.reason == "next_action kind human raises the picker"


def test_unattended_resume_raises_the_picker_for_a_none_next_action() -> None:
    _seed_epic()
    set_next_action(
        config=_config(),
        epic_id=_EPIC_ID,
        action=NextAction(kind="none", ref="", text="Nothing is recorded."),
        session="console-control-plane-primitives",
        now="2026-09-04T18:00:00Z",
    )

    directive = resume_directive(config=_config(), epic_id=_EPIC_ID, unattended=True)

    assert directive.ask
    assert directive.reason == "next_action kind none raises the picker"


def test_unattended_resume_raises_the_picker_for_a_dispatchable_kind_with_no_ref() -> None:
    _seed_epic()
    set_next_action(
        config=_config(),
        epic_id=_EPIC_ID,
        action=NextAction(kind="impl", ref="", text="Dispatch something."),
        session="console-control-plane-primitives",
        now="2026-09-04T18:00:00Z",
    )

    directive = resume_directive(config=_config(), epic_id=_EPIC_ID, unattended=True)

    assert directive.ask
    assert directive.reason == "next_action kind impl carries an empty ref"


def test_unattended_resume_raises_the_picker_when_the_epic_carries_no_pointer() -> None:
    _seed_epic()

    directive = resume_directive(config=_config(), epic_id=_EPIC_ID, unattended=True)

    assert directive.ask
    assert directive.next_action is None
    assert directive.reason == f"epic {_EPIC_ID} carries no typed next_action"


def test_an_attended_resume_always_asks() -> None:
    _seed_epic()
    set_next_action(
        config=_config(),
        epic_id=_EPIC_ID,
        action=_impl_action(),
        session="console-control-plane-primitives",
        now="2026-09-04T18:00:00Z",
    )

    directive = resume_directive(config=_config(), epic_id=_EPIC_ID, unattended=False)

    assert directive.ask
    assert directive.next_action is None
    assert directive.reason == "interactive resume"


def test_a_wrapped_prose_marker_line_no_longer_decides_the_resume() -> None:
    _seed_epic()
    _fake().seed_comment(
        issue_id=_EPIC_ID,
        text=(
            "plan-handoff-entry\nauthor: console\ntimestamp: 2026-09-04T18:00:00Z\n\n"
            "Next action: implement overseer-adclcd.6 through the\nfactory, without the\n"
        ),
        author="console",
        created_at="2026-09-04T18:00:00Z",
    )
    set_next_action(
        config=_config(),
        epic_id=_EPIC_ID,
        action=NextAction(kind="impl", ref="overseer-adclcd.6", text="Dispatch it."),
        session="console",
        now="2026-09-04T18:00:00Z",
    )

    directive = resume_directive(config=_config(), epic_id=_EPIC_ID, unattended=True)

    assert directive.next_action == "impl:overseer-adclcd.6"


def test_a_metadata_less_record_reads_as_no_pointer_rather_than_raising(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_epic()

    class _SparseClient:
        def show_issue(self, *, issue_id: str) -> dict[str, Any]:
            return {"id": issue_id, "issue_type": "epic"}

        def update_issue(self, *, issue_id: str, metadata: dict[str, Any]) -> None:
            self.written = (issue_id, metadata)

    sparse = _SparseClient()

    def _sparse_client(*, config: StoreConfig) -> _SparseClient:
        assert config.fake
        return sparse

    monkeypatch.setattr(_plan_next_action, "make_beads_client", _sparse_client)

    assert read_next_action(config=_config(), epic_id=_EPIC_ID) is None
    set_next_action(
        config=_config(),
        epic_id=_EPIC_ID,
        action=_impl_action(),
        session="console",
        now="2026-09-04T18:00:00Z",
    )

    assert sparse.written[1][NEXT_ACTION_METADATA_KEY]["ref"] == "bd-ib-w3nwz5.1"
