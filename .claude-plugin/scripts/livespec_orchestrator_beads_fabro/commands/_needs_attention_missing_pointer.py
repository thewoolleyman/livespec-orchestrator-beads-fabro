"""The missing-Proof-of-Done-pointer hygiene lane.

The pointer clause of `SPECIFICATION/contracts.md` (v115) requires that "an item
in `acceptance` whose merging run has a `verified` record and whose description
has no pointer MUST likewise be surfaced by `needs-attention` as a hygiene fact
naming the item and the pull request, and `reconcile-merged` driven for that item
MUST write the missing pointer". This is that fact; the repair it names is the
re-accept arm of the reconcile valve.

WHY IT IS A LANE OF ITS OWN AND NOT A BRANCH OF THE STALE-POINTER LANE. That lane
reads a pointer and compares it against the pull request's latest record; it is
structurally blind to an item that has NO pointer, because the pointer is where it
gets the pull request number from. This lane has to find the pull request another
way — from the dispatch JOURNAL — so the two share a subject and share neither
their input nor their question.

THE PULL REQUEST COMES FROM THE JOURNAL, WHICH IS THE ONLY PLACE IT SURVIVES. A
parked item carries no merge audit (the audit is written by the CLOSE), and its
description carries no pointer by construction here. The terminal `outcome`
records in `tmp/fabro-dispatch-journal.jsonl` name the merged pull request for
each dispatch of the item, newest-wins — the same read, and the same rule, the
run-identifier attribution uses.

AN UNREADABLE PULL REQUEST IS NOT A MISSING POINTER, and neither is a pull request
carrying no `verified` record for the merging run. Both yield NO fact, because the
lane would otherwise manufacture a finding out of an absent observation — the same
rule the acceptance pass's own evidence legs obey, and the same one the sibling
stale-pointer lane obeys. The record must also be ATTRIBUTED to the merging
dispatch: a `verified` record published by another dispatch of the same item
describes another tree, so the pointer it would produce is not this merge's
provenance.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING, cast

from livespec_runtime.attention_item import AttentionItem, Handoff, SourceRef

from livespec_orchestrator_beads_fabro.commands._dispatcher_io import ShellCommandRunner
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_attribution import (
    merging_dispatch,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_evidence import (
    read_pull_request_records,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_pointer import (
    PROOF_OF_DONE_POINTER_TITLE,
    pointer_in,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_record import (
    VERDICT_VERIFIED,
    latest_proof_record,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_reflection_journal import (
    read_journal_records,
)
from livespec_orchestrator_beads_fabro.commands._needs_attention_conformance import (
    ConformanceContext,
)
from livespec_orchestrator_beads_fabro.commands._needs_attention_handoffs import (
    reconcile_merged_command,
)

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandRunner
    from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "missing_proof_pointer_items",
]

_ACCEPTANCE_STATUS = "acceptance"
_JOURNAL_PATH = Path("tmp") / "fabro-dispatch-journal.jsonl"


def missing_proof_pointer_items(
    *,
    project_root: Path,
    repo: str,
    items: list[WorkItem],
    runner: CommandRunner | None = None,
) -> list[AttentionItem]:
    """One fact per parked item whose verified record landed with no pointer."""
    active = ShellCommandRunner() if runner is None else runner
    journal = project_root / _JOURNAL_PATH
    records = read_journal_records(journal_path=journal)
    return [
        _missing_pointer_item(
            project_root=project_root, repo=repo, item=item, pull_request=pull_request
        )
        for item in items
        if item.status == _ACCEPTANCE_STATUS
        if pointer_in(description=item.description) is None
        for pull_request in (_merged_pull_request(records=records, work_item_id=item.id),)
        if pull_request is not None
        if _has_verified_record(
            project_root=project_root,
            journal=journal,
            item_id=item.id,
            pull_request=pull_request,
            runner=active,
        )
    ]


def _merged_pull_request(
    *, records: tuple[dict[str, object], ...], work_item_id: str
) -> int | None:
    """The pull request this item's newest terminal outcome merged, or None.

    LAST matching record wins, which is the rule every other journal reader here
    applies: a re-dispatched item carries one terminal per dispatch, and the
    pointer belongs to the merge that landed last.
    """
    found: int | None = None
    for record in records:
        payload = record.get("outcome")
        if not isinstance(payload, Mapping):
            continue
        outcome = cast("Mapping[str, object]", payload)
        if outcome.get("work_item_id") != work_item_id:
            continue
        number = outcome.get("pr_number")
        if isinstance(number, int):
            found = number
    return found


def _has_verified_record(
    *,
    project_root: Path,
    journal: Path,
    item_id: str,
    pull_request: int,
    runner: CommandRunner,
) -> bool:
    """Whether the merging dispatch published a `verified` record on that pull request."""
    records = read_pull_request_records(repo=project_root, pr_number=pull_request, runner=runner)
    if records is None:
        return False
    dispatch = merging_dispatch(work_item_id=item_id, fabro_run_id=None, journal_path=journal)
    latest = latest_proof_record(
        records=records, verdict=VERDICT_VERIFIED, run_ids=dispatch.run_ids
    )
    return latest is not None


def _missing_pointer_item(
    *, project_root: Path, repo: str, item: WorkItem, pull_request: int
) -> AttentionItem:
    return ConformanceContext(project_root=project_root, repo=repo).candidate(
        id=f"hygiene:missing-proof-pointer:{item.id}",
        kind="hygiene",
        urgency="medium",
        summary=(
            f"Work-item {item.id} rests in {_ACCEPTANCE_STATUS} with a verified Proof of"
            f" Done record on pull request #{pull_request} and NO"
            f" `{PROOF_OF_DONE_POINTER_TITLE}` section in its description, so the item"
            " carries no provenance of the merge its acceptance was judged against."
            " Re-run the acceptance pass with reconcile-merged, which writes the missing"
            " pointer."
        ),
        source_ref=SourceRef(repo=repo, work_item=item.id),
        handoff=Handoff(
            kind="shell",
            command=reconcile_merged_command(project_root=project_root, work_item=item.id),
        ),
    )
