"""A needs-human ending with no readable failure cause SAYS the cause is absent.

Work-item `bd-ib-3nu5vv`, second assertion. The first one makes a Petri-era
routing stage's cause readable where the engine records one; this one is about
what the two surfaces owe when it records none — which, on the engine measured
today, is the ordinary case: research note 006 records "No `causes`, no
`signature`" on a Petri conclusion, and the candidate CLI renders `Error: ?`
for every failed stage of the runs this item was filed from.

THE OMISSION IS THE DEFECT, NOT THE ABSENCE. Both renderers emitted the
`innermost cause:` clause only when a cause was in hand, so a record whose
cause could not be read is BYTE-FOR-BYTE a record of an ending that had no
cause to report — and neither is distinguishable from a record written by a
build that never reported causes at all. That ambiguity is what made the
regression invisible for three runs: an operator reading `01M542TM46NS`,
`01M55WZ7DS6A` or `01M563W6CWYQ` had nothing to tell "this engine recorded
nothing" from "this reader could not read it", and the ledger comment cannot be
edited afterwards to add the distinction later.

WHY A STATED ABSENCE AND NOT AN EMPTY OR PLACEHOLDER ONE. An `innermost cause:`
line with nothing after it, or one carrying `?` / `unknown` / `None`, reads as
a cause the engine supplied — it sits exactly where a real cause sits — so it
is worse than silence rather than better. The clause therefore has to name
itself as an absence and say what was looked for.

THE SCOPE IS THE ATTRIBUTED ENDING, which the last two cases pin deliberately.
A stage failure is the one ending that OWES a cause: the record has already
claimed a fault, so a missing cause is a gap in its own account. An agent
request asked a question and suffered no fault, and an unestablished ending
establishes nothing either way — for those two, a line about a missing cause
would assert something about a fault neither record claims, which is the
prohibition `_dispatcher_needs_human_cause`'s docstring already carries.

The expected sentence is spelled as a LITERAL here and bound to its exported
name by one `getattr` assertion, because this module's Red predates the
constant and a Red's test bytes are fixed across its Red-to-Green pair.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro.commands import _dispatcher_needs_human_detail
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandResult,
    DispatchOutcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_fabro_terminal import (
    fabro_run_terminal_outcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_needs_human_cause import (
    needs_human_cause_body,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import (
    NEEDS_HUMAN_MARKER,
    DispatchPlan,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port import FabroInspectResult
from livespec_orchestrator_beads_fabro.commands._fabro_port_records import (
    fabro_failure_detail_from_payload,
    fabro_status_kind_from_payload,
)

_RUN = "01M55WZ7DS6A"
_ITEM = "bd-ib-3nu5vv"
_ROUTING_STAGE = "pr@1"
_TERMINAL_STAGE = "needs_human@1"
_RECORDED_AT_MS = 1792000000000

# The absence clause, as both surfaces must render it.
_CAUSE_ABSENT = (
    "innermost cause: ABSENT — the routing stage recorded no failure cause for "
    "this ending, so none is named rather than an empty or placeholder one"
)

# The terminal's own deliberate exit, which lives on the run CONCLUSION. It must
# not be reported as the cause, and it must not be reported as its absence
# either: it is the sentence the routing-stage attribution exists to suppress.
_TERMINAL_MESSAGE = "stage needs_human failed with no outgoing fail edge"

_READABLE_CAUSE = "goal gate unsatisfied for node pr and no retry target"

_STDERR = (
    f"{NEEDS_HUMAN_MARKER}_PRESERVED: refs/heads/needs-human/{_RUN}\n"
    f"{NEEDS_HUMAN_MARKER}: loop cannot auto-resolve this work-item; run "
    "terminated, work preserved by reference, decision routed to the ledger "
    "(blocked / needs-human)\n"
)


def _stage(*, handler: str, state: str) -> dict[str, Any]:
    """One entry of the Petri `stages` map, with the four keys it carries."""
    return {"handler": handler, "state": state, "output": None, "response": None}


def _petri_inspect(*, routing_state: str) -> list[object]:
    """A Petri-era `inspect` response whose checkpoint sits at the terminal.

    `routing_state` is what parts the attributed ending from the agent request:
    with the routing stage `failed` the record claims a fault and owes a cause,
    and with it `succeeded` the terminal's own designed failure is the only one
    left, which is a question an agent asked.
    """
    return [
        {
            "run_id": _RUN,
            "status": {"kind": "failed", "reason": "workflow_error"},
            "stages": {
                "implement@1": _stage(handler="agent", state="succeeded"),
                _ROUTING_STAGE: _stage(handler="agent", state=routing_state),
                _TERMINAL_STAGE: _stage(handler="script", state="failed"),
            },
            "checkpoint": {
                "current_node": "needs_human",
                "git_commit_sha": "9bcd4faa2e3c4d5f6071829304a5b6c7d8e9f012",
                "timestamp": "2026-10-18T02:00:00.000000000Z",
            },
            "conclusion": {
                "status": "failed",
                "failure": {
                    "reason": "workflow_error",
                    "detail": {"message": _TERMINAL_MESSAGE, "category": "deterministic"},
                },
            },
        }
    ]


def _unreadable_stages_inspect() -> list[object]:
    """The shape that establishes NOTHING: a `stages` list carries no state.

    An earlier Petri nightly reported `stages` as a list of ids rather than as
    a map, so neither grading input is readable and the ending is honestly
    undetermined — the third kind, and the one that must claim neither a fault
    nor a question.
    """
    return [
        {
            "run_id": _RUN,
            "status": {"kind": "failed", "reason": "workflow_error"},
            "stages": ["001-implement@1", _TERMINAL_STAGE],
            "checkpoint": {
                "current_node": "needs_human",
                "timestamp": "2026-10-18T02:00:00.000000000Z",
            },
            "conclusion": {
                "status": "failed",
                "failure": {
                    "reason": "workflow_error",
                    "detail": {"message": _TERMINAL_MESSAGE, "category": "deterministic"},
                },
            },
        }
    ]


def _petri_events(*, failure: dict[str, Any]) -> list[object]:
    """The routing stage's own failed ending, in the MEASURED Petri-era shape.

    Every spelling here is transcribed rather than reconstructed: the envelope
    from research note 006, and the body's `event`, its failure block at
    `outcome.status.failure` and the node at `item.subject.node.name` from this
    repository's committed reproducer
    `plan/fabro-currency/research/004-acp-spend-limit-repro.py` (candidate
    v0.371.0-nightly.0). The sibling module
    `test_dispatcher_needs_human_petri_routing_cause.py` records each citation
    field by field, including which of its own keys are composed.
    """
    body = {
        "event": "step.finished",
        "attempt": 1,
        "outcome": {"status": {"failure": failure}},
    }
    return [
        {
            "run_id": _RUN,
            "stream_seq": 12,
            "kind": "step.finished",
            "id": f"{_RUN}-12",
            "recorded_at": _RECORDED_AT_MS,
            "item": {
                "seq": 12,
                "recorded_at": _RECORDED_AT_MS,
                "subject": {"node": {"name": _ROUTING_STAGE}},
                "record": {"kind": "step.finished", "body": body},
            },
        }
    ]


def _plan(*, tmp_path: Path) -> DispatchPlan:
    return DispatchPlan(
        repo=tmp_path,
        work_item_id=_ITEM,
        branch=f"feat/{_ITEM}",
        workflow_toml=tmp_path / "workflow.toml",
        goal_file=tmp_path / "goal.txt",
        fabro_bin="fabro",
        fabro_factory_name="hp-candidate",
        fabro_factory_server="https://hp-xubuntu.example:32278",
        fabro_factory_dev_token=None,
        janitor=None,
        janitor_checkout=tmp_path / ".janitor",
        janitor_core_checkout=tmp_path / ".janitor" / ".livespec-core",
        janitor_core_repo_url="https://github.com/thewoolleyman/livespec.git",
        janitor_core_ref="master",
        review_fix_visit_cap=3,
        merge_on_review_cap_outcome="succeeded",
    )


def _surfaces(
    *, tmp_path: Path, inspect_payload: list[object], events_payload: list[object] | None
) -> tuple[DispatchOutcome, str]:
    """The dispatch result outcome and the durable ledger comment, as one pair.

    Both are returned from one call because they render from one outcome field:
    a build that fed the transient surface and not the durable one is the shape
    this item is closing, so a test reading only one of them would pass through
    it.
    """
    outcome = fabro_run_terminal_outcome(
        outcome_type=DispatchOutcome,
        plan=_plan(tmp_path=tmp_path),
        run_id=_RUN,
        inspect=FabroInspectResult(
            command=CommandResult(exit_code=0, stdout="", stderr=""),
            payload=inspect_payload,
            status_kind=fabro_status_kind_from_payload(payload=inspect_payload),
            failure=fabro_failure_detail_from_payload(payload=inspect_payload),
            events_payload=events_payload,
        ),
        exit_code=1,
        stderr=_STDERR,
    )
    assert outcome is not None
    return outcome, needs_human_cause_body(outcome=outcome)


def test_the_absence_clause_is_owned_by_one_module_and_spelled_once() -> None:
    """One owner for the sentence, because two surfaces make the same claim.

    The literal above is the test's own copy; this binds it to the exported
    name so the two renderers cannot drift into two wordings that merely look
    alike, and so a reader grepping either surface finds one phrase.
    """
    assert (
        getattr(_dispatcher_needs_human_detail, "NEEDS_HUMAN_CAUSE_ABSENT", None) == _CAUSE_ABSENT
    )


@pytest.mark.parametrize(
    "events_payload",
    [
        None,
        _petri_events(failure={"reason": "node_error"}),
        _petri_events(failure={}),
    ],
    ids=["unreadable-event-stream", "failure-block-with-no-cause", "empty-failure-block"],
)
def test_an_attributed_ending_with_no_readable_cause_states_the_absence(
    tmp_path: Path, events_payload: list[object] | None
) -> None:
    """Three ways the cause goes unread, one stated absence on both surfaces.

    The unreadable-stream case is the measured one: a refused `fabro events`
    read attaches `None`, which is also what every build predating the Petri
    envelope reading effectively saw. The other two are the engine recording a
    failure and saying nothing about why.
    """
    outcome, ledger = _surfaces(
        tmp_path=tmp_path,
        inspect_payload=_petri_inspect(routing_state="failed"),
        events_payload=events_payload,
    )

    assert outcome.fabro_failure_cause is None
    assert _CAUSE_ABSENT in outcome.detail
    assert _CAUSE_ABSENT in ledger
    # Not an EMPTY clause and not a placeholder standing in for a cause.
    assert "innermost cause: ;" not in outcome.detail
    assert "innermost cause: \n" not in ledger
    for placeholder in ("innermost cause: ?", "innermost cause: None", "innermost cause: unknown"):
        assert placeholder not in outcome.detail
        assert placeholder not in ledger
    # And the absence is still not an excuse to quote the terminal's own exit.
    assert _TERMINAL_MESSAGE not in outcome.detail
    assert _TERMINAL_MESSAGE not in ledger


def test_a_readable_cause_is_reported_as_the_cause_and_never_as_an_absence(
    tmp_path: Path,
) -> None:
    """The control without which a renderer could print the absence always.

    A build that emitted the absence clause unconditionally satisfies every
    assertion above while destroying the line those records exist to carry.
    """
    outcome, ledger = _surfaces(
        tmp_path=tmp_path,
        inspect_payload=_petri_inspect(routing_state="failed"),
        events_payload=_petri_events(
            failure={
                "reason": "node_error",
                "detail": {"message": _READABLE_CAUSE, "category": "deterministic"},
            }
        ),
    )

    assert f"innermost cause: {_READABLE_CAUSE}" in outcome.detail
    assert f"innermost cause: {_READABLE_CAUSE}" in ledger
    assert _CAUSE_ABSENT not in outcome.detail
    assert _CAUSE_ABSENT not in ledger


def test_a_failure_block_carrying_only_a_category_states_the_absence_and_keeps_it(
    tmp_path: Path,
) -> None:
    """The arm where a failure WAS read and only its cause is missing.

    This is the one case where the detail object exists, so a renderer keyed on
    "no failure block" rather than on "no cause" passes the three cases above
    and silently omits the clause here. The category is asserted as still
    reported, because the absence of a cause retracts nothing else the engine
    did record.
    """
    outcome, ledger = _surfaces(
        tmp_path=tmp_path,
        inspect_payload=_petri_inspect(routing_state="failed"),
        events_payload=_petri_events(failure={"reason": "node_error", "category": "deterministic"}),
    )

    assert outcome.fabro_failure_cause is None
    assert outcome.fabro_failure_category == "deterministic"
    assert _CAUSE_ABSENT in outcome.detail
    assert _CAUSE_ABSENT in ledger
    assert "failure category: deterministic" in ledger


def test_an_agent_request_ending_makes_no_claim_about_a_cause_either_way(
    tmp_path: Path,
) -> None:
    """An agent asked a question; nothing failed, so nothing is owed.

    The terminal still records `failed` because it always does, so this fixture
    is the one that would trip a renderer scoping the clause to "any
    needs-human ending" instead of to an attributed one.
    """
    outcome, ledger = _surfaces(
        tmp_path=tmp_path,
        inspect_payload=_petri_inspect(routing_state="succeeded"),
        events_payload=None,
    )

    assert outcome.needs_human_kind == "agent-request"
    assert "innermost cause" not in outcome.detail
    assert "innermost cause" not in ledger


def test_an_unestablished_ending_makes_no_claim_about_a_cause_either_way(
    tmp_path: Path,
) -> None:
    """Nothing was graded, so a missing cause is not a finding about a fault."""
    outcome, ledger = _surfaces(
        tmp_path=tmp_path,
        inspect_payload=_unreadable_stages_inspect(),
        events_payload=None,
    )

    assert outcome.needs_human_kind == "unestablished"
    assert "innermost cause" not in outcome.detail
    assert "innermost cause" not in ledger
