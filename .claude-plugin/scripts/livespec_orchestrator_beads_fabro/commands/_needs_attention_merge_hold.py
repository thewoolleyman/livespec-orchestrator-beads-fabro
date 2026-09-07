"""The one attention row a merge-held item produces, and the release it names.

A held item is `active` with no live dispatch lock and no run in flight: its run
already terminated green at the pr stage, its claim was reclaimed, and every
surface that reports on parked work has been taught to leave it alone. That is
the whole point of the ratified per-item merge hold — and it is also exactly how
a hold could go INVISIBLE, which the contract forbids in as many words. This
module is the counterweight: one row, standing for as long as the hold does.

Two properties are load-bearing rather than incidental.

It is ONE row per held item, not one per surface. The row is keyed
`hygiene:merge-hold:<work-item-id>`, so a second producer emitting the same fact
would collide on the id rather than quietly double-reporting a single hold.

It STANDS rather than fires. There is no dwell threshold and no staleness clock:
the hold is a maintainer's deliberate window, so the row is a statement that the
window is open, and it disappears on exactly two events — the hold is released,
or the item leaves `active`. Both are read from live state on every pass, so
nothing has to remember to retract it.

The pull request the summary names is read from the DISPATCH JOURNAL rather than
the forge. This surface composes a snapshot and must not depend on network
reachability to say that a hold stands; a hold whose pull request cannot be named
is still a hold, and reporting it without the number beats not reporting it.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import cast

from livespec_runtime.attention_item import AttentionItem, Handoff, SourceRef

from livespec_orchestrator_beads_fabro.commands._dispatcher_probe_cycle import journal_records
from livespec_orchestrator_beads_fabro.commands._needs_attention_conformance import (
    ConformanceContext,
)
from livespec_orchestrator_beads_fabro.commands._needs_attention_handoffs import drive_command
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "merge_hold_items",
]

_ACTIVE_STATUS = "active"
_JOURNAL_SUBPATH = ("tmp", "fabro-dispatch-journal.jsonl")


def merge_hold_items(
    *,
    project_root: Path,
    repo: str,
    items: list[WorkItem],
    held_work_item_ids: frozenset[str],
) -> list[AttentionItem]:
    """One attention row for every `active` item the merge hold currently holds."""
    pr_numbers = _journaled_pr_numbers(project_root=project_root)
    return [
        _merge_hold_item(
            project_root=project_root,
            repo=repo,
            work_item=item,
            pr_number=pr_numbers.get(item.id),
        )
        for item in items
        if item.status == _ACTIVE_STATUS and item.id in held_work_item_ids
    ]


def _merge_hold_item(
    *,
    project_root: Path,
    repo: str,
    work_item: WorkItem,
    pr_number: int | None,
) -> AttentionItem:
    action_id = f"set-merge-hold:{work_item.id}:off"
    return ConformanceContext(project_root=project_root, repo=repo).candidate(
        id=f"hygiene:merge-hold:{work_item.id}",
        kind="hygiene",
        urgency="medium",
        summary=_summary(work_item=work_item, pr_number=pr_number),
        source_ref=SourceRef(repo=repo, work_item=work_item.id),
        handoff=Handoff(
            kind="drive",
            command=drive_command(project_root=project_root, action_id=action_id),
            action_id=action_id,
        ),
    )


def _summary(*, work_item: WorkItem, pr_number: int | None) -> str:
    """Name the held pull request, or say plainly that the journal names none.

    The absent case is not silence. An item can be held before any dispatch of it
    ever opened a pull request, and a summary that simply omitted the subject
    would read as a rendering bug rather than as the state it is.
    """
    pull_request = (
        f"pull request #{pr_number}"
        if pr_number is not None
        else "no pull request named by the dispatch journal"
    )
    return (
        f"Merge hold stands on active work-item {work_item.id}: {pull_request} will not be "
        f"merged by any automated path until the hold is released with "
        f"set-merge-hold:{work_item.id}:off."
    )


def _journaled_pr_numbers(*, project_root: Path) -> dict[str, int]:
    """Newest-wins pull-request number per work-item, over the whole journal.

    Newest-wins is the convention every other per-item journal read here uses: a
    later record for one item cannot describe an earlier dispatch of it. Both
    record shapes are read — the pr number sits at the top level of some records
    and inside the `outcome` payload of others — because which one a held item
    left behind depends on which build dispatched it.
    """
    numbers: dict[str, int] = {}
    for record in journal_records(journal_path=project_root.joinpath(*_JOURNAL_SUBPATH)):
        for payload in _payloads(record=record):
            _record_pr_number(numbers=numbers, payload=payload)
    return numbers


def _payloads(*, record: Mapping[str, object]) -> tuple[Mapping[str, object], ...]:
    nested = record.get("outcome")
    if isinstance(nested, dict):
        return (record, cast("Mapping[str, object]", nested))
    return (record,)


def _record_pr_number(*, numbers: dict[str, int], payload: Mapping[str, object]) -> None:
    work_item_id = payload.get("work_item_id")
    pr_number = payload.get("pr_number")
    if (
        isinstance(work_item_id, str)
        and isinstance(pr_number, int)
        and not isinstance(pr_number, bool)
    ):
        numbers[work_item_id] = pr_number
