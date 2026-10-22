"""The two PROJECTIONS of a plan epic's authority chain, and how to read them.

A transition is committed by one server statement — the close of the current
token — and everything else is a projection written AFTERWARDS: the epic's
`plan_epoch_chain` metadata cache, which tells a reader where to start walking,
and the fixed-first-line `plan-progress-event` ledger comment, which is the
durable obligation history `contracts.md` section "Required result, budget and
progress epoch" requires.

Neither projection is authority. A reader that disagrees with the chain
reconciles from the chain, never the other way round, which is exactly why a
lost projection write is a diagnosable partial write rather than a lost
transition.

TWO PROPERTIES AN EDITOR MUST NOT INVERT.

The cache is written with BOTH sub-keys on every write. `bd update --metadata`
merges at the TOP level but replaces a nested object WHOLESALE, so a write
carrying only one sub-key destroys the other — the same merge hazard
`next_action_metadata` carries its whole pointer against.

The progress comment carries the CANONICAL PAYLOAD as well as its readable
lines. A retry of an already-committed operation has to be answered with the
event that was recorded, and prose cannot be parsed back into one; a recovery
that reconstructed the event from the readable lines would answer the retry
with a transition nobody committed. `bd comments` offers no edit and no delete,
so what is written here is permanent — which is also why no payload value is
ever interpolated into a template-shaped token.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

from livespec_orchestrator_beads_fabro.commands._plan_epoch_payload import (
    TransitionPayload,
    parse_payload,
    render_payload,
)
from livespec_orchestrator_beads_fabro.commands._plan_timeline import plan_comment_body

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro._beads_client import BeadsClient

__all__: list[str] = [
    "CHAIN_METADATA_KEY",
    "CURRENT_FIELD",
    "LATEST_CLOSED_FIELD",
    "PLAN_PROGRESS_PREFIX",
    "ChainCache",
    "ProgressEvent",
    "chain_cache_metadata",
    "progress_event_body",
    "read_chain_cache",
    "read_progress_events",
    "write_chain_cache",
    "write_progress_event",
]

CHAIN_METADATA_KEY = "plan_epoch_chain"
LATEST_CLOSED_FIELD = "latest_closed"
CURRENT_FIELD = "current"

# The fixed first line `contracts.md` names. `read_timeline` filters on the
# handoff and scope prefixes only, so progress events never enter the plan
# timeline a resume reads for self-sufficiency findings.
PLAN_PROGRESS_PREFIX = "plan-progress-event"

_OPERATION_LABEL = "operation: "
_PAYLOAD_LABEL = "payload: "
# The two header fields `plan_comment_body` renders above every plan comment,
# read back through the same labelled-line reader the payload uses so one
# format is never parsed two ways.
_AUTHOR_LABEL = "author: "
_RECORDED_LABEL = "recorded: "
_METADATA_FIELD = "metadata"
_TEXT_FIELD = "text"


@dataclass(frozen=True, kw_only=True)
class ChainCache:
    """Where a reader starts walking: the latest closed token and the current one."""

    latest_closed: str | None
    current: str


@dataclass(frozen=True, kw_only=True)
class ProgressEvent:
    """One recorded transition, as a `plan-progress-event` comment carries it.

    `payload` is None when the comment's canonical line could not be parsed.
    That is kept apart from the comment's absence because a recovery owes the
    retry the event that was RECORDED, and an unparseable record is reportable
    rather than something to fill in.

    `author` and `recorded_at` are the comment's own two header fields, and they
    are here because the payload cannot carry either: it is rendered before the
    comment exists, while WHO committed a transition and WHEN is precisely what
    an evidenced causal supersession must establish about the derivation it
    supersedes. Both default to the empty string, so a comment found without
    them is a DEGRADED read rather than an unparseable event — an absent author
    is simply not one of the reserved derivation actors, which is the fail-closed
    answer.
    """

    operation_id: str
    payload: TransitionPayload | None
    author: str = ""
    recorded_at: str = ""


def chain_cache_metadata(
    *,
    existing_metadata: dict[str, Any],
    latest_closed: str | None,
    current: str,
) -> dict[str, Any]:
    """Overlay the whole cache object onto an epic's metadata."""
    metadata = dict(existing_metadata)
    metadata[CHAIN_METADATA_KEY] = {
        LATEST_CLOSED_FIELD: latest_closed,
        CURRENT_FIELD: current,
    }
    return metadata


