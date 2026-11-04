"""The status-independent `relink-spec-tier` valve.

Relinking corrects the topic a held item's later ratification read follows. It
does not change the item lifecycle: the next intake or drain pass remains the
sole owner of release after a ratified topic and a fresh `stated` judgement.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, cast

from livespec_runtime.spec_stated import SpecStatedVerdict

from livespec_orchestrator_beads_fabro._store_comments import append_work_item_comment
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_gate import (
    item_comment_bodies,
)
from livespec_orchestrator_beads_fabro.commands._drive_valve_result import (
    valve_refusal,
    valve_success,
)
from livespec_orchestrator_beads_fabro.commands._plan_identity import canonical_plan_slug
from livespec_orchestrator_beads_fabro.commands._spec_change_tier import (
    SPEC_DIRNAME,
    SpecChangeTierDecision,
)
from livespec_orchestrator_beads_fabro.commands._spec_change_tier_record import (
    STAGE_RELINK,
    TierClauseProvenance,
    recorded_spec_change_tier,
    spec_change_tier_comment,
)

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.commands._dispatcher_invoker import InvokerIdentity
    from livespec_orchestrator_beads_fabro.commands._spec_change_tier_record import (
        RecordedSpecChangeTier,
    )
    from livespec_orchestrator_beads_fabro.types import StoreConfig, WorkItem

__all__: list[str] = [
    "RELINK_SPEC_TIER_ACTION",
    "RELINK_SPEC_TIER_STAGE",
    "proposal_topic_state",
    "relink_spec_tier",
]

RELINK_SPEC_TIER_ACTION = "relink-spec-tier"
RELINK_SPEC_TIER_STAGE = "human-valve-relink-spec-tier"
_COMMENT_MARKER = "livespec-spec-tier-relink"
_HISTORY_VERSION = re.compile(r"^v(\d+)$")
_REVISION_SUFFIX = "-revision.md"


def relink_spec_tier(
    *,
    repo: Path,
    config: StoreConfig,
    item: WorkItem,
    aid: str,
    topic: str,
    identity: InvokerIdentity,
) -> dict[str, Any]:
    """Replace a standing hold's linked topic after validating the filed proposal."""
    recorded = _held_record(config=config, item=item)
    if isinstance(recorded, dict):
        return recorded | {"action_id": aid}
    refusal = _topic_refusal(repo=repo, item=item, aid=aid, topic=topic)
    if refusal is not None:
        return refusal
    append_work_item_comment(
        path=config,
        work_item_id=item.id,
        body=_replacement_record(item=item, topic=topic, recorded=recorded),
    )
    append_work_item_comment(
        path=config,
        work_item_id=item.id,
        body=_relink_comment(
            actor=identity.invoker,
            previous=recorded.linked_proposal_topic,
            replacement=topic,
        ),
    )
    return valve_success(
        aid=aid,
        wid=item.id,
        stage=RELINK_SPEC_TIER_STAGE,
        status=item.status,
        assignee=item.assignee,
        msg=(
            f"Relinked {item.id}'s spec-change-tier hold from "
            f"{recorded.linked_proposal_topic!r} to {topic!r}; its status remains {item.status}."
        ),
    )


def _held_record(*, config: StoreConfig, item: WorkItem) -> RecordedSpecChangeTier | dict[str, Any]:
    """Return the held record, or the refusal that precedes every write."""
    comments = item_comment_bodies(path=config, work_item_id=item.id)
    recorded = recorded_spec_change_tier(comments=comments or ())
    if recorded is None or not recorded.is_spec_change or recorded.linked_proposal_topic is None:
        return valve_refusal(
            aid="",
            wid=item.id,
            err="not-held",
            msg=f"{RELINK_SPEC_TIER_ACTION} refused: {item.id} carries no spec-change-tier hold.",
        )
    return recorded


