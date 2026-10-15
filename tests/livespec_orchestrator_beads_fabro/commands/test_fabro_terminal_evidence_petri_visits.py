"""One Petri stage map entry PER VISIT, graded as one state per node.

A sibling of `test_fabro_terminal_evidence_petri_stages.py` for the reason that
module is a sibling of `test_fabro_terminal_evidence.py`: a Red's test bytes are
fixed across its Red-to-Green pair, so a shape measured after that module's Red
was authored cannot be added to it.

WHAT THE STAGE MAP ACTUALLY IS. `checkpoint.node_outcomes` is keyed by NODE and
carries that node's CURRENT status, which is why a node the loop retried to
success reports `succeeded` there. The Petri `stages` map is keyed
`<node>@<visit>` and carries one entry PER VISIT, and the engine never retires
an entry: a visit that failed and was then repaired by the graph's bounded fix
loop keeps its own `failed` entry for the life of the record. So the two maps
answer different questions — one the ending, one the whole history — and reading
the history map entry-by-entry grades a run on faults it recovered from.

THE SHAPE THAT PROVES IT IS THE ORDINARY ONE. `workflow.fabro` routes a
non-zero script node to `failed` and then into the fix loop, so `janitor@1`
failed / `fix@1` succeeded / `janitor@2` succeeded is what EVERY run the fix
loop repaired looks like. Graded per entry, such a run reports `janitor@1` as
the failed stage and the durable `livespec-needs-human-cause` comment then says
`no agent asked anything, so no answer is owed` — a recovered stage blamed and a
genuine question suppressed, in the one record that outlives the run. That per-
visit entries persist is not hypothetical: the run this item was filed from
carries `proof_capture@1` succeeded beside `proof_capture@2` failed.

SO EACH NODE IS COLLAPSED TO ITS LATEST VISIT BEFORE GRADING, and the
comparison is on the visit SUFFIX AS A NUMBER rather than on map order or on
text. Map order is not evidence of visit order, and `@10` sorts before `@9` as
text — two orderings that agree with the numeric one on the measured record and
disagree on a longer loop, which is the shape that would make a passing fixture
no evidence at all.
"""

from __future__ import annotations

from typing import Any

from livespec_orchestrator_beads_fabro.commands._fabro_causal_stage import (
    AGENT_REQUEST,
    STAGE_FAILURE,
    causal_stage_failure,
)
from livespec_orchestrator_beads_fabro.commands._fabro_terminal_evidence import terminal_evidence

_TERMINAL_STAGE = "needs_human@1"


def _stage(*, handler: str, state: str) -> dict[str, Any]:
    """One entry of the Petri `stages` map, with the four keys it carries."""
    return {"handler": handler, "state": state, "output": None, "response": None}


def _petri_payload(*, stages: dict[str, Any]) -> list[object]:
    """One Petri-era `inspect` response whose checkpoint sits at the terminal.

    The checkpoint carries the three keys that engine writes and NO
    `node_outcomes`, which is the condition that routes the reading to the
    stage map at all.
    """
    return [
        {
            "run_id": "01M4YYJZESMMEWJ74AEVAMK7TP",
            "status": {"kind": "failed", "reason": "workflow_error"},
            "stages": stages,
            "checkpoint": {
                "current_node": "needs_human",
                "git_commit_sha": "2d3bd3c0bdfb5df8cdd15e462c59e177f40bfd91",
                "timestamp": "2026-10-15T06:31:44.102938514Z",
            },
        }
    ]


def test_a_repaired_nodes_earlier_failed_visit_is_not_the_ending() -> None:
    """`janitor@1` failed and `janitor@2` succeeded, so the janitor did not fail.

    This is the defect, in the shape every fix-loop repair produces. The run
    reached the terminal because an agent asked a question; grading the history
    map per entry answers with a stage that had already been repaired, which
    both blames a node nobody should look at and tells the operator that no
    answer is owed on a run where one is.
    """
    evidence = terminal_evidence(
        payload=_petri_payload(
            stages={
                "implement@1": _stage(handler="agent", state="succeeded"),
                "janitor@1": _stage(handler="script", state="failed"),
                "fix@1": _stage(handler="agent", state="succeeded"),
                "janitor@2": _stage(handler="script", state="succeeded"),
                "review@1": _stage(handler="agent", state="succeeded"),
                _TERMINAL_STAGE: _stage(handler="script", state="failed"),
            }
        )
    )
    assert evidence is not None
    assert evidence.outcomes_observed is True
    assert evidence.failed_stages == ()
    assert evidence.current_predecessor is None
    assert causal_stage_failure(evidence=evidence).kind == AGENT_REQUEST


