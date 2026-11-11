"""The identity shared by repository preflight and pre-dispatch reuse.

The first dispatch after a spec-change-tier release must not reuse the
clause-form Definition-of-Done verdict taken before the ratified revision.
Both callers therefore recognise that release from the tier receipt history and
key their next taking on the whole specification tree.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_spec_identity import (
    SpecIdentity,
    spec_identity_for_governing,
    whole_tree_identity,
)

if TYPE_CHECKING:
    from pathlib import Path

    from livespec_orchestrator_beads_fabro.commands._dod_governing_heading import (
        GoverningHeadingVerdict,
    )
    from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = ["identity_for_dod_taking", "released_spec_change_tier"]

_SPEC_CHANGE_TIER_MARKER = "livespec-spec-change-tier"
_TIER_PREFIX = "tier: "
_SPEC_CHANGE_TIER = "spec-change"
_NO_TIER = "none"


def identity_for_dod_taking(
    *,
    item: WorkItem,
    cwd: Path,
    comments: Sequence[str],
    governing: GoverningHeadingVerdict | None,
    release_of_held_spec_tier: bool | None = None,
) -> SpecIdentity:
    """Return the input identity that this host taking must compare.

    An explicit value lets the release valve preserve its known decision. The
    ordinary preflight and pre-dispatch callers derive it from append-only tier
    receipts, so a launcher and a later dispatcher agree on the same bytes.
    """
    released = (
        released_spec_change_tier(comments=comments)
        if release_of_held_spec_tier is None
        else release_of_held_spec_tier
    )
    if released:
        return whole_tree_identity(cwd=cwd)
    return spec_identity_for_governing(item=item, cwd=cwd, governing=governing)


def released_spec_change_tier(*, comments: Sequence[str]) -> bool:
    """Whether the latest free tier receipt follows a spec-change-tier hold."""
    released = False
    for body in reversed(comments):
        tier = _tier_from(body=body)
        if tier == _NO_TIER:
            released = True
        elif tier == _SPEC_CHANGE_TIER:
            return released
    return False


def _tier_from(*, body: str) -> str | None:
    """Read the tier field from one tier receipt, ignoring unrelated riders."""
    lines = tuple(line.strip() for line in body.splitlines())
    if not lines or lines[0] != _SPEC_CHANGE_TIER_MARKER:
        return None
    return next(
        (line.removeprefix(_TIER_PREFIX) for line in lines if line.startswith(_TIER_PREFIX)),
        None,
    )