def read_chain_cache(*, metadata: dict[str, Any]) -> ChainCache | None:
    """Read one epic's cache, or None when it names no chain.

    An ill-typed cache reads the same as an absent one: both mean there is no
    start point a walk may trust, and inventing one would point the walk at a
    token id nobody wrote.
    """
    value = metadata.get(CHAIN_METADATA_KEY)
    if not isinstance(value, dict):
        return None
    fields = cast("dict[str, Any]", value)
    current = fields.get(CURRENT_FIELD)
    latest_closed = fields.get(LATEST_CLOSED_FIELD)
    if not isinstance(current, str) or current == "":
        return None
    if not isinstance(latest_closed, str | None):
        return None
    return ChainCache(latest_closed=latest_closed, current=current)


def write_chain_cache(
    *,
    client: BeadsClient,
    epic_id: str,
    latest_closed: str | None,
    current: str,
) -> None:
    """Project the cache onto the epic, preserving every other metadata key."""
    record = client.show_issue(issue_id=epic_id)
    existing = record.get(_METADATA_FIELD)
    client.update_issue(
        issue_id=epic_id,
        metadata=chain_cache_metadata(
            existing_metadata=dict(cast("dict[str, Any]", existing))
            if isinstance(existing, dict)
            else {},
            latest_closed=latest_closed,
            current=current,
        ),
    )


def progress_event_body(*, payload: TransitionPayload, now: str) -> str:
    """Render one progress event's body: the readable lines, then the payload.

    The event kind is read off the PAYLOAD rather than taken as a parameter, so
    a re-projection performed by the reconciler cannot render a kind that
    differs from the one the transition committed.
    """
    state = payload.authority
    return "\n".join(
        (
            f"{_OPERATION_LABEL}{payload.operation_id}",
            f"event: {payload.event_kind}",
            f"epoch: {payload.prior_epoch} -> {payload.new_epoch}",
            f"prior-token: {payload.prior_token_id}",
            f"next-token: {payload.next_token_id}",
            f"original-deadline: {state.original_deadline}",
            f"max-handoffs: {state.max_handoffs}",
            f"consumed-handoffs: {state.consumed_handoffs}",
            f"recorded: {now}",
            f"{_PAYLOAD_LABEL}{render_payload(payload=payload)}",
        )
    )


def write_progress_event(
    *,
    client: BeadsClient,
    epic_id: str,
    payload: TransitionPayload,
    author: str,
    now: str,
) -> None:
    """Append the committed transition's progress event to the epic."""
    client.add_comment(
        issue_id=epic_id,
        body=plan_comment_body(
            prefix=PLAN_PROGRESS_PREFIX,
            author=author,
            now=now,
            body=progress_event_body(payload=payload, now=now),
        ),
    )


def read_progress_events(*, client: BeadsClient, epic_id: str) -> tuple[ProgressEvent, ...]:
    """Read every progress event on one epic, oldest first."""
    events: list[ProgressEvent] = []
    for comment in client.list_comments(issue_id=epic_id):
        text = comment.get(_TEXT_FIELD)
        if not isinstance(text, str) or not text.startswith(PLAN_PROGRESS_PREFIX):
            continue
        event = _parse_event(text=text)
        if event is not None:
            events.append(event)
    return tuple(events)


def _parse_event(*, text: str) -> ProgressEvent | None:
    operation_id = _labelled_value(text=text, label=_OPERATION_LABEL)
    if operation_id is None:
        return None
    payload_text = _labelled_value(text=text, label=_PAYLOAD_LABEL)
    payload = None if payload_text is None else parse_payload(text=payload_text)
    return ProgressEvent(
        operation_id=operation_id,
        payload=payload,
        author=_labelled_value(text=text, label=_AUTHOR_LABEL) or "",
        recorded_at=_labelled_value(text=text, label=_RECORDED_LABEL) or "",
    )


def _labelled_value(*, text: str, label: str) -> str | None:
    for line in text.splitlines():
        if line.startswith(label):
            value = line.removeprefix(label).strip()
            if value != "":
                return value
    return None
