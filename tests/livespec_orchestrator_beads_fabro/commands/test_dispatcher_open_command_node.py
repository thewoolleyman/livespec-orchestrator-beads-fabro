"""Tests for the open-COMMAND-node reading behind the stall watchdog's bound.

`open_command_node` answers one question off one `fabro events --json` read:
which COMMAND node of the `implement-work-item` graph is started and not yet
ended, and what timeout did it resolve for this dispatch. The stall decision
grades a quiet stretch against that bound instead of the configured stall
window, because a command node emits a start event and a completion event and
nothing between them — so both liveness layers are flat for its whole duration
however healthy the run is (bd-ib-qsk4o5).

Everything here is hermetic: synthetic event JSON in, a reading out. No fabro
run launches and no probe is issued.

Two of these cases are controls rather than behaviour, and they are what give
the rest meaning. `test_command_nodes_are_exactly_the_graphs_script_nodes`
reads the COMMITTED workflow graph, because a node-name set that drifted away
from the graph would report "no command node open" for a node that is open —
a clean, plausible answer that reinstates the defect. And
`test_an_unreadable_stream_is_no_open_node` pins the absence of a reading
apart from a reading of absence: both answer None here, deliberately, and the
reason that conflation is safe is recorded on `LivenessSample`.
"""

from __future__ import annotations

import re
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_open_command_node import (
    COMMAND_NODES,
    open_command_node,
)
from livespec_orchestrator_beads_fabro.commands._node_timeouts import (
    DEFAULT_NODE_TIMEOUT_SECONDS,
    DEFAULT_NODE_TIMEOUTS,
    REPOSITORY_LAYER,
    NodeTimeouts,
)

_WORKFLOW = (
    Path(__file__).resolve().parents[3]
    / ".claude-plugin/.fabro/workflows/implement-work-item/workflow.fabro"
)

# One graph node block, e.g. `    janitor [\n        ...\n    ]`, captured
# whole so the body can be asked whether it declares a `script` attribute.
_NODE_BLOCK = re.compile(r"^    (?P<node>[a-z_]+) \[\n.*?^    \]", re.DOTALL | re.MULTILINE)


def _event(*, name: str, node: str, nested: bool = False) -> str:
    """One event record as the engine emits it, by node id and lifecycle name."""
    where = f'"properties": {{"node_id": "{node}"}}' if nested else f'"node_id": "{node}"'
    return f'{{"event": "{name}", {where}, "timestamp": "2026-10-12T09:52:05Z"}}'


def _stream(*records: str) -> str:
    return f"[{', '.join(records)}]"


def test_command_nodes_are_exactly_the_graphs_script_nodes() -> None:
    # The set is a claim ABOUT the committed graph, so it is checked against
    # it: a name this tuple misses is a node whose open stretch is graded
    # against the shorter stall window, which is the cancellation this item
    # fixes, and a name it carries that the graph does not declare widens a
    # bound for a node that cannot run. Both read as a perfectly normal
    # answer at every other surface.
    text = _WORKFLOW.read_text(encoding="utf-8")
    declared = {
        match.group("node") for match in _NODE_BLOCK.finditer(text) if "script=" in match.group(0)
    }
    assert declared == set(COMMAND_NODES)
    # And the ACP nodes are absent, which is the other half of the claim: a
    # run inside one emits agent events throughout, so widening its bound
    # would retire the backstop rather than relax it.
    assert "implement" not in COMMAND_NODES


def test_a_started_command_node_is_open_with_its_resolved_timeout() -> None:
    reading = open_command_node(
        events_json=_stream(_event(name="stage.started", node="janitor")),
        timeouts=DEFAULT_NODE_TIMEOUTS,
    )
    assert reading is not None
    assert reading.node == "janitor"
    assert reading.timeout_seconds == float(DEFAULT_NODE_TIMEOUT_SECONDS)


def test_a_completed_command_node_is_not_open() -> None:
    reading = open_command_node(
        events_json=_stream(
            _event(name="stage.started", node="janitor"),
            _event(name="stage.completed", node="janitor"),
        ),
        timeouts=DEFAULT_NODE_TIMEOUTS,
    )
    assert reading is None


def test_a_failed_command_node_is_not_open() -> None:
    # A FAILED stage ends the node exactly as a completed one does; the
    # engine emits a fresh start event when it retries, which the next case
    # covers.
    reading = open_command_node(
        events_json=_stream(
            _event(name="stage.started", node="publish_draft"),
            _event(name="stage.failed", node="publish_draft"),
        ),
        timeouts=DEFAULT_NODE_TIMEOUTS,
    )
    assert reading is None


def test_a_retried_command_node_is_open_again() -> None:
    # Two starts against one ending: the second attempt is running. Counting
    # rather than reading the last lifecycle event is what gets this right.
    reading = open_command_node(
        events_json=_stream(
            _event(name="stage.started", node="janitor"),
            _event(name="stage.failed", node="janitor"),
            _event(name="stage.started", node="janitor"),
        ),
        timeouts=DEFAULT_NODE_TIMEOUTS,
    )
    assert reading is not None
    assert reading.node == "janitor"


