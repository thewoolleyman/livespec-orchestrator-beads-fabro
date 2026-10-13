"""Ledger-held plan handoff and supervisor-handoff authoring."""

from __future__ import annotations

from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro.commands._plan_next_action_validation import (
    NextActionRefusal,
)
from livespec_orchestrator_beads_fabro.commands._plan_tracked_write import (
    TrackedWriteRequest,
    commit_tracked_write,
)

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.commands._plan_next_action import NextAction
    from livespec_orchestrator_beads_fabro.types import StoreConfig

__all__: list[str] = [
    "append_handoff",
    "append_supervisor_handoff",
]


def append_handoff(  # noqa: PLR0913 -- kw-only writer; `operation_id` is the retry identity, independent of the entry it names.
    *,
    config: StoreConfig,
    epic_id: str,
    body: str,
    author: str,
    now: str,
    next_action: NextAction,
    operation_id: str | None = None,
) -> NextActionRefusal | None:
    """Append one handoff entry AND update the epic's typed next_action.

    Per contracts.md's "Ledger-held handoff persistence": the next action is
    not carried by the comment. The entry holds rationale, warnings and
    pointers; the pointer to the next step is the typed metadata written here
    in the same call, so a handoff can never record a next step the resume
    path cannot see. `author` doubles as the `last_session` identity, because
    the session that signs the entry is the one that wrote the pointer.

    A handoff is the ONE sanctioned write that consumes a unit of the result
    budget, and the comment and the pointer are both projections of the epoch
    transition `_plan_tracked_write` commits first — so neither can record a
    handoff the durable authority did not account for. `operation_id` names the
    identity a retry is recognised by; omitted, it is derived from this call's
    own fields.
    """
    outcome = commit_tracked_write(
        request=TrackedWriteRequest(
            config=config,
            epic_id=epic_id,
            action=next_action,
            author=author,
            now=now,
            is_handoff=True,
            body=body,
            operation_id=operation_id,
        )
    )
    return outcome if isinstance(outcome, NextActionRefusal) else None


def append_supervisor_handoff(  # noqa: PLR0913 -- kw-only writer; `operation_id` is the retry identity, independent of the entry it names.
    *,
    config: StoreConfig,
    epic_id: str,
    slug: str,
    body: str,
    now: str,
    next_action: NextAction,
    operation_id: str | None = None,
) -> NextActionRefusal | None:
    """Append one handoff entry authored as the plan's reserved supervisor literal.

    Per contracts.md's "Ledger-held handoff persistence": the supervisor
    role's `author:` field MUST be `<slug>-supervisor`, computed here rather
    than accepted as a caller-supplied string, mirroring `archive_thread`'s
    `author="plan-archive"` reservation.
    """
    return append_handoff(
        config=config,
        epic_id=epic_id,
        body=body,
        author=f"{slug}-supervisor",
        now=now,
        next_action=next_action,
        operation_id=operation_id,
    )
