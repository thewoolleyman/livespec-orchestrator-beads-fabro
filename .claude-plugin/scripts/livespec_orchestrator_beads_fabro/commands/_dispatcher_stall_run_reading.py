"""What a cancelled run's own record says about where it was and what it published.

`SPECIFICATION/contracts.md` section "Dispatcher progress watchdog" -> "The
cancel record" requires a `stalled-no-progress` cancel to name "the stage the
run was executing" and, "when the run's event stream records a completed
`publish_draft`", also "the pull request and the head that the LAST completed
`publish_draft` of the run pushed, read from the run's own record". This module
is that reading, and it is PURE: the cancel site hands it the stream and the
record text it has already read, so every arm is exercisable without a factory.

TWO SOURCES ANSWER THE STAGE QUESTION AND THEY ARE NOT INTERCHANGEABLE. The
clause names both: the stage is "the node whose start event has no completion
event or, between nodes, the target of the edge its last succeeded node's
outcome selected". A run cancelled INSIDE a node is the first; a run cancelled
in the gap between two nodes has no open node at all, and only the selected edge
says where it was headed. Reporting the open node for a between-nodes
cancellation is impossible — there is none — but reporting the selected edge for
an OPEN node is perfectly possible and would be wrong: it names the node the run
has already entered as the one it is about to enter, which reads identically to
a correct record. So the open-node reading is asked FIRST and the edge is the
fallback, never a cross-check.

THE OPEN SET IS COUNTED RATHER THAN SEQUENCED, for the reason
`_dispatcher_open_command_node` gives: `parse_last_event_epoch` records that
events may arrive out of order, so a reader keying on the last lifecycle event
it saw would answer differently for one reordering of the same stream — and
counting is also what reads a RETRY correctly, since a retried node emits a
fresh start after its failure. Unlike that module this one counts EVERY node and
not only the command nodes, because the question here is "where was this run",
which an ACP node answers as well as a script node does.

WHY THE PUBLICATION IS READ FROM THE NODE'S OWN MARKER AND NEVER FROM ORIGIN.
The clause is explicit: the head "MUST NOT be read from origin at cancel time,
because origin's branch may have moved since". A re-dispatch's `publish_draft`,
a later `pr_refresh`, or an operator can each move the branch between the push
and the cancel, so an origin read answers a question about the branch NOW and
reports it as a fact about what THIS run put there. The node therefore declares
what it pushed on its own stderr, under `PUBLISHED_MARKER`, and this reads that
declaration back.

AND WHY AN UNREADABLE HEAD IS A FIRST-CLASS ANSWER rather than an omission. The
clause says that when the head "cannot be read, the record MUST say so rather
than omit it", and the difference is operational: an omitted head is exactly
what a record written by a build predating this reading looks like, so a reader
cannot tell "this run published nothing" from "this run published and nobody
recorded where". The first supports a plain re-dispatch and the second does not,
because a plain dispatch reclaims the publish branch and would delete the head
the resume exists to finish. `StallPublication` therefore carries
`published_head=None` as a MEASURED absence beside a pull request that WAS read,
and the record renderer states it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, cast

from livespec_orchestrator_beads_fabro.commands._fabro_port_events import (
    fabro_event_records_from_stdout,
)

__all__: list[str] = [
    "PUBLISHED_MARKER",
    "PUBLISH_DRAFT_NODE",
    "StallPublication",
    "executing_stage",
    "last_publish_draft_publication",
]

# The graph node whose completion is what makes a publication readable at all.
PUBLISH_DRAFT_NODE = "publish_draft"

# The marker `publish_draft` prints on stderr once it has pushed, naming the
# head it pushed and the pull request that head is published on. ONE literal
# shared by the producer — the node's own script in the committed graph — and
# this consumer, exactly as `NON_CONVERGED_MARKER` is.
PUBLISHED_MARKER = "LIVESPEC_PUBLISH_DRAFT_PUBLISHED"

# The marker's two fields, each matched on its own so a marker line carrying
# only one of them yields that one rather than neither.
#
# `head` is matched as a FULL object name and never as an abbreviation: git
# prints short names in its own push output, and a short name cannot anchor a
# resume — the resume clause compares a record's head against the forge's, which
# answers in full names, so a seven-character reading would report a mismatch
# for the very head it names.
_PUBLISHED_RE = re.compile(rf"{PUBLISHED_MARKER}:[^\n]*?\bhead=(?P<head>[0-9a-f]{{40,64}})\b")
_PULL_REQUEST_RE = re.compile(
    rf"{PUBLISHED_MARKER}:[^\n]*?\bpull_request=#?(?P<pull_request>\d+)\b"
)

# The engine's node-lifecycle event names, matched by SUFFIX because the
# stream's name field is namespaced on some builds (`fabro.stage.started`) and
# bare on others — and a FAILED stage ends a node exactly as a completed one
# does, since a retryable failure is followed by a fresh start event.
_STARTED_SUFFIX = "stage.started"
_ENDED_SUFFIXES: tuple[str, ...] = ("stage.completed", "stage.failed")
_COMPLETED_SUFFIX = "stage.completed"

# Where a record's event name lives, in the same descending preference the
# review-gate parser reads it in, so one stream shape is not read two ways.
_NAME_KEYS: tuple[str, ...] = ("event", "name", "event_name", "type")
_NODE_ID_KEY = "node_id"
_EDGE_SELECTED_SUFFIX = "edge.selected"
_TO_NODE_KEY = "to_node"


@dataclass(frozen=True, kw_only=True)
class StallPublication:
    """What one run's LAST completed `publish_draft` put on the publish branch.

    `pull_request` is the pull request that publication opened or pushed onto.
    `published_head` is the object name it pushed, or `None` when the run's own
    record does not carry one — a measured absence the renderer states, never an
    omission (see the module docstring).
    """

    pull_request: int | None
    published_head: str | None


def executing_stage(*, events_json: str) -> str | None:
    """The node this run was executing, or `None` when its record names none.

    `None` covers an unreadable stream, a stream with no lifecycle events, and a
    run whose every node has ended with no edge selected after it. All three
    mean the same thing to the cancel record: the run's own record does not say
    where it was, which the record states rather than guesses at.
    """
    events = fabro_event_records_from_stdout(stdout=events_json)
    if events is None:
        return None
    open_node = _open_node(events=events)
    if open_node is not None:
        return open_node
    return _last_selected_target(events=events)


def last_publish_draft_publication(
    *, events_json: str, record_text: str
) -> StallPublication | None:
    """The publication of this run's last completed `publish_draft`, or `None`.

    `None` means the run completed NO `publish_draft`, which is a different fact
    from a completed one whose head could not be read: the first says there is
    no publication to name, the second says there is one and the record cannot
    say where. Collapsing them advises a plain dispatch — which reclaims the
    publish branch — for a run that had already published.

    `record_text` is whatever the run's record carries: the cancel site passes
    the event stream and the engine's inspect output together, because the
    marker travels on the node's stderr and which of the two surfaces carries it
    depends on the engine build. Nothing here reads origin.

    The LAST marker in that text wins, which is what makes a run that published
    twice report its second publication: the markers are appended in the order
    the node emitted them, so the last is the newest.
    """
    events = fabro_event_records_from_stdout(stdout=events_json)
    if events is None or not _completed_publish_draft(events=events):
        return None
    heads = _PUBLISHED_RE.findall(record_text)
    pull_requests = _PULL_REQUEST_RE.findall(record_text)
    return StallPublication(
        pull_request=int(pull_requests[-1]) if pull_requests else None,
        published_head=heads[-1] if heads else None,
    )


def _completed_publish_draft(*, events: tuple[dict[str, Any], ...]) -> bool:
    """Whether the stream records a COMPLETED `publish_draft`.

    A FAILED `publish_draft` is deliberately not one: it may have pushed and may
    not, so a record naming a publication the node did not finish would assert
    something its own evidence does not establish.
    """
    return any(
        _node_id(event=event) == PUBLISH_DRAFT_NODE
        and _event_name(event=event).endswith(_COMPLETED_SUFFIX)
        for event in events
    )


def _open_node(*, events: tuple[dict[str, Any], ...]) -> str | None:
    """The node whose starts outnumber its endings, or `None` when none does.

    A tie is broken by NAME rather than by stream position, for the ordering
    reason in the module docstring: no two nodes of this graph run at once, so
    more than one open node is a reading artifact, and a positional tiebreak
    would answer differently for one reordering of the same records.
    """
    unfinished: dict[str, int] = {}
    for event in events:
        node = _node_id(event=event)
        if node is None:
            continue
        name = _event_name(event=event)
        if name.endswith(_STARTED_SUFFIX):
            unfinished[node] = unfinished.get(node, 0) + 1
        elif name.endswith(_ENDED_SUFFIXES):
            unfinished[node] = unfinished.get(node, 0) - 1
    still_open = sorted(node for node in unfinished if unfinished[node] > 0)
    return still_open[0] if still_open else None


def _last_selected_target(*, events: tuple[dict[str, Any], ...]) -> str | None:
    """The target of the last edge this run's record shows selected.

    Taken by stream POSITION because an edge selection is the one reading whose
    order is its meaning — the clause asks for the edge the LAST succeeded node
    selected — and because, unlike the open-node count, there is no
    reorder-tolerant form of "most recent" available here.
    """
    target: str | None = None
    for event in events:
        if not _event_name(event=event).endswith(_EDGE_SELECTED_SUFFIX):
            continue
        value: object = _properties(event=event).get(_TO_NODE_KEY)
        if isinstance(value, str) and value.strip():
            target = value
    return target


def _node_id(*, event: dict[str, Any]) -> str | None:
    """This record's node id, read top level first and from `properties` second.

    The engine puts `node_id` beside the envelope on its stage events while
    other event families nest their fields under `properties`, so both are read
    — in that order, which is the order `_dispatcher_open_command_node` reads
    them in, so one stream shape is not read two ways.
    """
    for source in (event, _properties(event=event)):
        value: object = source.get(_NODE_ID_KEY)
        if isinstance(value, str) and value.strip():
            return value
    return None


def _properties(*, event: dict[str, Any]) -> dict[str, object]:
    """This record's `properties` mapping, or an empty one when it carries none."""
    properties: object = event.get("properties")
    if isinstance(properties, dict):
        return cast("dict[str, object]", properties)
    return {}


def _event_name(*, event: dict[str, Any]) -> str:
    """This record's event name, or the empty string when it names none.

    The empty string is the right absence rather than `None`: it matches no
    suffix, so a record with no readable name neither opens nor closes a node
    and selects no edge, which is exactly what an unnamed record tells us.
    """
    for key in _NAME_KEYS:
        value: object = event.get(key)
        if isinstance(value, str):
            return value
    return ""