def _topic_refusal(*, repo: Path, item: WorkItem, aid: str, topic: str) -> dict[str, Any] | None:
    """Return why `topic` cannot replace a hold, or None when it names a usable proposal."""
    if canonical_plan_slug(text=topic) != topic:
        return valve_refusal(
            aid=aid,
            wid=item.id,
            err="non-canonical-topic",
            msg=(
                f"{RELINK_SPEC_TIER_ACTION} refused: {topic!r} is not a canonical proposed-change"
                " topic stem."
            ),
        )
    state = proposal_topic_state(spec_root=repo / SPEC_DIRNAME, topic=topic)
    if state == "unknown":
        return valve_refusal(
            aid=aid,
            wid=item.id,
            err="unknown-topic",
            msg=(
                f"{RELINK_SPEC_TIER_ACTION} refused: {topic!r} names no proposed change under"
                " proposed_changes or its history."
            ),
        )
    if state == "rejected":
        return valve_refusal(
            aid=aid,
            wid=item.id,
            err="rejected-topic",
            msg=(
                f"{RELINK_SPEC_TIER_ACTION} refused: {topic!r}'s latest revision record is"
                " reject, so the hold could not release."
            ),
        )
    return None


def proposal_topic_state(
    *, spec_root: Path, topic: str
) -> Literal["pending", "archived", "rejected", "unknown"]:
    """Read a proposal's current state from its open queue and versioned history."""
    if (spec_root / "proposed_changes" / f"{topic}.md").is_file():
        return "pending"
    revisions = _topic_revisions(spec_root=spec_root, topic=topic)
    if not revisions:
        return "unknown"
    latest = revisions[-1]
    if _decision(path=latest) == "reject":
        return "rejected"
    return "archived"


def _topic_revisions(*, spec_root: Path, topic: str) -> tuple[Path, ...]:
    """The topic's revision records in version order, only when the proposal exists there."""
    history = spec_root / "history"
    if not history.is_dir():
        return ()
    entries: list[tuple[int, Path]] = []
    for version in history.iterdir():
        match = _HISTORY_VERSION.fullmatch(version.name)
        proposal = version / "proposed_changes" / f"{topic}.md"
        revision = version / "proposed_changes" / f"{topic}{_REVISION_SUFFIX}"
        if match is not None and proposal.is_file():
            entries.append((int(match.group(1)), revision))
    return tuple(path for _, path in sorted(entries))


def _decision(*, path: Path) -> str | None:
    """Read the leading front-matter decision of one revision record."""
    if not path.is_file():
        return None
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    if not lines or lines[0] != "---":
        return None
    for line in lines[1:]:
        if line == "---":
            return None
        if line.startswith("decision:"):
            return line.removeprefix("decision:").strip()
    return None


def _relink_comment(*, actor: str, previous: str | None, replacement: str) -> str:
    """Render the durable, human-readable audit record for one successful replacement."""
    return "\n".join(
        (
            _COMMENT_MARKER,
            "",
            f"actor: {actor}",
            f"previous-topic: {previous}",
            f"replacement-topic: {replacement}",
        )
    )


def _replacement_record(*, item: WorkItem, topic: str, recorded: RecordedSpecChangeTier) -> str:
    """Copy the standing verdict and provenance into the replacement-topic record."""
    verdict = SpecStatedVerdict(
        kind=cast("Literal['stated', 'partial', 'unstated']", recorded.verdict_kind),
        stated_by=tuple(clause.heading for clause in recorded.named_clauses),
        generalization_target=recorded.generalization_target,
        rationale=recorded.rationale,
    )
    return spec_change_tier_comment(
        item_id=item.id,
        stage=STAGE_RELINK,
        decision=SpecChangeTierDecision(
            tier="spec-change",
            classification=cast(
                "Literal['bug', 'chore', 'feature', 'non_functional']", recorded.classification
            ),
            verdict=verdict,
            linked_proposal_topic=topic,
        ),
        spec_version=recorded.spec_version,
        digest=recorded.digest,
        provenance=TierClauseProvenance(
            selected=recorded.selected_clauses,
            named=recorded.named_clauses,
        ),
    )