def test_out_of_order_records_read_the_same_as_ordered_ones() -> None:
    # `parse_last_event_epoch` records that events may arrive out of order,
    # so a reader that keyed on the LAST start or ending it saw would answer
    # differently for one reordering of the same stream.
    ordered = _stream(
        _event(name="stage.started", node="janitor"),
        _event(name="stage.completed", node="janitor"),
    )
    reversed_stream = _stream(
        _event(name="stage.completed", node="janitor"),
        _event(name="stage.started", node="janitor"),
    )
    assert open_command_node(events_json=ordered, timeouts=DEFAULT_NODE_TIMEOUTS) is None
    assert open_command_node(events_json=reversed_stream, timeouts=DEFAULT_NODE_TIMEOUTS) is None


def test_a_repository_configured_timeout_is_the_reported_bound() -> None:
    # The bound is this dispatch's own resolution, not the fleet default, so
    # a repository that lengthens `dispatcher.node_timeouts.janitor` gets the
    # longer bound in the watchdog too.
    configured = NodeTimeouts(
        configured={"janitor": 5400},
        stall_seconds=7200,
        stall_layer=REPOSITORY_LAYER,
    )
    reading = open_command_node(
        events_json=_stream(_event(name="stage.started", node="janitor")),
        timeouts=configured,
    )
    assert reading is not None
    assert reading.timeout_seconds == 5400.0


def test_the_longest_bound_wins_when_two_nodes_read_as_open() -> None:
    # No two command nodes run at once in this graph, so a tie is a reading
    # artifact — and the bound then has to cover whichever node is genuinely
    # still running, which is the only choice that cannot cancel early.
    configured = NodeTimeouts(
        configured={"janitor": 900, "publish_draft": 3600},
        stall_seconds=7200,
        stall_layer=REPOSITORY_LAYER,
    )
    reading = open_command_node(
        events_json=_stream(
            _event(name="stage.started", node="janitor"),
            _event(name="stage.started", node="publish_draft"),
        ),
        timeouts=configured,
    )
    assert reading is not None
    assert reading.node == "publish_draft"
    assert reading.timeout_seconds == 3600.0


def test_a_nested_node_id_is_read() -> None:
    # The engine puts `node_id` beside the envelope on its stage events while
    # other event families nest their fields under `properties`; both shapes
    # are read, so one build's envelope cannot blind the bound.
    reading = open_command_node(
        events_json=_stream(_event(name="stage.started", node="janitor", nested=True)),
        timeouts=DEFAULT_NODE_TIMEOUTS,
    )
    assert reading is not None
    assert reading.node == "janitor"


def test_an_acp_nodes_lifecycle_events_are_passed_over() -> None:
    reading = open_command_node(
        events_json=_stream(_event(name="stage.started", node="implement")),
        timeouts=DEFAULT_NODE_TIMEOUTS,
    )
    assert reading is None


def test_a_record_with_no_node_id_is_passed_over() -> None:
    reading = open_command_node(
        events_json='[{"event": "stage.started", "timestamp": "2026-10-12T09:52:05Z"}]',
        timeouts=DEFAULT_NODE_TIMEOUTS,
    )
    assert reading is None


def test_a_non_string_node_id_is_passed_over() -> None:
    reading = open_command_node(
        events_json='[{"event": "stage.started", "node_id": 7}]',
        timeouts=DEFAULT_NODE_TIMEOUTS,
    )
    assert reading is None


def test_a_non_mapping_properties_value_is_passed_over() -> None:
    reading = open_command_node(
        events_json='[{"event": "stage.started", "properties": "janitor"}]',
        timeouts=DEFAULT_NODE_TIMEOUTS,
    )
    assert reading is None


def test_a_command_nodes_non_lifecycle_event_neither_opens_nor_closes_it() -> None:
    reading = open_command_node(
        events_json=_stream(_event(name="edge.selected", node="janitor")),
        timeouts=DEFAULT_NODE_TIMEOUTS,
    )
    assert reading is None


def test_a_record_with_no_readable_name_neither_opens_nor_closes_a_node() -> None:
    # The name field is absent, or present and not a string; either way the
    # record says nothing about a node's lifecycle, which is what an unnamed
    # record tells us.
    assert (
        open_command_node(
            events_json='[{"node_id": "janitor", "timestamp": "2026-10-12T09:52:05Z"}]',
            timeouts=DEFAULT_NODE_TIMEOUTS,
        )
        is None
    )
    assert (
        open_command_node(
            events_json='[{"event": 1, "node_id": "janitor"}]',
            timeouts=DEFAULT_NODE_TIMEOUTS,
        )
        is None
    )


def test_a_namespaced_event_name_is_read() -> None:
    # Some builds namespace the stream's name field, so the lifecycle names
    # are matched by suffix.
    reading = open_command_node(
        events_json=_stream(_event(name="fabro.stage.started", node="janitor")),
        timeouts=DEFAULT_NODE_TIMEOUTS,
    )
    assert reading is not None
    assert reading.node == "janitor"


def test_an_unreadable_stream_is_no_open_node() -> None:
    # A stream the shared reader cannot read at all answers None — the same
    # answer as a readable stream with nothing open. The conflation is
    # deliberate and is safe because the same read already lands as a
    # no-signal `last_event_epoch`, and a no-signal observation is excluded
    # from the quiet window the bound is taken across.
    assert open_command_node(events_json="", timeouts=DEFAULT_NODE_TIMEOUTS) is None
    assert open_command_node(events_json="7", timeouts=DEFAULT_NODE_TIMEOUTS) is None


def test_an_empty_stream_is_no_open_node() -> None:
    assert open_command_node(events_json="[]", timeouts=DEFAULT_NODE_TIMEOUTS) is None
