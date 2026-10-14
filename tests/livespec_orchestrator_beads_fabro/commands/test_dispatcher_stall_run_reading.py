"""The absence arms of the cancelled run's own reading.

The populated readings — the open node, the between-nodes edge target, the last
publication and the unpublished run — are asserted at the integration tier in
`tests/integration/test_dispatcher_stall_cancel_scenario172.py`, because they
are what the cancel record is graded on. What lives here is the set of readings
that return NOTHING, and they need their own module for a reason the populated
cases cannot carry: each of them produces a well-formed, plausible answer, so a
reader that had stopped reading would look identical to one that read and found
nothing.

`None` from `executing_stage` is deliberately one value for three different
facts, and the module docstring explains why: an unreadable stream, a stream
with no lifecycle events, and a run whose every node ended with no edge selected
after it all mean "the run's own record does not say where it was", which is
what the cancel record states instead of guessing.
"""

from __future__ import annotations

import json

from livespec_orchestrator_beads_fabro.commands._dispatcher_stall_run_reading import (
    executing_stage,
    last_publish_draft_publication,
)


def test_an_unreadable_stream_names_no_stage_and_no_publication() -> None:
    """A stream nothing could be read out of reports absence on both readings.

    Asserted on BOTH readings because they take different routes out of the
    same failure — one returns before the open-node count, the other before the
    completed-`publish_draft` test — so a build that guarded only one would
    satisfy half of this and then match a marker against text belonging to a
    stream it could not parse.
    """
    assert executing_stage(events_json="not json at all") is None
    assert last_publish_draft_publication(events_json="not json at all", record_text="") is None


def test_a_stream_with_no_lifecycle_events_names_no_stage() -> None:
    """A readable stream carrying no node lifecycle reports no stage.

    This is the empty-but-healthy case, which is distinct from the unreadable
    one above: the stream parsed, and it genuinely says nothing about nodes.
    """
    assert executing_stage(events_json="[]") is None


def test_a_node_event_that_neither_starts_nor_ends_a_node_leaves_it_closed() -> None:
    """A node-scoped event of some other family does not open a node.

    The counting is over START and END events only. An event that names a node
    but neither starts nor ends it — a log line, a tool call, a heartbeat —
    must leave the count where it was: incrementing on it would report a node
    as open for ever, which is a cancel that can never name the stage it was
    really in, and decrementing would close a node that is still running.
    """
    events = json.dumps(
        [
            {"event": "fabro.agent.log", "node_id": "implement"},
            {"event": "fabro.agent.tool.completed", "node_id": "implement"},
        ]
    )

    assert executing_stage(events_json=events) is None


def test_an_edge_naming_no_usable_target_selects_nothing() -> None:
    """An `edge.selected` whose target is absent, blank or not a string is skipped.

    The three shapes are asserted together because they are one guard, and
    because each would otherwise reach the record as a stage: a blank string is
    the one that matters most, since it renders as a present-but-empty
    `executing_stage` — a record that looks like it located the run and names
    nowhere.
    """
    events = json.dumps(
        [
            {"event": "fabro.edge.selected", "properties": {"to_node": None}},
            {"event": "fabro.edge.selected", "properties": {"to_node": "   "}},
            {"event": "fabro.edge.selected", "properties": {}},
            {"event": "fabro.edge.selected"},
        ]
    )

    assert executing_stage(events_json=events) is None


def test_a_failed_publish_draft_is_not_a_completed_publication() -> None:
    """A `publish_draft` that FAILED establishes no publication to name.

    It may have pushed and it may not, so a record naming a publication the
    node did not finish would assert something its own evidence does not
    establish — and the marker in the record text is NOT allowed to stand in
    for the completion event, which is why the fixture carries one.
    """
    events = json.dumps(
        [
            {"event": "fabro.stage.started", "node_id": "publish_draft"},
            {"event": "fabro.stage.failed", "node_id": "publish_draft"},
        ]
    )
    record_text = (
        f"LIVESPEC_PUBLISH_DRAFT_PUBLISHED: publish_branch=x head={'e' * 40} pull_request=#9"
    )

    assert last_publish_draft_publication(events_json=events, record_text=record_text) is None
    # The failed node is CLOSED, so the stage reading falls through to the edge
    # target — and there is none, which is the honest absence.
    assert executing_stage(events_json=events) is None
