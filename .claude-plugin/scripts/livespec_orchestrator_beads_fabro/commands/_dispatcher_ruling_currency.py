"""Which operator ruling currently governs one item's next dispatch, read from its comments.

`SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback priority"
→ "Recovery from the failed run's preserved work" → "A ruled seed names the tree a
released item's next dispatch starts from" makes the ITEM'S LEDGER COMMENTS the
only source recovery routing may read a ruling from: "Recovery routing MUST read
current rulings from the item's ledger comments and never from a host's journal
alone, so a ruling written from one checkout governs a dispatch from any other."
The journal record a ruling also leaves is the writing host's own account of the
act, and a dispatch from another checkout has never seen it.

PURE, AND THE ONE READER OF A RULING. A ruling is "CURRENT from the instant its
comment is written until the item carries a `...-consumed` comment naming it, or
until a later seed ruling or fresh ruling for the same item replaces it; the
latest ruling of either kind governs." Recovery routing asks this module and
nothing else which ruling governs, so that sentence is read in one place rather
than once per kind.

Three properties an editor must not invert. The LATEST ruling decides, whichever
kind it is, and it is graded for consumption AFTER it is chosen: a consumed ruling
is not current, and an earlier unconsumed ruling does not become current again
behind it, because the later one replaced it. A consumed comment is matched to
its ruling by the KIND of its marker and the ruling's INSTANT — a seed ruling and
a fresh ruling written in the same second must not consume each other. And the
instant is searched for among the consumed comment's field VALUES rather than
under a field name, because the clause says only that the comment "names the
ruling's instant, the dispatch id and the run id": a reader keyed on one field
name would stop recognising consumption the day the writer spells it another way,
and a ruling that is never recognised as consumed governs every dispatch for ever.

THE PARSE KEEPS THE FIRST OCCURRENCE OF EVERY FIELD BUT THE INSTANT, which it takes
from the body's last line. The writers render `instant` last and `reason` is
operator prose, so a reason spanning lines can carry a line shaped like another
field; a last-occurrence parse would let it overwrite the real one. A comment that
opens with the marker but lacks a field is inert rather than half-read, because a
ruling assembled from whichever fields happened to parse would route a dispatch on
a tree nobody ruled.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from livespec_orchestrator_beads_fabro.commands._dispatcher_fresh_ruling import (
    FRESH_RULING_MARKER,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_seed_ruling import (
    SEED_RULING_MARKER,
    SeedRuling,
)

__all__: list[str] = [
    "FRESH_RULING_CONSUMED_MARKER",
    "SEED_RULING_CONSUMED_MARKER",
    "FreshRuling",
    "current_ruling",
]

SEED_RULING_CONSUMED_MARKER = f"{SEED_RULING_MARKER}-consumed"
FRESH_RULING_CONSUMED_MARKER = f"{FRESH_RULING_MARKER}-consumed"

_SEPARATOR = ": "
_INSTANT_PREFIX = "instant: "
_SEED_FIELDS = ("work-item", "preservation-ref", "commit-sha", "invoker", "reason")
_FRESH_FIELDS = ("work-item", "invoker", "reason")


@dataclass(frozen=True, kw_only=True)
class FreshRuling:
    """One operator instruction that the item's next dispatch start fresh."""

    work_item_id: str
    invoker: str
    reason: str
    instant: str


def current_ruling(*, comments: Sequence[str]) -> SeedRuling | FreshRuling | None:
    """The ruling that governs, from the item's comments oldest first, or `None`.

    `None` is any of: no ruling was ever written, the latest ruling has been
    consumed, or the comments carry only inert text.
    """
    latest: SeedRuling | FreshRuling | None = None
    for text in comments:
        latest = _seed_ruling(comment=text) or _fresh_ruling(comment=text) or latest
    if isinstance(latest, SeedRuling):
        consumed = SEED_RULING_CONSUMED_MARKER
    elif isinstance(latest, FreshRuling):
        consumed = FRESH_RULING_CONSUMED_MARKER
    else:
        return None
    if any(
        _names_instant(comment=text, marker=consumed, instant=latest.instant) for text in comments
    ):
        return None
    return latest


def _fields(*, comment: str, marker: str, required: tuple[str, ...]) -> dict[str, str] | None:
    """The body's fields, or `None` when it is not this marker's or lacks a required one."""
    lines = comment.splitlines()
    if not lines or lines[0] != marker or not lines[-1].startswith(_INSTANT_PREFIX):
        return None
    fields: dict[str, str] = {}
    for line in lines[1:-1]:
        name, separator, value = line.partition(_SEPARATOR)
        if separator:
            _ = fields.setdefault(name, value)
    instant = lines[-1].removeprefix(_INSTANT_PREFIX)
    if not instant or any(not fields.get(name) for name in required):
        return None
    fields["instant"] = instant
    return fields


def _seed_ruling(*, comment: str) -> SeedRuling | None:
    """Decode one seed-ruling body; any other comment, or a malformed one, is inert."""
    fields = _fields(comment=comment, marker=SEED_RULING_MARKER, required=_SEED_FIELDS)
    if fields is None:
        return None
    return SeedRuling(
        work_item_id=fields["work-item"],
        preservation_ref=fields["preservation-ref"],
        commit_sha=fields["commit-sha"],
        invoker=fields["invoker"],
        reason=fields["reason"],
        instant=fields["instant"],
    )


def _fresh_ruling(*, comment: str) -> FreshRuling | None:
    """Decode one fresh-ruling body; any other comment, or a malformed one, is inert."""
    fields = _fields(comment=comment, marker=FRESH_RULING_MARKER, required=_FRESH_FIELDS)
    if fields is None:
        return None
    return FreshRuling(
        work_item_id=fields["work-item"],
        invoker=fields["invoker"],
        reason=fields["reason"],
        instant=fields["instant"],
    )


def _names_instant(*, comment: str, marker: str, instant: str) -> bool:
    """Whether this comment is a `marker` consumption naming exactly this instant."""
    lines = comment.splitlines()
    if not lines or lines[0] != marker:
        return False
    return any(line.partition(_SEPARATOR)[2] == instant for line in lines[1:])
