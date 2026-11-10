"""Which COMMAND node of the phase graph a run is inside, read off its events.

One concern: given one `fabro events --json` read and this dispatch's
resolved node timeouts, report the `OpenCommandNode` the stall decision
grades against — or None when no command node is open and when the stream
could not be read at all.

WHY A COMMAND NODE NEEDS ITS OWN BOUND. Every other node of the
`implement-work-item` graph is an ACP node, so a healthy run inside one is
emitting agent tool events and heartbeat metric exports continuously. A
COMMAND node — `janitor`, `publish_draft`, `implementation_diff`,
`verify_pr` — runs a shell script, so it emits its start event, runs for as
long as the script takes, and emits a completion event. Both liveness layers
are therefore FLAT across its whole duration however healthy the run is: the
heartbeat because it beats only while an agent turn runs, the event stream
because there is no further event to emit. Measured 2026-10-12, a sandbox
`just check` ran to 21 minutes under load, so the stall window is routinely
the shorter of the two bounds and grading a command node against it cancelled
runs whose work was already green (bd-ib-qsk4o5: three of six stall cancels
on hp since 2026-10-08, including run 01M4QKN0R3N3, cancelled inside
`publish_draft` seven minutes after its janitor went green).

THE OPEN SET IS COUNTED, NOT SEQUENCED, because the watchdog's own
`parse_last_event_epoch` records that events may arrive out of order: a
reader that keyed on the LAST start or completion it happened to see would
answer differently for one reordering of the same stream. Counting starts
against completions is order-free, and it is also what makes a RETRY read
correctly — a node whose first attempt failed emits a second start, so two
starts against one completion is genuinely open.

A TIE IS BROKEN BY THE LONGEST BOUND rather than by position in the stream,
for the same reason. In this graph no two command nodes run at once, so the
tie is a reading artifact; when one is produced, the bound has to cover
whichever node is genuinely still running, and the longest is the only choice
that cannot cancel a run early.

Pure of side effects: the `fabro events` call itself happens in
`_dispatcher_io_liveness_probe` through the `FabroPort`, so the hermetic test
tier drives every branch from synthetic event JSON.
"""

from __future__ import annotations

from typing import Any, cast

from livespec_orchestrator_beads_fabro.commands._dispatcher_watchdog import OpenCommandNode
from livespec_orchestrator_beads_fabro.commands._fabro_port_events import (
    fabro_event_records_from_stdout,
)
from livespec_orchestrator_beads_fabro.commands._node_timeouts import NodeTimeouts

__all__: list[str] = [
    "COMMAND_NODES",
    "open_command_node",
    "updated_open_command_node",
]

# Every COMMAND node of the `implement-work-item` workflow — the nodes the
# graph declares with a `script` attribute rather than an `acp.command` one.
# The ACP nodes are deliberately absent: a healthy run inside one emits agent
# events throughout, so the stall window already bounds it correctly, and
# widening every node's bound to its own timeout would retire the backstop.
#
# The three TERMINAL sentinels (`dead_implementer`, `needs_human`,
# `non_converged`) ARE here, because they are command nodes like the rest and
# each one pushes a preserve ref before the run ends; a sentinel's script is
# no more instantaneous than the janitor's. They cost nothing when they are
# not running, and `tests/.../test_dispatcher_open_command_node.py` asserts
# this tuple against the committed graph so the set cannot drift away from it.
COMMAND_NODES: tuple[str, ...] = (
    "dead_implementer",
    "dod_gate_mutation_guard",
    "fix_commit_settle",
    "fix_open_red_route",
    "fix_progress_route",
    "implement_amendment_route",
    "implement_commit_settle",
    "implement_completion",
    "implement_hook_route",
    "implementation_diff",
    "janitor",
    "janitor_admission",
    "janitor_failure_route",
    "janitor_refresh_route",
    "needs_human",
    "non_converged",
    "pr",
    "pr_refresh",
    "pr_refresh_head",
    "pr_refresh_merged_reconcile_route",
    "pr_route",
    "proof_grade",
    "proof_grade_route",
    "publish_draft",
    "publish_merged_reconcile_route",
    "recapture_route",
    "refresh_repair",
    "review_fix_admission",
    "review_fix_commit_settle",
    "review_fix_open_red_route",
    "verify_pr",
)

# The engine's node-lifecycle event names, matched by SUFFIX because the
# stream's name field is namespaced on some builds (`fabro.stage.started`)
# and bare on others. A FAILED stage ends the node exactly as a completed one
# does: when the failure is retryable the engine emits a fresh start event,
# which the start/completion count then reads as open again.
_STARTED_SUFFIXES: tuple[str, ...] = ("stage.started", "step.started")
_ENDED_SUFFIXES: tuple[str, ...] = ("stage.completed", "stage.failed", "step.finished")

# Where a record's event name lives, in the same descending preference the
# review-gate parser reads it in, so one stream shape is not read two ways.
_NAME_KEYS: tuple[str, ...] = ("event", "name", "event_name", "type")

_NODE_ID_KEY = "node_id"
_PETRI_ITEM_KEY = "item"
_PETRI_RECORD_KEY = "record"
_PETRI_BODY_KEY = "body"
_PETRI_SUBJECT_KEY = "subject"
_PETRI_NODE_KEY = "node"
_PETRI_NODE_NAME_KEY = "name"
_PETRI_NODE_KIND_KEY = "kind"
_PETRI_COMMAND_KIND = "attractor/command"


