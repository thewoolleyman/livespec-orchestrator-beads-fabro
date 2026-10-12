"""What a needs-human terminal's OWN checkpoint establishes about its cause.

The shape every assertion here is written against was verified by running
`fabro inspect <run> --server <factory> --json` against the two real runs
behind epic `bd-ib-ctagnf`, and it is NOT the shape a `fabro dump` export
carries. The CLI returns a one-element LIST whose record carries ONLY a
top-level `checkpoint` — there is no `checkpoints` history array — and that
checkpoint reports `current_node` as the terminal with `next_node_id` null.
A reader requiring a non-empty `next_node_id` naming the terminal therefore
cannot see the terminated CLI response at all, which is the input-shape error
these cases exist to pin.

THE TWO RUNS DIFFER IN THE ONE WAY THAT MATTERS, which is why both fixtures
are committed rather than one being taken as representative. The backgrounded
run records a loop failure signature for its failed `pr` stage; the
provider-ceiling run records NO loop signature for its failed `implement`
stage and only the terminal's own. So a loop counter is not the predicate for
a real failed predecessor, and its absence is not evidence that an agent asked
a question.

AND A LOOP SIGNATURE IS NOT EVIDENCE OF A CURRENT CAUSE EITHER. The engine's
`CircuitBreakerLifecycle.after_node` accumulates `loop_failure_signatures` and
never clears them on a later successful node, so a run that failed a gate,
recovered, and then genuinely asked a question still carries the old
signature. Attributing it would report a fault for an ending no fault caused.
The authoritative current evidence is the per-node outcome map; the signatures
are history.
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any, cast

_MODULE = "livespec_orchestrator_beads_fabro.commands._fabro_terminal_evidence"
_SOURCE = (
    Path(__file__).resolve().parents[3]
    / ".claude-plugin"
    / "scripts"
    / "livespec_orchestrator_beads_fabro"
    / "commands"
    / "_fabro_terminal_evidence.py"
)
_FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "fabro_native_inspect"

_BACKGROUND_SIGNATURE = "pr|deterministic|acp turn failed"
_PROVIDER_SIGNATURE = "implement|transient_infra|acp turn failed"
_TERMINAL_SIGNATURE = "needs_human|deterministic|script failed"


def _native(*, name: str) -> list[object]:
    """One committed native `fabro inspect --json` response."""
    return cast(
        "list[object]", json.loads((_FIXTURES / f"{name}.json").read_text(encoding="utf-8"))
    )


def _evidence(*, payload: object) -> Any:
    module = importlib.import_module(_MODULE)
    return module.terminal_evidence(payload=payload)


def test_the_native_terminal_checkpoint_is_read_from_a_null_next_node() -> None:
    """The real CLI response reports the terminal as `current_node`, not as next."""
    assert _SOURCE.is_file()
    evidence = _evidence(payload=_native(name="background"))
    assert evidence is not None
    assert evidence.failed_stages == ("pr",)
    assert evidence.outcomes_observed is True


def test_a_failed_predecessor_needs_no_loop_signature() -> None:
    """The provider run's failed `implement` carries no loop signature of its own."""
    assert _SOURCE.is_file()
    evidence = _evidence(payload=_native(name="provider"))
    assert evidence is not None
    assert evidence.failed_stages == ("implement",)
    assert evidence.stage_signatures == (_PROVIDER_SIGNATURE,)
    # The ONLY loop signature on that checkpoint belongs to the terminal, which
    # runs only because something else already failed and so can never be the
    # cause. It is excluded rather than reported as history.
    assert evidence.history_signatures == ()


def test_the_terminal_node_is_never_its_own_causal_stage() -> None:
    """The dead-end terminal exits 1 by design and is excluded from attribution."""
    assert _SOURCE.is_file()
    evidence = _evidence(payload=_native(name="background"))
    assert evidence is not None
    assert "needs_human" not in evidence.failed_stages
    assert _TERMINAL_SIGNATURE not in evidence.stage_signatures


