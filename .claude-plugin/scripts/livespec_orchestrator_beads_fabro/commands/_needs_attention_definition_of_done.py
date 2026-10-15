"""The advisory-Definition-of-Done hygiene lane: a repairable `ready` item.

The Definition-of-Done-and-Proof-of-Done clause of `SPECIFICATION/contracts.md`
(v115) asks for this row in one sentence: "`needs-attention` SHOULD surface, as
hygiene facts, each `ready` item carrying an advisory Definition-of-Done finding,
so that it is repaired before a sandbox is spent on it."

WHY THIS CANNOT RIDE THE UNRUNNABLE-ACCEPTANCE ROW. That row fires on the shared
eligibility decision REFUSING an item. An advisory finding is forbidden from
refusing anything — the clause gives the judgement to the `dod_gate` node — so an
item carrying one is perfectly eligible, is dispatched in the ordinary way, and is
therefore silent on that lane and on every other lane in the snapshot: nothing is
stranded, nothing is held, nothing is aging past a bound. Without this row the
only way such an item becomes visible is the sandbox it spends discovering the
finding for itself.

WHY THE HANDOFF IS THE ITEM'S OWN RECORD AND NOT A DISPATCH. The row's stated
purpose is repair "before a sandbox is spent", so a handoff that spends the
sandbox defeats the row. Note the asymmetry with the unrunnable lane, which also
refuses a dispatch handoff but for the opposite reason: there the dispatch would
be REFUSED and read as a broken factory, while here it would SUCCEED and consume
exactly the resource the row exists to protect.

THE HELD LANE BESIDE IT ANSWERS THE OPPOSITE QUESTION. "Judged before
admission" and "Judged again before dispatch" each ask `needs-attention` to
list the items that judgement HELD, with the verdict's first remedy. Such an
item is not dispatchable at all, so it is silent on the advisory lane above by
construction — and silent on every other lane too, because nothing about it is
stranded, aging or claimed. The two lanes are therefore neighbours rather than
one row with a flag: they differ in urgency, in the remedy they print, and in
whether the item can still be dispatched while it stands.

WHY THE SUMMARY CARRIES THE FINDINGS RATHER THAN COUNTING THEM. The two
recognised forms want different edits — restating a test-existence assertion as
behaviour, or naming the governing scenario on the reference line — and a count
cannot tell an operator which. The findings are the reason the row exists, so they
travel with it.
"""

from __future__ import annotations

import shlex
from pathlib import Path
from typing import TYPE_CHECKING

from livespec_runtime.attention_item import AttentionItem, Handoff, SourceRef

from livespec_orchestrator_beads_fabro.commands._config import resolve_store_config
from livespec_orchestrator_beads_fabro.commands._dispatcher_definition_of_done_advisories import (
    advisory_definition_of_done_findings,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_gate import (
    held_judgement,
    item_comment_bodies,
)
from livespec_orchestrator_beads_fabro.commands._needs_attention_conformance import (
    ConformanceContext,
)
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt
from livespec_orchestrator_beads_fabro.errors import (
    ConnectionPrefixMissingError,
    LivespecConfigUnreadableError,
)

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_record import (
        RecordedJudgement,
    )
    from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "advisory_definition_of_done_items",
    "held_definition_of_done_items",
]


_READY_STATUS = "ready"
# Every lane this item can be held in. A held item rests where a mechanical
# finding would hold it — `pending-approval` or `backlog` for the admission
# hold, `ready` for the dispatch refusal — so keying the lane on one of them
# would make exactly one of the two holds invisible.
_HELDABLE_STATUSES = frozenset({"backlog", "pending-approval", "ready"})