def open_command_node(*, events_json: str, timeouts: NodeTimeouts) -> OpenCommandNode | None:
    """The COMMAND node this stream shows open, with its resolved timeout; None if none.

    `timeouts` is this dispatch's own resolution, carried on the plan, so the
    bound reported here is the SAME number the rendered graph gave the node —
    a re-resolution could grade the host's window against one reading while
    the node ran under another, and neither record would show it.

    None covers both "no command node is open" and "the stream was not
    readable at all", which is the same conflation `LivenessSample` documents:
    an unreadable stream already lands as a no-signal `last_event_epoch` from
    the same read, and that no-signal sample is excluded from the quiet window
    entirely, so a bound taken from it could not have been acted on either way.
    """
    events = fabro_event_records_from_stdout(stdout=events_json)
    if events is None:
        return None
    unfinished: dict[str, int] = {}
    for event in events:
        node = _command_node_id(event=event)
        if node is None:
            continue
        name = _event_name(event=event)
        if name.endswith(_STARTED_SUFFIXES):
            unfinished[node] = unfinished.get(node, 0) + 1
        elif name.endswith(_ENDED_SUFFIXES):
            unfinished[node] = unfinished.get(node, 0) - 1
    candidates = [
        OpenCommandNode(node=node, timeout_seconds=float(timeouts.seconds_for(node=node)))
        for node in sorted(unfinished)
        if unfinished[node] > 0
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda candidate: candidate.timeout_seconds)


def updated_open_command_node(
    *,
    established: OpenCommandNode | None,
    events_json: str,
    timeouts: NodeTimeouts,
) -> OpenCommandNode | None:
    """Update an open command node from one incremental event read.

    A delta can omit a still-running command node entirely, so it cannot be
    interpreted as a complete stream. An unreadable delta and a readable delta
    with no lifecycle event both retain the established node; only an observed
    completion of that specific node clears it.
    """
    events = fabro_event_records_from_stdout(stdout=events_json)
    if events is None:
        return established
    current = open_command_node(events_json=events_json, timeouts=timeouts)
    if current is not None:
        return current
    if established is not None and any(
        _command_node_id(event=event) == established.node
        and _event_name(event=event).endswith(_ENDED_SUFFIXES)
        for event in events
    ):
        return None
    return established


def _command_node_id(*, event: dict[str, Any]) -> str | None:
    """This record's node id when it names a COMMAND node, else None.

    Read from the top level first and from `properties` second, because the
    engine puts `node_id` beside the envelope on its stage events while other
    event families nest their fields under `properties`. A node id that is not
    a command node is passed over here rather than filtered downstream, which
    is what keeps the start/completion counting free of every ACP node's own
    lifecycle events.
    """
    for source in (event, _properties(event=event)):
        value: object = source.get(_NODE_ID_KEY)
        if isinstance(value, str) and value in COMMAND_NODES:
            return value
    node = _petri_node(event=event)
    if node is None or node.get(_PETRI_NODE_KIND_KEY) != _PETRI_COMMAND_KIND:
        return None
    value = node.get(_PETRI_NODE_NAME_KEY)
    if isinstance(value, str) and value in COMMAND_NODES:
        return value
    return None


def _properties(*, event: dict[str, Any]) -> dict[str, object]:
    """This record's `properties` mapping, or an empty one when it carries none."""
    properties: object = event.get("properties")
    if isinstance(properties, dict):
        return cast("dict[str, object]", properties)
    return {}


def _petri_node(*, event: dict[str, Any]) -> dict[str, object] | None:
    """The Petri-era subject node, or None when this is not its envelope."""
    item: object = event.get(_PETRI_ITEM_KEY)
    if not isinstance(item, dict):
        return None
    item_mapping = cast("dict[str, object]", item)
    subject: object = item_mapping.get(_PETRI_SUBJECT_KEY)
    if not isinstance(subject, dict):
        return None
    subject_mapping = cast("dict[str, object]", subject)
    node: object = subject_mapping.get(_PETRI_NODE_KEY)
    if not isinstance(node, dict):
        return None
    return cast("dict[str, object]", node)


def _event_name(*, event: dict[str, Any]) -> str:
    """This record's event name, or the empty string when it names none.

    The empty string is the right absence here rather than None: it matches no
    lifecycle suffix, so a record with no readable name neither opens nor
    closes a node, which is what an unnamed record tells us.
    """
    for key in _NAME_KEYS:
        value: object = event.get(key)
        if isinstance(value, str):
            return value
    item: object = event.get(_PETRI_ITEM_KEY)
    if not isinstance(item, dict):
        return ""
    item_mapping = cast("dict[str, object]", item)
    record: object = item_mapping.get(_PETRI_RECORD_KEY)
    if not isinstance(record, dict):
        return ""
    record_mapping = cast("dict[str, object]", record)
    body: object = record_mapping.get(_PETRI_BODY_KEY)
    if not isinstance(body, dict):
        return ""
    body_mapping = cast("dict[str, object]", body)
    value = body_mapping.get("event")
    if isinstance(value, str):
        return value
    return ""
