"""The plan-epic timeline, and the handoff self-sufficiency findings over it.

The plan operation asks which action to take on every resume. That question is
right for an operator sitting at the terminal and wrong for the overseer
daemon's context-threshold restart, which re-enters the same thread with
nobody present to answer. This module supplies the reading half of the rule:
whether the session carries the unattended marker, and what the timeline of
handoff and scope comments holds. The decision half moved to
`_plan_next_action.py`, which reads the epic's typed `next_action` metadata.

`recorded_next_actions` survives that move as a HUMAN-READABILITY probe only.
It is no longer the resume authority — a wrapped prose line truncated the
instruction twice on a live tenant while the resume reported one confident
action — and `handoff_timeline_findings` is the only caller left: it reports
whether a newest handoff still reads as self-sufficient to a person.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro.effects import IsoDatetimeParseFailure, parse_iso_datetime
from livespec_orchestrator_beads_fabro.store import read_work_item_comments

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from livespec_orchestrator_beads_fabro.store import WorkItemComment
    from livespec_orchestrator_beads_fabro.types import StoreConfig

__all__: list[str] = [
    "HANDOFF_KIND",
    "PLAN_HANDOFF_PREFIX",
    "PLAN_SCOPE_PREFIX",
    "SCOPE_KIND",
    "UNATTENDED_ENV_VAR",
    "PlanTimelineEntry",
    "handoff_timeline_findings",
    "is_unattended_session",
    "plan_comment_body",
    "read_timeline",
    "recorded_next_actions",
]

UNATTENDED_ENV_VAR = "LIVESPEC_PLAN_UNATTENDED"
HANDOFF_KIND = "handoff"
SCOPE_KIND = "scope"
PLAN_HANDOFF_PREFIX = "plan-handoff-entry"
PLAN_SCOPE_PREFIX = "plan-scope-event"

_TRUTHY = frozenset({"1", "on", "true", "yes"})
_NEXT_ACTION_MARKER = "next action"
_MARKER_ORNAMENTS = "-*# "
_WORK_ITEM_ID_PATTERN = re.compile(r"\b[a-z][a-z0-9]*(?:-[a-z0-9]+)+(?:\.\d+)?\b")
_EXPECTED_HEADER_SHAPE = "`plan-handoff-entry|plan-scope-event`, `author: `, `timestamp: `"
_AUTHOR_LINE_INDEX = 1
_TIMESTAMP_LINE_INDEX = 2
_MIN_HEADER_LINES = 2
_FULL_HEADER_LINES = 3


@dataclass(frozen=True, kw_only=True)
class PlanTimelineEntry:
    """One parsed plan-epic timeline entry."""

    kind: str
    body: str
    author: str
    created_at: str


def is_unattended_session(*, env: Mapping[str, str]) -> bool:
    """Report whether this session carries the unattended-resume marker."""
    return env.get(UNATTENDED_ENV_VAR, "").strip().lower() in _TRUTHY


def recorded_next_actions(*, body: str) -> tuple[str, ...]:
    """Return every next action a handoff body names in prose, in written order.

    A marker line that names nothing after its colon records no action: it is
    counted as absent rather than as an empty instruction.

    This is a readability probe, NOT the resume authority — see the module
    docstring. `resume_directive` reads the epic's typed `next_action`
    metadata and never this.
    """
    actions: list[str] = []
    for line in body.splitlines():
        marker_line = line.strip().lstrip(_MARKER_ORNAMENTS).strip()
        if not marker_line.lower().startswith(_NEXT_ACTION_MARKER):
            continue
        _, separator, action = marker_line.partition(":")
        if not separator or not action.strip():
            continue
        actions.append(action.strip())
    return tuple(actions)


def plan_comment_body(*, prefix: str, author: str, now: str, body: str) -> str:
    """Render one plan-epic comment: the three-line header, a blank line, the body.

    The RENDER lives beside `_parse_entry`'s read of the same header, because the
    two are one format and a format whose halves sit in different modules drifts.
    Every plan comment goes through here — handoff entries, scope events, and the
    archive leg's own entry — so `read_timeline` can never meet a header shape
    this function does not produce.
    """
    return f"{prefix}\nauthor: {author}\ntimestamp: {now}\n\n{body}"


def handoff_timeline_findings(*, entries: Sequence[PlanTimelineEntry]) -> tuple[str, ...]:
    """Return ledger-timeline handoff self-sufficiency findings."""
    findings: list[str] = []
    for index, entry in enumerate(entries, start=1):
        if entry.body.strip() == "":
            findings.append(f"timeline entry {index} is empty")
        if entry.author.strip() == "":
            findings.append(f"timeline entry {index} is unattributed")
    findings.extend(_newest_handoff_findings(entries=entries))
    return tuple(findings)


def read_timeline(*, config: StoreConfig, epic_id: str) -> tuple[PlanTimelineEntry, ...]:
    """Read plan-epic handoff and scope comments oldest-first, each kind-labelled."""
    entries: list[PlanTimelineEntry] = []
    for index, comment in enumerate(
        read_work_item_comments(path=config, work_item_id=epic_id), start=1
    ):
        if not comment.text.startswith((PLAN_HANDOFF_PREFIX, PLAN_SCOPE_PREFIX)):
            continue
        entries.append(
            _parse_entry(
                comment=comment,
                comment_ref=_comment_ref(epic_id=epic_id, comment=comment, index=index),
            )
        )
    return tuple(entries)


def _newest_handoff_findings(*, entries: Sequence[PlanTimelineEntry]) -> list[str]:
    handoffs = [entry for entry in entries if entry.kind == HANDOFF_KIND]
    if not handoffs:
        return ["no handoff entry on the plan timeline"]
    newest = handoffs[-1]
    actions = recorded_next_actions(body=newest.body)
    findings: list[str] = []
    if len(actions) != 1:
        findings.append(f"newest handoff records {len(actions)} next actions, not exactly one")
    if _WORK_ITEM_ID_PATTERN.search(newest.body) is None:
        findings.append("newest handoff names no work-item id")
    return findings


def _parse_entry(*, comment: WorkItemComment, comment_ref: str) -> PlanTimelineEntry:
    header, _, body = comment.text.partition("\n\n")
    lines = header.splitlines()
    if len(lines) < _MIN_HEADER_LINES:
        raise _format_error(comment_ref=comment_ref, detail="missing author line")
    created_at = _created_at(lines=lines, comment=comment)
    return PlanTimelineEntry(
        kind=HANDOFF_KIND if lines[0] == PLAN_HANDOFF_PREFIX else SCOPE_KIND,
        body=body,
        author=lines[_AUTHOR_LINE_INDEX].removeprefix("author: "),
        created_at=created_at,
    )


def _created_at(*, lines: list[str], comment: WorkItemComment) -> str:
    if len(lines) >= _FULL_HEADER_LINES and lines[_TIMESTAMP_LINE_INDEX].startswith("timestamp: "):
        header_created_at = lines[_TIMESTAMP_LINE_INDEX].removeprefix("timestamp: ")
        if _is_parseable_timestamp(value=header_created_at):
            return header_created_at
    return comment.created_at or ""


def _is_parseable_timestamp(*, value: str) -> bool:
    parsed = parse_iso_datetime(text=value.replace("Z", "+00:00"))
    return not isinstance(parsed, IsoDatetimeParseFailure)


def _comment_ref(*, epic_id: str, comment: WorkItemComment, index: int) -> str:
    if comment.comment_id is not None:
        return comment.comment_id
    return f"{epic_id} comment #{index}"


def _format_error(*, comment_ref: str, detail: str) -> ValueError:
    problem = f"Malformed plan timeline comment {comment_ref}: {detail}"
    expected = f"expected plan timeline header {_EXPECTED_HEADER_SHAPE}, then a blank line and body"
    message = f"{problem}; {expected}"
    return ValueError(message)
