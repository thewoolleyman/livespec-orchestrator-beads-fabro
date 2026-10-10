"""Ledger-held plan handoff and supervisor-handoff authoring."""

from __future__ import annotations

from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro._beads_client import make_beads_client
from livespec_orchestrator_beads_fabro.commands._plan_next_action import (
    LEGACY_TRACKING,
    NextAction,
    NextActionRefusal,
    set_next_action,
)
from livespec_orchestrator_beads_fabro.commands._plan_next_action_validation import (
    validate_next_action,
)
from livespec_orchestrator_beads_fabro.commands._plan_timeline import (
    PLAN_HANDOFF_PREFIX,
    plan_comment_body,
)

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.types import StoreConfig

__all__: list[str] = [
    "append_handoff",
    "append_supervisor_handoff",
]


def append_handoff(
    *,
    config: StoreConfig,
    epic_id: str,
    body: str,
    author: str,
    now: str,
    next_action: NextAction,
) -> NextActionRefusal | None:
    """Append one handoff entry AND update the epic's typed next_action.

    Per contracts.md's "Ledger-held handoff persistence": the next action is
    not carried by the comment. The entry holds rationale, warnings and
    pointers; the pointer to the next step is the typed metadata written here
    in the same call, so a handoff can never record a next step the resume
    path cannot see. `author` doubles as the `last_session` identity, because
    the session that signs the entry is the one that wrote the pointer.
    """
    refusal = validate_next_action(
        action=next_action,
        epic_id=epic_id,
        legacy_tracking=LEGACY_TRACKING,
    )
    if refusal is not None:
        return refusal
    client = make_beads_client(config=config)
    client.add_comment(
        issue_id=epic_id,
        body=plan_comment_body(prefix=PLAN_HANDOFF_PREFIX, author=author, now=now, body=body),
    )
    return set_next_action(
        config=config,
        epic_id=epic_id,
        action=next_action,
        session=author,
        now=now,
    )


def append_supervisor_handoff(
    *,
    config: StoreConfig,
    epic_id: str,
    slug: str,
    body: str,
    now: str,
    next_action: NextAction,
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
    )
