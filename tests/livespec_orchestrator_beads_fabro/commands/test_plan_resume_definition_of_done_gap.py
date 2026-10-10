"""Every plan resume reports a missing Definition of Done section.

Per the plan Definition-of-Done clause of `SPECIFICATION/contracts.md` (v115): a
plan epic lacking the section — one created before the clause was ratified — MUST
be reported by EVERY plan resume as `plan-definition-of-done: missing`. An
unattended resume MUST NOT author assertions on the maintainer's behalf: it sets
`next_action` to `kind: human` naming the gap, UNLESS the existing `next_action`
is `kind: impl`, which it still takes.

The `impl` carve-out is the load-bearing half. Without it, an unattended resume
of a legacy plan would overwrite a live dispatch pointer with a question nobody
is there to answer — stalling the plan the clause was meant to help.
"""

from __future__ import annotations

from dataclasses import fields

from livespec_orchestrator_beads_fabro._beads_client import (
    FakeBeadsClient,
    IssueDraft,
    make_beads_client,
    reset_fake_singleton,
)
from livespec_orchestrator_beads_fabro.commands._plan_next_action import (
    NEXT_ACTION_METADATA_KEY,
    NextAction,
    ResumeDirective,
    read_next_action,
    resume_directive,
    set_next_action,
)
from livespec_orchestrator_beads_fabro.types import StoreConfig

_EPIC_ID = "bd-ib-legacy"
_MISSING_FINDING = "plan-definition-of-done: missing"
_RESULT = {
    "repo": "livespec-orchestrator-beads-fabro",
    "item_status": {"item_id": _EPIC_ID, "status": "closed"},
}
_BUDGET = {"deadline": "2099-10-04T00:00:00Z", "max_handoffs": 3}
_SECTION = (
    "Plan anchor for plan/herdr-release.\n"
    "\n"
    "## Definition of Done\n"
    "\n"
    "- The released overseer runs in a real herdr session.\n"
)


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


def _seed_epic(*, description: str) -> None:
    reset_fake_singleton()
    _ = _fake().create_issue(
        draft=IssueDraft(
            issue_id=_EPIC_ID,
            issue_type="epic",
            title="A plan filed before the clause was ratified",
            description=description,
            assignee=None,
            created_at="2026-10-04T00:00:00Z",
            metadata={"rank": "a1", "plan_slug": "herdr-release"},
            labels=["origin:freeform"],
        )
    )


def test_an_attended_resume_of_a_sectionless_epic_reports_the_gap() -> None:
    """ "EVERY plan resume" includes the attended one, which asks regardless."""
    # The directive has to be able to CARRY a finding before it can report one.
    assert "findings" in {one.name for one in fields(ResumeDirective)}

    _seed_epic(description="plan")

    directive = resume_directive(config=_config(), epic_id=_EPIC_ID, unattended=False)

    assert directive.ask
    assert any(one.startswith(_MISSING_FINDING) for one in directive.findings)
    # An attended resume authors the section WITH the maintainer; it writes no
    # pointer of its own, so the epic's metadata is untouched.
    assert NEXT_ACTION_METADATA_KEY not in _fake().show_issue(issue_id=_EPIC_ID).get("metadata", {})


def test_an_unattended_resume_of_a_sectionless_epic_sets_a_human_next_action() -> None:
    _seed_epic(description="plan")
    set_next_action(
        config=_config(),
        epic_id=_EPIC_ID,
        action=NextAction(
            kind="spec-op",
            ref="propose-change:herdr",
            text="Propose it.",
            required_result=_RESULT,
            budget=_BUDGET,
        ),
        session="overseerd",
        now="2026-10-04T00:00:00Z",
    )

    directive = resume_directive(config=_config(), epic_id=_EPIC_ID, unattended=True)

    assert directive.ask
    assert directive.next_action is None
    assert any(one.startswith(_MISSING_FINDING) for one in directive.findings)
    # The pointer was REWRITTEN to kind human, naming the gap. A `spec-op` is not
    # the carve-out: only `impl` survives.
    written = read_next_action(config=_config(), epic_id=_EPIC_ID)
    assert written is not None
    assert written.kind == "human"
    assert "Definition of Done" in written.text


def test_an_unattended_resume_still_takes_an_impl_next_action_despite_the_gap() -> None:
    """The carve-out: a live dispatch pointer is NOT overwritten by the gap."""
    _seed_epic(description="plan")
    impl = NextAction(
        kind="impl",
        ref="bd-ib-child",
        text="Dispatch bd-ib-child.",
        required_result=_RESULT,
        budget=_BUDGET,
    )
    set_next_action(
        config=_config(),
        epic_id=_EPIC_ID,
        action=impl,
        session="overseerd",
        now="2026-10-04T00:00:00Z",
    )

    directive = resume_directive(config=_config(), epic_id=_EPIC_ID, unattended=True)

    assert not directive.ask
    assert directive.next_action == "impl:bd-ib-child"
    # The gap is still REPORTED — reported and acted on are different things.
    assert any(one.startswith(_MISSING_FINDING) for one in directive.findings)
    assert read_next_action(config=_config(), epic_id=_EPIC_ID) == impl


def test_an_epic_carrying_the_section_reports_no_finding() -> None:
    """The control. Without it, a finding hard-coded to fire would pass every case."""
    _seed_epic(description=_SECTION)
    set_next_action(
        config=_config(),
        epic_id=_EPIC_ID,
        action=NextAction(
            kind="human",
            ref="",
            text="Confirm the slug.",
            required_result=None,
            budget=None,
        ),
        session="overseerd",
        now="2026-10-04T00:00:00Z",
    )

    directive = resume_directive(config=_config(), epic_id=_EPIC_ID, unattended=True)

    assert directive.findings == ()
    # And the ordinary typed-pointer behaviour is untouched: a `human` pointer
    # raises the picker with its own reason, not the gap's.
    assert directive.ask
    assert directive.reason == "next_action kind human raises the picker"
    assert read_next_action(config=_config(), epic_id=_EPIC_ID) == NextAction(
        kind="human",
        ref="",
        text="Confirm the slug.",
        required_result=None,
        budget=None,
    )
