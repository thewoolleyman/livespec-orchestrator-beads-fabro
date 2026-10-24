"""Session-performable disposition of a plan child.

The archive gate refuses while any child of the plan epic is undisposed, and
sessions have treated re-parenting or closing a child as a maintainer call. The
two together deadlock the archive for any epic that accumulated scope creep:
the session will not dispose, so the gate never opens, so the plan stays live
until somebody interrupts the maintainer for it.

Disposing a plan child is not a spec-change decision. It changes where work is
TRACKED, not what the specification REQUIRES, so it is one of the decisions a
session takes itself with a recorded rationale. The rationale is written to the
ledger BEFORE the mutation, so a failed mutation leaves an explained intent
rather than a silent disposition.

One refusal remains, and `bd-ib-yykjko` INVERTED it. The autonomy-tier bullet
of `SPECIFICATION/contracts.md` section "Grooming and slice-size calibration"
ends "Plan-child disposition refuses a held spec-change-tier child and admits
an implementation follow-up", and it says in the same breath that the tier is
"never read off `spec_commitment_hint` (which marks an implementation follow-up
to an already ratified change)". So the field this refusal used to key on marks
exactly the child the clause says to ADMIT.

The refusal now asks the one authority the clause names: the item's own
recorded spec-change-tier classification, held out of `ready` while its linked
proposed-change topic carries no ratifying revision record. That read is the
SHARED `standing_spec_change_hold`, never a second account of it — two
spellings of one hold is how a child refused here comes to be admitted by the
dispatch wall in the same minute.

A child whose comments cannot be read is ADMITTED rather than refused, which is
the same fail-open direction the hold takes everywhere else: the record is the
only thing that can establish the tier, and refusing every disposition on a
transient ledger fault reinstates the exact deadlock the paragraphs above
describe.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro._beads_client import EDGE_PARENT_CHILD, make_beads_client
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_gate import (
    item_comment_bodies,
)
from livespec_orchestrator_beads_fabro.commands._spec_change_tier_gate import (
    standing_spec_change_hold,
)

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro._beads_client import BeadsClient
    from livespec_orchestrator_beads_fabro.types import StoreConfig

__all__: list[str] = [
    "DISPOSITION_PREFIX",
    "PlanDispositionRefusedError",
    "close_plan_child",
    "reparent_plan_child",
]

DISPOSITION_PREFIX = "plan-child-disposition"


class PlanDispositionRefusedError(Exception):
    """Expected refusal raised when a session may not dispose a plan child."""

    @classmethod
    def spec_change_tier(cls, *, child_id: str, detail: str) -> PlanDispositionRefusedError:
        held = f"{child_id} is held out of ready by the spec-change tier"
        return cls(f"{held} and is not session-disposable until that hold releases.\n{detail}")


def close_plan_child(
    *,
    config: StoreConfig,
    epic_id: str,
    child_id: str,
    rationale: str,
    author: str,
    now: str,
) -> None:
    """Close one plan child, recording why, with no human valve."""
    client = make_beads_client(config=config)
    _refuse_spec_change_tier(config=config, child_id=child_id)
    _record_disposition(
        client=client,
        epic_id=epic_id,
        child_id=child_id,
        disposition="closed",
        rationale=rationale,
        author=author,
        now=now,
    )
    client.close_issue(issue_id=child_id, reason=rationale)


def reparent_plan_child(  # noqa: PLR0913 — one kw-only argument per recorded disposition field.
    *,
    config: StoreConfig,
    epic_id: str,
    child_id: str,
    new_parent_id: str,
    rationale: str,
    author: str,
    now: str,
) -> None:
    """Move one plan child to another parent, recording why, with no human valve."""
    client = make_beads_client(config=config)
    _refuse_spec_change_tier(config=config, child_id=child_id)
    _record_disposition(
        client=client,
        epic_id=epic_id,
        child_id=child_id,
        disposition=f"re-parented to {new_parent_id}",
        rationale=rationale,
        author=author,
        now=now,
    )
    client.remove_dependency(from_id=child_id, to_id=epic_id)
    client.add_dependency(from_id=child_id, to_id=new_parent_id, edge_type=EDGE_PARENT_CHILD)


def _refuse_spec_change_tier(*, config: StoreConfig, child_id: str) -> None:
    """Refuse a child the recorded spec-change-tier classification HOLDS.

    The repository root is what the ratification half of the hold is read
    against, and a connection descriptor carrying none cannot reach a spec
    history at all — so `topic_is_ratified` answers False for every topic and
    the hold stands, which is the fail-closed direction that half owns.
    """
    bodies = item_comment_bodies(path=config, work_item_id=child_id)
    if bodies is None:
        return
    repo = config.repo_root
    hold = standing_spec_change_hold(
        work_item_id=child_id,
        repo=Path() if repo is None else repo,
        comments=bodies,
    )
    if hold is not None:
        raise PlanDispositionRefusedError.spec_change_tier(child_id=child_id, detail=hold.detail)


def _record_disposition(  # noqa: PLR0913 — one kw-only argument per recorded disposition field.
    *,
    client: BeadsClient,
    epic_id: str,
    child_id: str,
    disposition: str,
    rationale: str,
    author: str,
    now: str,
) -> None:
    body = (
        f"{DISPOSITION_PREFIX}\nauthor: {author}\ntimestamp: {now}\n\n"
        f"{child_id} {disposition} out of plan epic {epic_id} by the plan session.\n\n"
        f"Rationale: {rationale}"
    )
    client.add_comment(issue_id=child_id, body=body)
    client.add_comment(issue_id=epic_id, body=body)
