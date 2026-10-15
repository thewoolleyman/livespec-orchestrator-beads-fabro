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

from typing import Any

from livespec_orchestrator_beads_fabro.commands._fabro_causal_stage import (
    STAGE_FAILURE,
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
