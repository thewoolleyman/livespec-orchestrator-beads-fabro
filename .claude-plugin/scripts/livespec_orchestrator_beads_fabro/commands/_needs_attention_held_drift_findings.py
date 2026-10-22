"""The attention lane that lists every drift finding held past the queue cap.

The third fact derived from the detection-coverage anchor, beside the two
staleness facts its sibling composes. The queue-cap clause requires it by name:
when the cap is reached, further findings "MUST be HELD on the
detection-coverage anchor with their identities" and "`needs-attention` MUST
list the held findings with a handoff naming `revise`".

WHY `revise` AND NOT A DETECTOR. A held finding is not a detection run that has
not happened; it is a finding the pass HAS made and cannot file, because the
open-proposal queue is full. Running the drift pass again would change nothing
— the cap is still reached — so the handoff names the one operation that
actually clears the hold: `revise`, which adjudicates an open proposal and so
frees a slot. A handoff naming `capture-spec-drift` here would send the
operator to re-run a detector whose findings are already in hand.

A FINDING THAT HAS SINCE BEEN FILED IS NO LONGER HELD, which is why this lane
subtracts the filed set rather than listing every record on the anchor. The
hold records are APPEND-ONLY — the anchor is a ledger row and comments cannot
be edited or deleted — so a later pass that files a previously held finding
leaves its hold record standing for ever. A lane that read the records alone
would carry that finding in the operator's inbox permanently, with no act that
could ever clear it.

ONE FACT FOR THE WHOLE SET, not one per finding. The remedy is identical for
every held finding (adjudicate an open proposal), the cap is a repository
property, and a per-finding fact would put five rows in the inbox that one
`revise` pass clears together. The identities and their merges ride the
summary, so nothing is lost: the operator can see which merges are holding the
frontier.
"""

from __future__ import annotations

import shlex
from typing import TYPE_CHECKING

from livespec_runtime.attention_item import AttentionItem, Handoff, SourceRef

from livespec_orchestrator_beads_fabro.commands._drift_run_held import held_findings
from livespec_orchestrator_beads_fabro.commands._drift_run_proposals import (
    filed_finding_identities,
)
from livespec_orchestrator_beads_fabro.commands._needs_attention_conformance import (
    ConformanceContext,
)

if TYPE_CHECKING:
    from pathlib import Path

    from livespec_orchestrator_beads_fabro.types import StoreConfig

__all__: list[str] = [
    "HELD_DRIFT_FINDINGS_KEY",
    "held_drift_finding_items",
]

HELD_DRIFT_FINDINGS_KEY = "held-drift-findings"

_REVISE_OPERATION = "revise"


def held_drift_finding_items(
    *,
    project_root: Path,
    spec_root: Path,
    repo: str,
    config: StoreConfig,
    anchor: str | None,
) -> list[AttentionItem]:
    """One fact listing every still-held drift finding, or nothing when none is."""
    filed = filed_finding_identities(spec_root=spec_root)
    still_held = [
        one for one in held_findings(path=config, anchor=anchor) if one.identity not in filed
    ]
    if not still_held:
        return []
    listed = ", ".join(f"{one.identity} (merge {one.merge}, {one.kind})" for one in still_held)
    summary = (
        f"{len(still_held)} drift finding(s) are HELD for {repo} because the open "
        f"drift-origin proposal queue stands at dispatcher.drift_proposal_queue_cap: "
        f"{listed}. A held finding is not disposed of, so the drift coverage frontier "
        f"does not advance past its merge. Adjudicate an open proposal through revise "
        f"to free a queue slot; re-running the drift pass changes nothing while the cap "
        f"is reached."
    )
    return [
        ConformanceContext(project_root=project_root, repo=repo).candidate(
            id=f"hygiene:{HELD_DRIFT_FINDINGS_KEY}:{repo}",
            kind="hygiene",
            urgency="medium",
            summary=summary,
            source_ref=SourceRef(repo=repo),
            handoff=Handoff(kind="shell", command=_revise_command(project_root=project_root)),
        )
    ]


def _revise_command(*, project_root: Path) -> str:
    """The handoff an operator runs to clear a hold: `revise`, in this repository."""
    invocation = f"livespec:{_REVISE_OPERATION}"
    return (
        f"cd {shlex.quote(str(project_root))} && codex exec {shlex.quote(invocation)} < /dev/null"
    )
