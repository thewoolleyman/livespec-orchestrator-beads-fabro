"""The measurements a surveyed dispatch claim is graded on.

The grading ladder is pure and lives one module over; this is where its inputs
are actually taken — from this host's lock files, from the forge, and from the
dispatch journal. The split is the usual one here: a decision that reached for
a subprocess itself could not be exercised across the fourteen holds without a
factory, a forge and a live lock, and those are exactly the conditions the
holds exist for.

EVERY READING IS THREE-VALUED, AND THAT IS THE WHOLE POINT OF THIS MODULE.
The helpers these replace are two-valued by design and correct for their own
callers: `live_dispatch_lock` collapses "no lock" and "a lock I could not
read" into `None`, because its caller is counting WIP slots and over-counting
is the safe direction. Here the same collapse would be a release: a claim whose
lock could not be read would report "no live owner" and the recovery would hand
a live dispatch's item back to the queue. So each observation below names the
measurement that failed instead of returning its negative answer.

THE JOURNAL READ IS THE ONE WHOSE ABSENCE IS NOT A FAILURE. A journal file that
does not exist is a checkout that has never dispatched, which is readable and
empty; a journal that exists and cannot be read is unavailable. The two are
different answers and `journal_records_or_none` keeps them apart, which is what
lets a history reading mean something narrower than "no history found".
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

from livespec_orchestrator_beads_fabro.commands._dispatcher_dispatch_lock import (
    LOCK_ABSENT,
    LOCK_DEAD,
    LOCK_LIVE,
    observe_dispatch_lock,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandRunner
from livespec_orchestrator_beads_fabro.commands._dispatcher_stranded_claim_grade import (
    FORGE_MERGED_PR,
    FORGE_NO_MERGED_PR,
    FORGE_UNOBSERVABLE,
    HISTORY_ABSENT_RUN_RELEASE,
    HISTORY_NO_PREDECESSOR,
    HISTORY_OTHER_OUTCOME,
    HISTORY_UNAVAILABLE,
    OWNER_LIVE,
    OWNER_NONE,
    OWNER_UNOBSERVABLE,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_stranded_claim_records import (
    STRANDED_CLAIM_RELEASE_STAGE,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_tenant_checkouts import (
    tenant_checkouts,
)
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt, parse_json

__all__: list[str] = [
    "DISPATCH_ID_JOURNAL_STAGE",
    "journal_records_or_none",
    "observe_merged_pull_request",
    "observe_owner_liveness",
    "observe_predecessor_history",
]

_GH_TIMEOUT_SECONDS = 120.0
_MERGED_STATE = "MERGED"

# The stage every dispatch writes at launch, which is what delimits one
# dispatch's journal segment from the next. Spelled here rather than imported
# for the reason `_dispatcher_recovery_release` gives about the same literal:
# its writer keeps it private, and recognising the row is all this needs.
DISPATCH_ID_JOURNAL_STAGE = "dispatch-id"

_STAGE_KEY = "stage"
_WORK_ITEM_KEY = "work_item_id"


def observe_owner_liveness(*, repo: Path, work_item_id: str) -> str:
    """Whether a live dispatch owns this item in ANY checkout on this host.

    EVERY lock location is read, and the answer is `none` only when every one
    of them was read and each is either absent or names a process that is not
    alive — the contract's own wording. A single unreadable location makes the
    whole reading `unobservable`, because "no live owner" is a claim about the
    complete set and one unread member leaves the set unestablished.

    The checkouts come from the tenant registry, exactly as the WIP-cap
    accounting resolves them: a worktree, a janitor checkout and a fresh clone
    share a tenant and never a filesystem root, so the invoking checkout's own
    lock path answers for its callers alone.
    """
    unobservable = False
    for checkout in tenant_checkouts(repo=repo):
        observed = observe_dispatch_lock(repo=checkout, work_item_id=work_item_id)
        if observed == LOCK_LIVE:
            return OWNER_LIVE
        if observed not in (LOCK_ABSENT, LOCK_DEAD):
            unobservable = True
    return OWNER_UNOBSERVABLE if unobservable else OWNER_NONE


def observe_merged_pull_request(
    *,
    repo: Path,
    runner: CommandRunner,
    work_item_id: str,
) -> str:
    """Whether the forge reports a merged pull request for this item.

    Asked of the forge rather than of the dispatch journal, because the
    question is whether the WORK landed and a journal row is this host's
    account of a dispatch it may have been killed partway through. The search
    is by work-item id, which is what the publish branch and every pull-request
    title carry.

    A non-zero exit, output that is not a JSON list, or an entry whose shape
    cannot be read all report `unobservable`. The clause makes that a hold
    rather than a negative: a forge outage must not license releasing a claim
    whose work has already merged, because the recovery for THAT item is
    `reconcile-merged` and a release would send it back through the factory.
    """
    result = runner.run(
        argv=[
            "gh",
            "pr",
            "list",
            "--state",
            "merged",
            "--search",
            work_item_id,
            "--json",
            "number,state,title",
            "--limit",
            "20",
        ],
        cwd=repo,
        timeout_seconds=_GH_TIMEOUT_SECONDS,
    )
    if result.exit_code != 0:
        return FORGE_UNOBSERVABLE
    parsed = parse_json(text=result.stdout)
    if not isinstance(parsed, list):
        return FORGE_UNOBSERVABLE
    entries = cast("list[object]", parsed)
    for entry in entries:
        if not isinstance(entry, dict):
            return FORGE_UNOBSERVABLE
        if cast("dict[str, Any]", entry).get("state") == _MERGED_STATE:
            return FORGE_MERGED_PR
    return FORGE_NO_MERGED_PR


def journal_records_or_none(*, journal_path: Path) -> tuple[Mapping[str, object], ...] | None:
    """Every record this journal holds, or None when it could not be read.

    An ABSENT file is the empty tuple rather than `None`: a checkout that has
    never dispatched has a readable, empty history, and reporting it as
    unavailable would hold every claim on every fresh checkout forever.
    """
    if not journal_path.exists():
        return ()
    read = attempt(
        action=lambda: journal_path.read_text(encoding="utf-8"),
        exceptions=(OSError, UnicodeDecodeError),
    )
    if isinstance(read, AttemptFailure):
        return None
    parsed = (parse_json(text=line) for line in read.splitlines())
    return tuple(cast("Mapping[str, object]", one) for one in parsed if isinstance(one, dict))


def observe_predecessor_history(
    *,
    records: tuple[Mapping[str, object], ...] | None,
    work_item_id: str,
) -> str:
    """Whether the item's PRECEDING dispatch ended in an absent-run release.

    The journal's launch rows for the item delimit its dispatches, so the
    newest row opens the dispatch whose claim is standing now and the row
    before it opens its predecessor. Whatever the journal recorded BETWEEN the
    two belongs to that predecessor, which is where its ending sits: a
    stranded-claim release is written after the dispatch died and before any
    successor announced itself.

    READ AS "the PRECEDING dispatch", never "ever released". A lifetime count
    of release rows agrees with this reading on a journal holding nothing else
    and disagrees on the sequence that actually occurs — a release, a human
    move, an unrelated dispatch, then a vanished run — where the clause calls
    for a release and a lifetime count would rest the item for a human. It is
    the same trap `_dispatcher_stall_disposition` records for its own repeat
    arm, and the journal already carries the discriminator.

    A journal that could not be read is `unavailable`, and so is one carrying
    NO launch row for the item: without a boundary there is no segment to read,
    and the dispatch most likely to have left a claim stranded is exactly the
    one whose record went missing. Exactly ONE launch row is a confirmed first
    dispatch, which has no predecessor to have released anything.
    """
    if records is None:
        return HISTORY_UNAVAILABLE
    starts = [
        index
        for index, record in enumerate(records)
        if _names(record=record, work_item_id=work_item_id, stage=DISPATCH_ID_JOURNAL_STAGE)
    ]
    if not starts:
        return HISTORY_UNAVAILABLE
    if len(starts) == 1:
        return HISTORY_NO_PREDECESSOR
    released = any(
        _names(record=record, work_item_id=work_item_id, stage=STRANDED_CLAIM_RELEASE_STAGE)
        for record in records[starts[-2] : starts[-1]]
    )
    return HISTORY_ABSENT_RUN_RELEASE if released else HISTORY_OTHER_OUTCOME


def _names(*, record: Mapping[str, object], work_item_id: str, stage: str) -> bool:
    return record.get(_STAGE_KEY) == stage and record.get(_WORK_ITEM_KEY) == work_item_id