def test_a_recovered_stage_signature_is_history_and_not_a_current_cause() -> None:
    """A node that later SUCCEEDED leaves a signature the engine never clears.

    This is the negative control for the whole attribution: the run carries a
    `review` loop signature and a terminal routing, and `review` is recorded
    `succeeded`. Nothing currently failed, so there is no causal stage — and
    the stale signature is retained as history rather than attributed.
    """
    assert _SOURCE.is_file()
    payload = [
        {
            "run_id": "01RECOVEREDTHENASKED",
            "status": {"kind": "failed"},
            "checkpoint": {
                "current_node": "needs_human",
                "next_node_id": None,
                "completed_nodes": ["implement", "review", "disposition"],
                "loop_failure_signatures": {"review|deterministic|acp turn failed": 1},
                "node_outcomes": {
                    "implement": {"status": "succeeded"},
                    "review": {"status": "succeeded"},
                    "disposition": {"status": "succeeded"},
                },
            },
        }
    ]
    evidence = _evidence(payload=payload)
    assert evidence is not None
    assert evidence.failed_stages == ()
    assert evidence.history_signatures == ("review|deterministic|acp turn failed",)
    assert evidence.outcomes_observed is True


def test_an_unreadable_outcome_map_is_reported_as_unobserved() -> None:
    """No per-node outcomes means the signatures cannot be graded against anything.

    The signature is still carried, because on a record with no outcome map it
    is the only evidence there is — but `outcomes_observed` says the grading
    input was absent, so the renderer can hedge instead of asserting a cause.
    """
    assert _SOURCE.is_file()
    payload = [
        {
            "run_id": "01NOOUTCOMEMAP",
            "checkpoint": {
                "current_node": "needs_human",
                "loop_failure_signatures": {_BACKGROUND_SIGNATURE: 1},
            },
        }
    ]
    evidence = _evidence(payload=payload)
    assert evidence is not None
    assert evidence.outcomes_observed is False
    assert evidence.failed_stages == ()
    assert evidence.history_signatures == (_BACKGROUND_SIGNATURE,)


def test_the_legacy_dump_shaped_history_array_still_resolves() -> None:
    """A `checkpoints[]` export shape keeps resolving, next-node routing and all."""
    assert _SOURCE.is_file()
    payload = [
        {
            "run_id": "01LEGACYDUMPSHAPE",
            "checkpoints": [
                {
                    "checkpoint": {
                        "next_node_id": "needs_human",
                        "loop_failure_signatures": {_BACKGROUND_SIGNATURE: 2},
                        "node_outcomes": {"pr": {"failure": {"signature": _BACKGROUND_SIGNATURE}}},
                    }
                }
            ],
        }
    ]
    evidence = _evidence(payload=payload)
    assert evidence is not None
    assert evidence.failed_stages == ("pr",)
    assert evidence.stage_signatures == (_BACKGROUND_SIGNATURE,)


def test_a_record_that_never_routed_to_the_terminal_yields_no_evidence() -> None:
    """A run executing an ordinary node is not a needs-human terminal."""
    assert _SOURCE.is_file()
    payload = [{"run_id": "01STILLWORKING", "checkpoint": {"current_node": "implement"}}]
    assert _evidence(payload=payload) is None


def test_an_unusable_payload_yields_no_evidence() -> None:
    """An absent or unparseable record establishes nothing, and says so."""
    assert _SOURCE.is_file()
    assert _evidence(payload=None) is None
    assert _evidence(payload=[]) is None


def test_several_failed_predecessors_are_ordered_by_the_completed_node_list() -> None:
    """`completed_nodes` is the engine's own ORDER; the outcome map is unordered.

    Both failed stages are carried — naming one of several would hide the rest
    behind an answer that looks complete — and the LAST in completed order is
    reported as the current predecessor.
    """
    assert _SOURCE.is_file()
    payload = [
        {
            "run_id": "01TWOFAILURES",
            "checkpoint": {
                "current_node": "needs_human",
                "completed_nodes": ["review", "pr"],
                "node_outcomes": {
                    "pr": {"status": "failed"},
                    "review": {"status": "failed"},
                },
            },
        }
    ]
    evidence = _evidence(payload=payload)
    assert evidence is not None
    assert evidence.failed_stages == ("review", "pr")
    assert evidence.current_predecessor == "pr"
