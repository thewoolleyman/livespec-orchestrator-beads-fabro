"""The attention rows for a held item whose generalization target was ratified elsewhere.

The autonomy-tier bullet of `SPECIFICATION/contracts.md` asks `needs-attention` to
surface, under the existing `hygiene` kind as `hygiene:spec-tier-relink:<work-item-id>`,
an item held because its linked topic has no ratifying revision record while a
LATER ratified revision amended its generalization-target heading under a
different topic. The hold clears only on the EXACT linked topic, and nothing else
tells a seat that the stem it predicted at filing has gone stale; this row is that
signal, and the handoff names the `relink-spec-tier` route that replaces it.

THE ROW READS THE SAME `standing_hold` THE WALL'S REFUSAL DOES, so the two surfaces
can never name different candidates for one item. It takes NO judgement and writes
nothing: naming a candidate neither releases the hold nor relinks the item, and the
handoff is a `drive` action a person or an agent session chooses to run.

IT IS ONE ROW PER ITEM, keyed on the work-item id so the fact is stable across
snapshots, and it stands for exactly as long as the candidate does — a relink makes
the linked topic the ratified one, the hold stops being `unratified-topic`, and the
row is simply absent on the next pass with nothing to retract.

ONLY HELDABLE LANES ARE READ. A held item rests out of `ready`, so an `active` or
parked-for-acceptance item carries no hold a relink could serve, and reading its
comments would spend a ledger read per item for a row that cannot exist.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from livespec_runtime.attention_item import AttentionItem, Handoff, SourceRef

from livespec_orchestrator_beads_fabro.commands._dispatcher_spec_commitments import (
    ratified_proposal_topics,
)
from livespec_orchestrator_beads_fabro.commands._needs_attention_conformance import (
    ConformanceContext,
)
from livespec_orchestrator_beads_fabro.commands._needs_attention_handoffs import drive_command
from livespec_orchestrator_beads_fabro.commands._spec_change_tier import SPEC_DIRNAME
from livespec_orchestrator_beads_fabro.commands._spec_change_tier_wall import standing_hold

if TYPE_CHECKING:
    from pathlib import Path

    from livespec_orchestrator_beads_fabro.commands._spec_change_tier_hold import SpecChangeHold
    from livespec_orchestrator_beads_fabro.commands._spec_change_tier_relink_candidate import (
        RelinkCandidate,
    )
    from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

__all__: list[str] = ["spec_tier_relink_items"]

_HELDABLE_STATUSES = frozenset({"backlog", "pending-approval", "ready"})


def spec_tier_relink_items(
    *,
    project_root: Path,
    repo: str,
    items: list[WorkItem],
    config: StoreConfig,
) -> list[AttentionItem]:
    """One fact per held item that carries a relink candidate."""
    spec_root = project_root / SPEC_DIRNAME
    ratified = ratified_proposal_topics(spec_root=spec_root)
    facts: list[AttentionItem] = []
    for item in items:
        if item.status not in _HELDABLE_STATUSES:
            continue
        hold = standing_hold(
            item=item, config=config, spec_root=spec_root, ratified_topics=ratified
        )
        candidate = None if hold is None else hold.relink_candidate
        if hold is not None and candidate is not None:
            facts.append(_row(project_root=project_root, repo=repo, hold=hold, candidate=candidate))
    return facts


def _row(
    *, project_root: Path, repo: str, hold: SpecChangeHold, candidate: RelinkCandidate
) -> AttentionItem:
    action_id = f"relink-spec-tier:{hold.work_item_id}:{candidate.topic}"
    return ConformanceContext(project_root=project_root, repo=repo).candidate(
        id=f"hygiene:spec-tier-relink:{hold.work_item_id}",
        kind="hygiene",
        urgency="medium",
        summary=(
            f"Work-item {hold.work_item_id} is held for its linked proposed-change topic"
            f" {hold.linked_proposal_topic}, which has no ratifying revision record, while"
            f" proposed-change topic {candidate.topic} amended its generalization-target"
            f" heading at specification version {candidate.spec_version}. If that topic carries"
            f" this item's behaviour, relink the hold with {action_id}; naming it does not"
            " release the hold."
        ),
        source_ref=SourceRef(repo=repo, work_item=hold.work_item_id),
        handoff=Handoff(
            kind="drive",
            command=drive_command(project_root=project_root, action_id=action_id),
            action_id=action_id,
        ),
    )