def held_definition_of_done_items(
    *, project_root: Path, repo: str, items: list[WorkItem]
) -> list[AttentionItem]:
    """One fact per item a standing Definition-of-Done verdict is holding.

    The clause asks for this row twice in the same words — once for the
    pre-admission hold and once for the pre-dispatch refusal — and both are the
    SAME standing verdict read off the same record, so this is one lane rather
    than two. It takes NO judgement: an attention snapshot runs over the whole
    tenant, and a lane that could judge would spend a model call per item.

    MEDIUM, against the advisory lane's LOW. An advisory finding leaves the item
    dispatchable; a held one does not move at all until a human edits it, which
    is a stopped item rather than a repairable one.
    """
    resolved = attempt(
        action=lambda: resolve_store_config(cwd=project_root, work_items_arg=None),
        exceptions=(ConnectionPrefixMissingError, LivespecConfigUnreadableError),
    )
    if isinstance(resolved, AttemptFailure):
        # No connection, no recorded verdict to read: the lane reports nothing
        # rather than raising out of a snapshot composed from many lanes.
        return []
    config = resolved
    facts: list[AttentionItem] = []
    for item in items:
        if item.status not in _HELDABLE_STATUSES:
            continue
        bodies = item_comment_bodies(path=config, work_item_id=item.id)
        recorded = (
            None
            if bodies is None
            else held_judgement(item=item, repo=project_root, comments=bodies)
        )
        if recorded is not None:
            facts.append(
                _held_item(project_root=project_root, repo=repo, item=item, verdict=recorded)
            )
    return facts


def _held_item(
    *, project_root: Path, repo: str, item: WorkItem, verdict: RecordedJudgement
) -> AttentionItem:
    return ConformanceContext(project_root=project_root, repo=repo).candidate(
        id=f"hygiene:held-definition-of-done:{item.id}",
        kind="hygiene",
        urgency="medium",
        summary=(
            f"Work-item {item.id} is held by the Definition-of-Done judgement and"
            " will not be admitted or dispatched until its section changes."
            f" First remedy: {verdict.first_remedy}"
        ),
        source_ref=SourceRef(repo=repo, work_item=item.id),
        handoff=Handoff(
            kind="shell", command=_repair_command(project_root=project_root, item=item)
        ),
    )


def advisory_definition_of_done_items(
    *, project_root: Path, repo: str, items: list[WorkItem]
) -> list[AttentionItem]:
    """One fact per `ready` item the advisory half of the wall reports on."""
    return [
        _advisory_item(project_root=project_root, repo=repo, item=item, findings=findings)
        for item in items
        if item.status == _READY_STATUS
        for findings in (advisory_definition_of_done_findings(item=item, cwd=project_root),)
        if findings
    ]


def _advisory_item(
    *,
    project_root: Path,
    repo: str,
    item: WorkItem,
    findings: tuple[str, ...],
) -> AttentionItem:
    return ConformanceContext(project_root=project_root, repo=repo).candidate(
        # The orchestrator-owned `hygiene:<type>:<resource>` id form, keyed on the
        # work-item so the fact is STABLE across snapshots: a consumer tracking
        # whether this item still carries the finding keys on the id, and a
        # snapshot-scoped id would read as a new problem every pass.
        id=f"hygiene:advisory-definition-of-done:{item.id}",
        kind="hygiene",
        # LOW, deliberately. The item is dispatchable and nothing is stuck; the
        # cost of leaving it is one sandbox spent on a finding that was already
        # visible, which is real but is not an outage.
        urgency="low",
        summary=_summary(item=item, findings=findings),
        source_ref=SourceRef(repo=repo, work_item=item.id),
        handoff=Handoff(
            kind="shell", command=_repair_command(project_root=project_root, item=item)
        ),
    )


def _summary(*, item: WorkItem, findings: tuple[str, ...]) -> str:
    """The operator-facing one-liner, carrying every advisory finding verbatim."""
    named = " ".join(findings)
    return (
        f"Work-item {item.id} rests in {_READY_STATUS} carrying an ADVISORY"
        f" Definition-of-Done finding: {named} Repair it in the item's description"
        " before a sandbox is spent on it; the gate judges the same forms and will"
        " rest the run at needs-human if they survive."
    )


def _repair_command(*, project_root: Path, item: WorkItem) -> str:
    """Read the item's own record, which is the surface the repair edits."""
    wrapper = Path(__file__).parents[2] / "bin" / "context.py"
    return (
        f"python3 {shlex.quote(str(wrapper))} "
        f"--project-root {shlex.quote(str(project_root))} {shlex.quote(item.id)} --json"
    )
