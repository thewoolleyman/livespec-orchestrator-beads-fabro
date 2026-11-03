"""Malformed Petri envelope coverage for the stall watchdog command-node reader."""

from __future__ import annotations

import json

from livespec_orchestrator_beads_fabro.commands._dispatcher_open_command_node import (
    open_command_node,
)
from livespec_orchestrator_beads_fabro.commands._node_timeouts import DEFAULT_NODE_TIMEOUTS


def test_malformed_petri_envelopes_do_not_open_a_command_node() -> None:
    """Absent Petri mappings say no lifecycle fact rather than raising or guessing."""
    petri_node = {"subject": {"node": {"name": "janitor", "kind": "attractor/command"}}}
    legacy_node = {"node_id": "janitor"}
    events = json.dumps(
        [
            {},
            {"item": {}},
            {"item": {"subject": {}}},
            {**legacy_node, "item": {}},
            {**legacy_node, "item": {"record": {}}},
            {**legacy_node, "item": {"record": {"body": "not a mapping"}}},
            {**legacy_node, "item": {"record": {"body": {}}}},
            {"item": petri_node},
            {
                "item": {
                    "record": {"body": {"event": "step.started"}},
                    "subject": {
                        "node": {"name": "not-a-workflow-node", "kind": "attractor/command"}
                    },
                }
            },
        ]
    )

    assert open_command_node(events_json=events, timeouts=DEFAULT_NODE_TIMEOUTS) is None
