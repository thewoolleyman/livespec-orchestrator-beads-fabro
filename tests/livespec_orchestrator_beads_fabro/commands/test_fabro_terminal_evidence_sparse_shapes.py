"""Sparse and malformed terminal-checkpoint shapes the measured runs cannot reach.

A sibling of `test_fabro_terminal_evidence.py` rather than more cases inside
it, for the reason `test_plan_result_proof_subject.py` is a sibling of
`test_plan_result_proof.py`: these shapes were found by a coverage measurement
taken AFTER that module's Red was authored, and a Red's test bytes are fixed
across its Red-to-Green pair.

Every shape here is one `bd`-adjacent engine record could legitimately produce
and none of them is a well-formed run. They matter because the fail direction
is asymmetric: an outcome map this reader cannot parse must degrade to "nothing
established" rather than to a confident attribution, since a confident wrong
stage reads exactly like a correct one at every surface downstream.
"""

from __future__ import annotations

from typing import Any

from livespec_orchestrator_beads_fabro.commands._fabro_terminal_evidence import terminal_evidence

_SHARED_SIGNATURE = "retry|deterministic|acp turn failed"


def _terminal(*, checkpoint: dict[str, Any]) -> list[object]:
    """One native-shaped response whose single checkpoint sits at the terminal."""
    return [
        {"run_id": "01SPARSESHAPE", "checkpoint": {"current_node": "needs_human", **checkpoint}}
    ]


def test_a_malformed_outcome_entry_is_skipped_rather_than_attributed() -> None:
    """A non-string node id, a blank one, and a non-mapping outcome all drop out.

    The well-formed sibling entry is asserted alongside them, so this is a case
    about SKIPPING the malformed ones and not about a reader that gave up on
    the whole map the moment it met one.
    """
    evidence = terminal_evidence(
        payload=_terminal(
            checkpoint={
                "node_outcomes": {
                    "7": ["not", "a", "mapping"],
                    "   ": {"status": "failed"},
                    "pr": {"status": "failed"},
                }
            }
        )
    )
    assert evidence is not None
    assert evidence.failed_stages == ("pr",)
    assert evidence.outcomes_observed is True


def test_an_entirely_malformed_outcome_map_reads_as_unobserved() -> None:
    """Every entry dropping leaves nothing to grade signatures against."""
    evidence = terminal_evidence(
        payload=_terminal(checkpoint={"node_outcomes": {"9": "not a mapping"}})
    )
    assert evidence is not None
    assert evidence.outcomes_observed is False
    assert evidence.failed_stages == ()
    assert evidence.current_predecessor is None


def test_a_failed_stage_carrying_no_signature_names_no_signature() -> None:
    """The stage is still attributed; an absent signature is not invented for it."""
    evidence = terminal_evidence(
        payload=_terminal(checkpoint={"node_outcomes": {"pr": {"status": "failed"}}})
    )
    assert evidence is not None
    assert evidence.failed_stages == ("pr",)
    assert evidence.stage_signatures == ()


def test_a_failure_block_without_a_signature_field_names_no_signature() -> None:
    """A present block carrying no readable signature yields none for that stage."""
    evidence = terminal_evidence(
        payload=_terminal(
            checkpoint={"node_outcomes": {"pr": {"failure": {"category": "deterministic"}}}}
        )
    )
    assert evidence is not None
    assert evidence.failed_stages == ("pr",)
    assert evidence.stage_signatures == ()


def test_two_failed_stages_sharing_one_signature_report_it_once() -> None:
    """Both stages are named; the signature they share is not duplicated."""
    evidence = terminal_evidence(
        payload=_terminal(
            checkpoint={
                "completed_nodes": ["review", "pr"],
                "node_outcomes": {
                    "review": {"status": "failed", "failure": {"signature": _SHARED_SIGNATURE}},
                    "pr": {"status": "failed", "failure": {"signature": _SHARED_SIGNATURE}},
                },
            }
        )
    )
    assert evidence is not None
    assert evidence.failed_stages == ("review", "pr")
    assert evidence.stage_signatures == (_SHARED_SIGNATURE,)


def test_a_failed_stage_absent_from_the_completed_list_keeps_its_map_order() -> None:
    """`completed_nodes` orders what it mentions; the rest follow, none dropped."""
    evidence = terminal_evidence(
        payload=_terminal(
            checkpoint={
                "completed_nodes": ["review"],
                "node_outcomes": {
                    "pr": {"status": "failed"},
                    "review": {"status": "failed"},
                },
            }
        )
    )
    assert evidence is not None
    assert evidence.failed_stages == ("review", "pr")
    assert evidence.current_predecessor == "pr"


def test_a_non_list_completed_nodes_field_leaves_the_map_order_standing() -> None:
    """An unusable ordering field is ignored rather than emptying the answer."""
    evidence = terminal_evidence(
        payload=_terminal(
            checkpoint={
                "completed_nodes": "review,pr",
                "node_outcomes": {"pr": {"status": "failed"}},
            }
        )
    )
    assert evidence is not None
    assert evidence.failed_stages == ("pr",)


def test_a_non_mapping_loop_signature_field_yields_no_history() -> None:
    """The counter is a signature-to-count map; anything else establishes nothing."""
    evidence = terminal_evidence(
        payload=_terminal(checkpoint={"loop_failure_signatures": ["pr|deterministic|x"]})
    )
    assert evidence is not None
    assert evidence.history_signatures == ()


def test_a_blank_loop_signature_key_is_dropped_from_history() -> None:
    """A key carrying no text names no stage, so it cannot be history about one."""
    evidence = terminal_evidence(
        payload=_terminal(checkpoint={"loop_failure_signatures": {"   ": 1, 4: 2}})
    )
    assert evidence is not None
    assert evidence.history_signatures == ()


def test_a_checkpoint_at_the_terminal_with_a_next_node_is_not_terminal() -> None:
    """Naming the terminal as current WHILE queueing another node has not ended there."""
    assert (
        terminal_evidence(
            payload=[
                {
                    "run_id": "01STILLROUTING",
                    "checkpoint": {"current_node": "needs_human", "next_node_id": "janitor"},
                }
            ]
        )
        is None
    )


def test_the_newest_terminal_checkpoint_wins_over_an_older_one() -> None:
    """A history array can hold several; the last one is the run's own ending."""
    evidence = terminal_evidence(
        payload=[
            {
                "run_id": "01TWOTERMINALS",
                "checkpoints": [
                    {"checkpoint": {"next_node_id": "needs_human", "node_outcomes": {}}},
                    {
                        "checkpoint": {
                            "next_node_id": "needs_human",
                            "node_outcomes": {"pr": {"status": "failed"}},
                        }
                    },
                ],
            }
        ]
    )
    assert evidence is not None
    assert evidence.failed_stages == ("pr",)
