"""The merged-reconcile ending, as the Dispatcher reads it and grades against it.

The merged-reconcile ending is how a run finishes when its publication had already
landed: `pr_refresh` found the publish branch gone and the pull request MERGED, or
`publish_draft` found the item's change already on the default branch. The run writes
no `verified` or `carried_forward` record for the merged head, so the ending is not
proof of anything by itself.

TWO READERS LIVE HERE because they are the two halves of one fact. The sandbox prints
one `LIVESPEC_MERGED_RECONCILE:` line, and `merged_reconcile_from_text` carries it into
the dispatch outcome, whose detail is the only place the Dispatcher can keep it once the
sandbox is gone. `merged_head_record` is what the acceptance pass then does with the
merged head: it selects the record that PROVES that head, and returns none when no
record does, so every `factory_captured` assertion reads as unevidenced rather than
passing on a `verified` record taken on some other head.

WHY THE ROUTE-CLASSIFIER LINE IS NOT THIS EVENT. The routing nodes print
`LIVESPEC_MERGED_RECONCILE_ROUTE:` on the same stream. The pattern requires the colon
and `pull_request=` directly after the sentinel, so a route line can never be read as
the event.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_record import (
    VERDICT_CARRIED_FORWARD,
    VERDICT_VERIFIED,
    ProofRecord,
    latest_proof_record,
)

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome

__all__: list[str] = [
    "MERGED_RECONCILE_SENTINEL",
    "MergedReconcile",
    "merged_head_record",
    "merged_reconcile_detail",
    "merged_reconcile_from_text",
    "record_published_head",
    "records_proving_head",
    "with_merged_reconcile",
]

MERGED_RECONCILE_SENTINEL = "LIVESPEC_MERGED_RECONCILE"

_NO_PROOF_HEAD = "none"
_HEAD_LABEL = "Publish-branch head:"
_FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
_EVENT_PATTERN = re.compile(
    "".join(
        (
            re.escape(MERGED_RECONCILE_SENTINEL),
            r": pull_request=(?P<pull_request>\d+) ",
            r"merge_commit=(?P<merge_commit>[0-9a-f]{40}) ",
            r"merged_head=(?P<merged_head>[0-9a-f]{40}) ",
            r"proof_head=(?P<proof_head>[0-9a-f]{40}|none) ",
            r"heads_equal=(?P<heads_equal>true|false)",
        )
    )
)


@dataclass(frozen=True, kw_only=True)
class MergedReconcile:
    """One merged-reconcile ending, as the sandbox reported it.

    `proof_head` is `None` when no `verified` or `carried_forward` record of the run
    exists, which is a different fact from a record naming a different head and so
    is not collapsed into an empty string.
    """

    pull_request: int
    merge_commit: str
    merged_head: str
    proof_head: str | None
    heads_equal: bool


def merged_reconcile_from_text(*, text: str) -> MergedReconcile | None:
    """The ending one run's output reports, or `None` when it reports none.

    `None` is the ordinary answer: nearly every run ends through `pr`. The LAST
    matching line wins, because a re-entered stage prints the line afresh.
    """
    matches = list(_EVENT_PATTERN.finditer(text))
    if not matches:
        return None
    found = matches[-1]
    proof_head = found.group("proof_head")
    return MergedReconcile(
        pull_request=int(found.group("pull_request")),
        merge_commit=found.group("merge_commit"),
        merged_head=found.group("merged_head"),
        proof_head=None if proof_head == _NO_PROOF_HEAD else proof_head,
        heads_equal=found.group("heads_equal") == "true",
    )


def merged_reconcile_detail(*, event: MergedReconcile) -> str:
    """The sentence the dispatch outcome detail carries for one ending."""
    proof = event.proof_head or "no verified or carried_forward record"
    return (
        f"merged-reconcile ending: pull request #{event.pull_request} merged as "
        f"{event.merge_commit} with merged head {event.merged_head}; the latest "
        f"verified or carried_forward head is {proof}; heads equal: "
        f"{'yes' if event.heads_equal else 'no'}"
    )


def with_merged_reconcile(
    *, outcome: DispatchOutcome, event: MergedReconcile | None
) -> DispatchOutcome:
    """The outcome carrying the merged-reconcile ending, in its detail and as a value.

    An outcome whose run reported no such ending passes through untouched.
    """
    if event is None:
        return outcome
    return replace(
        outcome,
        merged_reconcile=event,
        detail=f"{outcome.detail}; {merged_reconcile_detail(event=event)}",
    )


def record_published_head(*, body: str) -> str | None:
    """The one full head a record's PROSE declares, or `None` for none or several.

    Fence-aware for the reason the record reader is: a proof that prints another
    record's `Publish-branch head:` line is output, not a declaration.
    """
    declared: set[str] = set()
    fence: str | None = None
    for line in body.splitlines():
        delimiter = _FENCE.match(line)
        if delimiter is not None:
            fence = _fence_after(fence=fence, delimiter=delimiter.group(1))
            continue
        stripped = line.strip()
        if fence is None and stripped.casefold().startswith(_HEAD_LABEL.casefold()):
            value = stripped[len(_HEAD_LABEL) :].strip().strip("`").casefold()
            if _FULL_SHA.match(value) is not None:
                declared.add(value)
    return declared.pop() if len(declared) == 1 else None


def merged_head_record(
    *,
    records: Sequence[ProofRecord],
    run_ids: tuple[str, ...],
    merged_head: str,
) -> ProofRecord | None:
    """The record whose per-assertion verdicts may grade the merged head, or `None`.

    Only a record of this dispatch that NAMES the merged head proves it. A newest
    `verified` record on that head grades its own assertions. A `carried_forward`
    record naming it carries the proof of the `verified` record it points at, so the
    grades come from that record. `None` means no record proves the head, and the
    caller must read every assertion as unevidenced.
    """
    naming = [
        one
        for one in records
        if one.run_id in run_ids
        and one.verdict in (VERDICT_VERIFIED, VERDICT_CARRIED_FORWARD)
        and record_published_head(body=one.body) == merged_head
    ]
    if not naming:
        return None
    if naming[-1].verdict == VERDICT_VERIFIED:
        return naming[-1]
    return latest_proof_record(records=records, verdict=VERDICT_VERIFIED, run_ids=run_ids)


def _fence_after(*, fence: str | None, delimiter: str) -> str | None:
    if fence is None:
        return delimiter
    if delimiter[0] == fence[0] and len(delimiter) >= len(fence):
        return None
    return fence


def records_proving_head(
    *,
    records: Sequence[ProofRecord],
    run_ids: tuple[str, ...],
    merged_head: str,
) -> tuple[ProofRecord, ...]:
    """The records the factory leg may read after a merged-reconcile ending.

    Every `verified` and `carried_forward` record is withheld except the one that
    proves the merged head, so the leg's ordinary newest-`verified` choice can only
    land on a record of that head. Host and human records are untouched, because the
    ending says nothing about them.
    """
    proving = merged_head_record(records=records, run_ids=run_ids, merged_head=merged_head)
    anchors = (VERDICT_VERIFIED, VERDICT_CARRIED_FORWARD)
    kept = tuple(one for one in records if one.verdict not in anchors)
    return kept if proving is None else (*kept, proving)
