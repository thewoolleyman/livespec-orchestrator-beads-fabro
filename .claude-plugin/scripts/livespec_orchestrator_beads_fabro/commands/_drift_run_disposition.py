"""What the drift run DOES with one finding: file it, or hold it past the cap.

The per-finding half of the pass, split from `_drift_run` by cohesion: that
module enumerates a scope and judges each merge, while this one answers the one
question the contract attaches to `dispatcher.drift_proposal_queue_cap` — "is
there room in the open queue for this proposal, and if not, where does the
finding go instead".

THE LADDER'S ORDER IS LOAD-BEARING, and each rung answers a question the next
one cannot.

ALREADY FILED comes first, because the frontier rule asks whether every finding
of a merge IS filed and not whether this pass filed it. A finding filed by an
earlier pass — or by a pass that held it and a later pass that filed it — is
filed, and asking the cap about it first would hold a finding whose proposal
already rests in the queue, stopping the frontier for ever behind work that is
done.

THE CAP comes second and is read as `>=` rather than `>`, because the contract
says the hold begins "when the count of open drift-origin proposals is AT"
the cap. A `>` reading admits one proposal beyond the cap on every pass, which
is the off-by-one that looks correct in every test with a cap of one.

ALREADY HELD IS A RUNG *INSIDE* THE CAP RUNG, never ahead of it, and the
difference is the whole of this module's correctness. A hold is a decision about
THIS PASS's queue and not a property of the finding, so a ladder that answered
"already held" before consulting the cap could never file a held finding again:
once an identity had a hold record, every later pass reported it held however
empty the queue had since become. Measured on cap 1 with one open drift-origin
proposal and one `unstated` merge — the first pass held the finding and the
contiguous frontier answered None; the open proposal was then adjudicated into
`history/vNNN/proposed_changes/`, leaving the queue at 0 of 1; and the next pass
still reported it held with the frontier still None. That is PERMANENT: the
contract's frontier rule says a merge carrying a held finding stops the frontier
"until every finding of it is filed", so the frontier wedges at that merge for
ever while every later tick re-judges a growing backlog at one model call per
merge and files nothing. Both this module's own account of the ladder and
`_needs_attention_held_drift_findings`'s subtraction of the filed set describe
the promotion that rung made unreachable.

So the cap rung decides, and the already-held reading only decides what to do
once it has: at the cap a hold already on record is REPORTED without being
re-recorded, because the record is append-only and the root reconcile timer
fires every ten minutes — a pass that re-recorded each held finding would bury
the anchor under copies of one hold, and the operator surface would list it once
per copy. Below the cap the same finding FILES, which is the act the hold was
waiting on.

A FINDING NOBODY COULD HOLD IS IN NEITHER TUPLE, and that is the fail-closed
answer rather than an oversight. `record_held_finding` returns False when no
anchor is committed, and a finding that is neither filed nor held has not been
disposed of — so the merge carrying it is unprocessed and the frontier stops
there. Reporting it as held would advance the frontier past a finding that
exists nowhere at all.

BOTH TREE READINGS ARE RE-TAKEN PER FINDING, not once for the scope, because
this module writes into the very directories it reads. Two merges of one scope
can carry one identity — the same behaviour re-landed — and a filed set taken
before the loop would file it twice under one name, the second write silently
replacing the first. The open-queue count has the mirror problem: a count taken
before the loop lets a scope file its way past the cap, one proposal per merge,
while every individual decision looks correct.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro.commands._drift_run_held import (
    held_findings,
    record_held_finding,
)
from livespec_orchestrator_beads_fabro.commands._drift_run_proposals import (
    drift_proposal_document,
    file_drift_proposal,
    filed_finding_identities,
    open_drift_origin_proposals,
    target_spec_files,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence
    from pathlib import Path

    from livespec_orchestrator_beads_fabro.commands._drift_run_findings import DriftFinding
    from livespec_orchestrator_beads_fabro.types import StoreConfig

__all__: list[str] = [
    "Disposition",
    "DispositionContext",
    "dispose_findings",
]


@dataclass(frozen=True, kw_only=True)
class DispositionContext:
    """Everything the disposition of one finding is decided against.

    `anchor` is the committed detection-coverage anchor, and `config` the
    tenant connection, each None when the repository commits none. Either
    absence makes a hold IMPOSSIBLE rather than merely unrecorded, which is
    what stops the frontier at a merge whose finding nothing could dispose of.
    """

    spec_root: Path
    spec_tree: dict[str, str]
    config: StoreConfig | None
    anchor: str | None
    cap: int
    author: str
    now: Callable[[], str]


@dataclass(frozen=True, kw_only=True)
class Disposition:
    """Where one merge's findings went.

    A finding in NEITHER tuple is one nothing could dispose of; the pass reads
    that as an unprocessed merge, which is what stops the frontier.
    """

    filed: tuple[str, ...]
    held: tuple[str, ...]


def dispose_findings(
    *, findings: Sequence[DriftFinding], context: DispositionContext
) -> Disposition:
    """File each finding, or hold it on the anchor when the queue is at the cap."""
    filed: list[str] = []
    held: list[str] = []
    for finding in findings:
        _dispose_one(finding=finding, context=context, filed=filed, held=held)
    return Disposition(filed=tuple(filed), held=tuple(held))


def _dispose_one(
    *,
    finding: DriftFinding,
    context: DispositionContext,
    filed: list[str],
    held: list[str],
) -> None:
    """One finding down the ladder the module docstring describes."""
    if finding.identity in filed_finding_identities(spec_root=context.spec_root):
        filed.append(finding.identity)
        return
    if len(open_drift_origin_proposals(spec_root=context.spec_root)) >= context.cap:
        _hold_one(finding=finding, context=context, held=held)
        return
    _ = file_drift_proposal(
        spec_root=context.spec_root,
        finding=finding,
        document=drift_proposal_document(
            finding=finding,
            author=context.author,
            now=context.now(),
            targets=target_spec_files(spec_tree=context.spec_tree, finding=finding),
        ),
    )
    filed.append(finding.identity)


def _hold_one(*, finding: DriftFinding, context: DispositionContext, held: list[str]) -> None:
    """Hold ONE finding the queue has no room for, re-recording nothing.

    Reached only with the queue AT the cap, which is what keeps the hold a
    decision about this pass's queue rather than a property the finding keeps
    for ever — see the module docstring for what answering this question first
    costs.

    A finding ALREADY on record is reported held without a second record,
    because the anchor is append-only. A finding nothing could hold is in
    neither tuple, which stops the frontier at its merge.
    """
    if finding.identity in _held_identities(context=context):
        held.append(finding.identity)
        return
    if record_held_finding(path=context.config, anchor=context.anchor, finding=finding):
        held.append(finding.identity)


def _held_identities(*, context: DispositionContext) -> frozenset[str]:
    return frozenset(
        one.identity for one in held_findings(path=context.config, anchor=context.anchor)
    )
