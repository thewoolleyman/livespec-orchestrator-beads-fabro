"""The Petri engine's per-stage states as a terminal's evidence (`bd-ib-dls2qt`).

A sibling of `test_fabro_terminal_evidence.py` rather than more cases inside it,
for the reason `test_fabro_terminal_evidence_sparse_shapes.py` is one: a Red's
test bytes are fixed across its Red-to-Green pair, so a shape measured after
that module's Red was authored cannot be added to it.

THE SHAPE, AND WHERE IT WAS MEASURED. On the Petri engine (hp-candidate
`:32278`, carrier `0.382.0-nightly.0` `adeefec`) a terminated run's
`fabro inspect --json` checkpoint carries only `current_node`,
`git_commit_sha` and `timestamp`. The per-node outcome map every assertion in
the two sibling modules reads — `checkpoint.node_outcomes` — DOES NOT EXIST on
that engine. Petri reports outcomes per STAGE instead, in the record's
top-level `stages` map keyed `<node>@<visit>`, each entry carrying `handler`,
`state`, `output` and `response`. Measured 2026-10-15 on run
`01M4Y7EJWTQWK5CWWS0NKDHY7T` (work-item `bd-ib-o6aeji`, canary 12): `inspect`
reported 48 stages `succeeded` and 2 `failed` — `proof_capture@2` and the
`needs_human@1` terminal — while the durable `livespec-needs-human-cause`
ledger comment written at 03:48:35Z recorded `ending: unestablished`, because
the reader found no outcome map to grade. Canary 11 (run
`01M4XNM4BBMYFPQDA6X5JCBDYM`) recorded the same at 2026-10-14T20:24:01Z.

The payloads below TRANSCRIBE that key set rather than copying a capture: the
per-stage keys, the three checkpoint keys, and the two failed stage ids are the
measured values, and the remaining stage ids stand in for the 48 that
succeeded. Nothing here asserts on `output` or `response`, which this reader
does not consult — the cause TEXT those fields and `fabro dump` carry is a
later item's to surface, and this one restores the CLASSIFICATION alone.

WHY THE TERMINAL'S OWN `failed` STATE IS IN EVERY FIXTURE. The `needs_human`
node is a dead-end script that exits 1 by design, so it records `failed` on
every run that reaches it — including the run where an agent simply asked a
question and nothing went wrong. A fixture omitting it would describe a record
no Petri run produces, and would let a reader that never excluded the terminal
pass the agent-request case.
"""

from __future__ import annotations

from typing import Any, cast

from livespec_orchestrator_beads_fabro.commands._fabro_causal_stage import (
    AGENT_REQUEST,
    STAGE_FAILURE,
    UNESTABLISHED,
    causal_stage_failure,
)
from livespec_orchestrator_beads_fabro.commands._fabro_terminal_evidence import terminal_evidence

_RUN_ID = "01M4Y7EJWTQWK5CWWS0NKDHY7T"
_FAILED_STAGE = "proof_capture@2"
_TERMINAL_STAGE = "needs_human@1"


def _stage(*, handler: str, state: str) -> dict[str, Any]:
    """One entry of the Petri `stages` map, with the four keys it carries."""
    return {"handler": handler, "state": state, "output": None, "response": None}


def _petri_payload(*, stages: object) -> list[object]:
    """One Petri-era `inspect` response whose checkpoint sits at the terminal.

    The checkpoint carries the three keys the engine writes and NO
    `node_outcomes`, which is the whole condition these cases are about.
    """
    return [
        {
            "run_id": _RUN_ID,
            "status": {"kind": "failed", "reason": "workflow_error"},
            "stages": stages,
            "checkpoint": {
                "current_node": "needs_human",
                "git_commit_sha": "90a53bad350043b9b723f64cfaa9d593ab1c2d3e",
                "timestamp": "2026-10-15T03:48:12.118293471Z",
            },
        }
    ]


_STAGES_WITH_A_FAILURE: dict[str, Any] = {
    "implement@1": _stage(handler="agent", state="succeeded"),
    "janitor@1": _stage(handler="script", state="succeeded"),
    "proof_capture@1": _stage(handler="agent", state="succeeded"),
    _FAILED_STAGE: _stage(handler="agent", state="failed"),
    _TERMINAL_STAGE: _stage(handler="script", state="failed"),
}

# The SAME run with its one real failure removed: an agent rode a conditional
# edge off a stage that succeeded and asked a question. The terminal still
# records `failed`, because it always does.
_STAGES_WITHOUT_A_FAILURE: dict[str, Any] = {
    "implement@1": _stage(handler="agent", state="succeeded"),
    "janitor@1": _stage(handler="script", state="succeeded"),
    "proof_capture@1": _stage(handler="agent", state="succeeded"),
    _FAILED_STAGE: _stage(handler="agent", state="succeeded"),
    _TERMINAL_STAGE: _stage(handler="script", state="failed"),
}


def test_a_petri_stage_state_map_establishes_the_ending() -> None:
    """The stage states ground the verdict the absent outcome map cannot.

    This is the defect itself: every Petri needs-human ending reported
    `unestablished`, so the one durable record of why a run stopped told its
    reader that the record "does not establish whether a stage failed or a
    decision was genuinely requested" — about a run whose own `inspect` output
    named the failed stage.
    """
    evidence = terminal_evidence(payload=_petri_payload(stages=_STAGES_WITH_A_FAILURE))
    assert evidence is not None
    assert evidence.outcomes_observed is True
    assert causal_stage_failure(evidence=evidence).kind == STAGE_FAILURE


