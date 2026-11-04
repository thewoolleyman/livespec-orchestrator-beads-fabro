"""Shared predicates for advertised and enforced drive valves."""

from __future__ import annotations

from typing import TYPE_CHECKING

from returns.unsafe import unsafe_perform_io

from livespec_orchestrator_beads_fabro.commands._dispatcher_policy_overrides import (
    effective_admission_policy,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_policy_settings import (
    DEFAULT_ADMISSION_POLICY,
)

if TYPE_CHECKING:
    from pathlib import Path

    from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "awaits_dispatcher_admission",
    "can_approve_item",
]

_PENDING_APPROVAL = "pending-approval"
_AUTO_ADMISSION = "auto"
_MANUAL_ADMISSION = "manual"


def can_approve_item(*, item: WorkItem, cwd: Path) -> bool:
    """Return whether the item rests at the approve valve awaiting a human (advertising)."""
    return item.status == _PENDING_APPROVAL and _admission_policy(item=item, cwd=cwd) == (
        _MANUAL_ADMISSION
    )


def awaits_dispatcher_admission(*, item: WorkItem, cwd: Path) -> bool:
    """Return whether the Dispatcher, not a human approve valve, owns admission."""
    return item.status == _PENDING_APPROVAL and _admission_policy(item=item, cwd=cwd) == (
        _AUTO_ADMISSION
    )


def _admission_policy(*, item: WorkItem, cwd: Path) -> str:
    """The item's admission policy, falling back to `manual` when unreadable.

    Both predicates above answer a plain yes/no about which valve owns the
    item, so the unreadable-config fallback is spelled once here. `manual` is
    the safe end: a policy that cannot be read offers the item to a human
    rather than claiming the Dispatcher already owns it.

    ⚠️ `unsafe_perform_io` is not ceremony. `IOResult.value_or` returns
    `IO[value]`, not the value — without it both comparisons below are against
    an `IO` wrapper and are False for EVERY item.
    """
    return unsafe_perform_io(
        effective_admission_policy(item=item, cwd=cwd).value_or(DEFAULT_ADMISSION_POLICY)
    )
