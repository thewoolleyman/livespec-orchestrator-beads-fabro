"""What one spec-change-tier cadence point learned, and how each answer is recorded.

Split out of `_spec_change_tier_gate`, which owns the classify-then-judge order.
This owns the four ways a cadence point ENDS — a standing record or attestation
settles it, a classification is recorded, the classification did not run, or the
ledger could not be read — and the outcome value they all return, so the gate's
file stays at the one decision it exists to make.

A STANDING HUMAN ATTESTATION BEATS A REUSABLE HELD RECORD and yields to a
reusable free one, which is already the answer the attestation would record. It
takes no model: the attested `stated` verdict is recorded as a `none` tier, once
per specification version.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro.commands._spec_change_tier import attested_decision
from livespec_orchestrator_beads_fabro.commands._spec_change_tier_record import (
    classification_did_not_run_comment,
    recorded_did_not_run_causes,
    recorded_spec_change_tier,
    reusable_spec_change_tier,
    spec_change_tier_comment,
)
from livespec_orchestrator_beads_fabro.commands._spec_tier_attestation import (
    standing_attestation,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from livespec_orchestrator_beads_fabro.commands._spec_change_tier import (
        SpecChangeTierDecision,
    )
    from livespec_orchestrator_beads_fabro.commands._spec_change_tier_record import (
        RecordedSpecChangeTier,
    )
    from livespec_orchestrator_beads_fabro.types import SpecSnapshot, WorkItem

__all__: list[str] = [
    "SpecChangeTierOutcome",
    "did_not_run_outcome",
    "recorded_outcome",
    "standing_outcome",
]


@dataclass(frozen=True, kw_only=True)
class SpecChangeTierOutcome:
    """What one cadence point learned, and whether anything was spent learning it.

    `recorded` is the classification that NOW STANDS against the item, which is
    `None` exactly when the classification did not run — and `cause` then names
    why. The two are reported together rather than as one optional, because a
    caller routing the item needs both: the tier to route by, and the cause to
    say in its own record that it routed without one.

    `reused` is reported rather than inferred from `recorded`, because a reused
    classification and a freshly-taken identical one are indistinguishable by
    value — and the cap the clause's economy rests on is about the SPEND, not the
    answer.
    """

    work_item_id: str
    recorded: RecordedSpecChangeTier | None
    cause: str | None = None
    reused: bool = False

    @property
    def is_spec_change(self) -> bool:
        """Whether the standing classification puts the item in the tier.

        `False` for an item whose classification did not run, which is the
        route-as-before direction the clause requires — not a claim that the
        item is free, which is what `recorded is None` says and what a caller
        records.
        """
        return self.recorded is not None and self.recorded.is_spec_change


def standing_outcome(
    *,
    item: WorkItem,
    stage: str,
    snapshot: SpecSnapshot,
    digest: str,
    comments: Sequence[str],
    append: Callable[..., None],
) -> SpecChangeTierOutcome | None:
    """The outcome a standing record or a standing attestation settles, else `None`.

    `None` means neither settles it and the classification has to be taken. A
    standing attestation beats a reusable HELD record and yields to a reusable
    free one, which is already the answer the attestation would record.
    """
    spec_version = str(snapshot.version)
    reused = reusable_spec_change_tier(comments=comments, spec_version=spec_version, digest=digest)
    cited = standing_attestation(item=item, comments=comments, spec_tree=snapshot.files)
    if cited is not None and (reused is None or reused.is_spec_change):
        return recorded_outcome(
            item=item,
            stage=stage,
            decision=attested_decision(heading=cited.heading.rstrip()),
            spec_version=spec_version,
            digest=digest,
            append=append,
        )
    if reused is None:
        return None
    return SpecChangeTierOutcome(work_item_id=item.id, recorded=reused, reused=True)


def recorded_outcome(
    *,
    item: WorkItem,
    stage: str,
    decision: SpecChangeTierDecision,
    spec_version: str,
    digest: str,
    append: Callable[..., None],
) -> SpecChangeTierOutcome:
    """Write one decision's record and report the classification it leaves standing.

    The outcome's `recorded` is read back out of the body just written rather
    than assembled beside it, so the classification a caller routes by is the
    one the record carries — a second construction is how the two come to differ
    while both look right.
    """
    body = spec_change_tier_comment(
        item_id=item.id,
        stage=stage,
        decision=decision,
        spec_version=spec_version,
        digest=digest,
    )
    append(body=body)
    return SpecChangeTierOutcome(
        work_item_id=item.id, recorded=recorded_spec_change_tier(comments=(body,))
    )


def did_not_run_outcome(  # noqa: PLR0913 - each argument is one field of the record it writes.
    *,
    item: WorkItem,
    stage: str,
    spec_version: str,
    digest: str,
    cause: str,
    comments: Sequence[str],
    append: Callable[..., None],
) -> SpecChangeTierOutcome:
    """Record that the classification did not run, unless this cause already stands."""
    if cause not in recorded_did_not_run_causes(comments=comments):
        append(
            body=classification_did_not_run_comment(
                item_id=item.id,
                stage=stage,
                spec_version=spec_version,
                digest=digest,
                cause=cause,
            )
        )
    return SpecChangeTierOutcome(work_item_id=item.id, recorded=None, cause=cause)