def test_the_latest_visit_of_a_node_still_names_its_own_failure() -> None:
    """`proof_capture@1` succeeded and `proof_capture@2` failed — `@2` is named.

    The collapse is to the LATEST visit and not to the first, so the measured
    run's own shape still answers as it must. Without this case the collapse
    could be implemented as "the earliest visit wins" and the case above would
    not notice.
    """
    evidence = terminal_evidence(
        payload=_petri_payload(
            stages={
                "implement@1": _stage(handler="agent", state="succeeded"),
                "proof_capture@1": _stage(handler="agent", state="succeeded"),
                "proof_capture@2": _stage(handler="agent", state="failed"),
                _TERMINAL_STAGE: _stage(handler="script", state="failed"),
            }
        )
    )
    assert evidence is not None
    assert evidence.failed_stages == ("proof_capture@2",)
    assert evidence.current_predecessor == "proof_capture@2"
    assert causal_stage_failure(evidence=evidence).kind == STAGE_FAILURE


def test_the_latest_visit_is_chosen_by_number_and_not_by_map_order() -> None:
    """The repaired visit is written FIRST here, and still wins.

    JSON object order is the engine's document order and this reader uses it
    for SEQUENCE, but it is not evidence of visit order — a record that listed
    the retry before the failure would otherwise grade the failure as current.
    """
    evidence = terminal_evidence(
        payload=_petri_payload(
            stages={
                "janitor@2": _stage(handler="script", state="succeeded"),
                "janitor@1": _stage(handler="script", state="failed"),
                _TERMINAL_STAGE: _stage(handler="script", state="failed"),
            }
        )
    )
    assert evidence is not None
    assert evidence.failed_stages == ()
    assert causal_stage_failure(evidence=evidence).kind == AGENT_REQUEST


def test_the_latest_visit_is_chosen_by_number_and_not_as_text() -> None:
    """`janitor@10` outranks `janitor@9`, which a text comparison inverts.

    This is the discriminating case for the comparison itself: on every
    single-digit record a lexicographic comparison agrees with the numeric one,
    so a fixture that never crosses ten would pass against the wrong rule.
    """
    evidence = terminal_evidence(
        payload=_petri_payload(
            stages={
                "janitor@9": _stage(handler="script", state="failed"),
                "janitor@10": _stage(handler="script", state="succeeded"),
                _TERMINAL_STAGE: _stage(handler="script", state="failed"),
            }
        )
    )
    assert evidence is not None
    assert evidence.failed_stages == ()
    assert causal_stage_failure(evidence=evidence).kind == AGENT_REQUEST


def test_an_unnumbered_visit_suffix_falls_back_to_the_records_own_order() -> None:
    """Two entries of one node carrying no readable visit number.

    No engine writes this, and the reader still has to answer: a suffix it
    cannot order numerically leaves document order as the only ordering
    evidence on the record, which is the same fallback `_failed_stages` already
    uses when the checkpoint names no completed nodes. The alternative — keeping
    both entries because neither can be ranked — is the defect above returning
    through the one shape nobody writes a fixture for.
    """
    evidence = terminal_evidence(
        payload=_petri_payload(
            stages={
                "janitor@retry": _stage(handler="script", state="failed"),
                "janitor@final": _stage(handler="script", state="succeeded"),
                _TERMINAL_STAGE: _stage(handler="script", state="failed"),
            }
        )
    )
    assert evidence is not None
    assert evidence.failed_stages == ()
    assert causal_stage_failure(evidence=evidence).kind == AGENT_REQUEST