def test_the_failed_petri_stage_is_named_and_the_terminal_stage_is_not() -> None:
    """`proof_capture@2` is the cause; `needs_human@1` can never be one.

    The terminal exclusion already existed and could not reach a Petri record,
    because it compared against the bare node id while Petri keys its stages
    `<node>@<visit>`. Naming the terminal is the worst available answer: it is
    true of every needs-human ending there has ever been, so it reads as a
    finding while carrying no information, and it displaces the stage that
    actually failed.
    """
    evidence = terminal_evidence(payload=_petri_payload(stages=_STAGES_WITH_A_FAILURE))
    assert evidence is not None
    assert evidence.failed_stages == (_FAILED_STAGE,)
    assert evidence.current_predecessor == _FAILED_STAGE
    assert causal_stage_failure(evidence=evidence).stages == (_FAILED_STAGE,)


def test_every_non_terminal_petri_stage_succeeding_is_an_agent_request() -> None:
    """A question genuinely awaits a human, and the terminal must not hide it.

    This is the same exclusion read from the other side, and it is the half
    that fails toward inventing a fault: without it the terminal's own designed
    `failed` state is the one failure on every such record, so EVERY Petri
    agent request would be reported as a stage failure.
    """
    evidence = terminal_evidence(payload=_petri_payload(stages=_STAGES_WITHOUT_A_FAILURE))
    assert evidence is not None
    assert evidence.outcomes_observed is True
    assert evidence.failed_stages == ()
    assert causal_stage_failure(evidence=evidence).kind == AGENT_REQUEST


def test_the_terminal_failure_is_not_a_succeeded_turn_predecessor() -> None:
    """The terminal's designed failure cannot become a turn available for release."""
    payload = _petri_payload(stages=_STAGES_WITHOUT_A_FAILURE)
    checkpoint = cast("dict[str, Any]", cast("dict[str, Any]", payload[0])["checkpoint"])
    checkpoint["completed_nodes"] = ["review", "needs_human"]
    evidence = terminal_evidence(payload=payload)
    assert evidence is not None
    assert evidence.succeeded_predecessor is None
    assert evidence.succeeded_output is None


def test_a_checkpoint_carrying_node_outcomes_is_still_graded_from_them() -> None:
    """The stage map is a FALLBACK, never a merge — the outcome map still wins.

    The two inputs are made to DISAGREE, which is the only shape that can fail
    for the right reason: the outcome map records nothing failed while the
    stage map records `proof_capture@2` failed, so a reader that preferred the
    stage map, or merged the two, reports a stage failure here. A fixture whose
    inputs agreed would pass whichever one was read.

    There is no Red for this one and the implementation never had a defect
    here: it is a preservation assertion, pinning the precedence an engine
    carrying BOTH shapes depends on.
    """
    payload = _petri_payload(stages=_STAGES_WITH_A_FAILURE)
    checkpoint = cast("dict[str, Any]", cast("dict[str, Any]", payload[0])["checkpoint"])
    checkpoint["node_outcomes"] = {
        "implement": {"status": "succeeded"},
        "review": {"status": "succeeded"},
    }
    evidence = terminal_evidence(payload=payload)
    assert evidence is not None
    assert evidence.failed_stages == ()
    assert causal_stage_failure(evidence=evidence).kind == AGENT_REQUEST


def test_a_stages_field_that_is_not_a_map_still_reports_unestablished() -> None:
    """A `stages` LIST is not a reading, and an absence must not become a verdict.

    An earlier Petri nightly reported `stages` as a list of stage ids rather
    than as a map — the shape
    `tests/.../test_dispatcher_fabro_terminal_needs_human.py` transcribes from
    `v0.378.0-nightly.0`. Neither input is then readable, so the ending is
    honestly undetermined; the alternative, treating an unreadable field as
    "graded, and nothing failed", would manufacture an agent nobody heard from.

    Like the case above this has no Red: it is the honest-unknown arm being
    pinned against the widening, not a defect that was fixed.
    """
    evidence = terminal_evidence(payload=_petri_payload(stages=["implement@1", _TERMINAL_STAGE]))
    assert evidence is not None
    assert evidence.outcomes_observed is False
    assert causal_stage_failure(evidence=evidence).kind == UNESTABLISHED


def test_a_stage_entry_carrying_no_state_grounds_nothing() -> None:
    """An entry with no readable `state` is not a reading, so it is dropped.

    Every entry dropping leaves the map unreadable, which is the honest-unknown
    arm rather than a confident one: a reader that counted an entry it could
    not grade would report "graded, and nothing failed" — a genuine question —
    for a record that said nothing at all.
    """
    evidence = terminal_evidence(
        payload=_petri_payload(
            stages={
                "implement@1": {"handler": "agent", "output": None},
                _TERMINAL_STAGE: {"handler": "script", "state": None},
            }
        )
    )
    assert evidence is not None
    assert evidence.outcomes_observed is False
    assert evidence.failed_stages == ()
