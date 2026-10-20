"""The recorded output of a succeeded Petri turn reaches terminal evidence."""

from __future__ import annotations

import importlib
from typing import Any

from livespec_orchestrator_beads_fabro.commands._fabro_terminal_evidence import (
    terminal_evidence,
)

_OUTCOMES_MODULE = "livespec_orchestrator_beads_fabro.commands._fabro_port_node_outcomes"


def test_a_succeeded_petri_turn_retains_its_response_for_terminal_evidence() -> None:
    """A response-only Petri entry remains available to a successful-turn reader."""
    module = importlib.import_module(_OUTCOMES_MODULE)
    outcomes = module.fabro_node_outcomes(
        record={
            "stages": {
                "review@1": {
                    "state": "succeeded",
                    "response": "Selected model is at capacity.",
                }
            }
        },
        checkpoint={},
    )
    assert outcomes["review@1"] == {
        "status": "succeeded",
        "response": "Selected model is at capacity.",
    }


def test_a_failed_predecessor_is_not_presented_as_a_succeeded_turn() -> None:
    """A later command failure cannot be replaced by an earlier review's output."""
    payload: list[dict[str, Any]] = [
        {
            "checkpoint": {
                "current_node": "needs_human",
                "next_node_id": None,
                "completed_nodes": ["review", "janitor"],
                "node_outcomes": {
                    "review": {
                        "status": "succeeded",
                        "output": "Selected model is at capacity.",
                    },
                    "janitor": {"status": "failed"},
                },
            }
        }
    ]
    evidence = terminal_evidence(payload=payload)
    assert evidence is not None
    assert hasattr(evidence, "succeeded_predecessor")
    assert evidence.succeeded_predecessor is None
    assert evidence.succeeded_output is None
