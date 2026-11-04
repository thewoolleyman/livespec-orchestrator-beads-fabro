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

One refusal remains. A child whose AUTONOMY TIER is spec-change, and which is
still held for its linked proposal's ratification, is design-human-gated by
routing, and this module refuses to dispose it, naming the child.

THE DISCRIMINATOR IS THE RECORDED CLASSIFICATION, NOT `spec_commitment_hint`,
and the plan-child-disposition clause of `SPECIFICATION/constraints.md` says so
in as many words: the two "are near-opposites", because a non-null hint marks an
implementation FOLLOW-UP to an ALREADY-RATIFIED change — "ordinary dispatchable
work whose disposition this bullet admits" — while a spec-change slice "is
decided by that judgement and is held until its OWN linked proposal ratifies,
whether or not it also carries a hint from an earlier ratified change". This
module read the hint until `bd-ib-yykjko`, so it refused every ratified
follow-up and admitted every unratified feature: wrong "in both directions",
which is the clause's own phrase for it.

IT FAILS CLOSED, which the same clause requires outright: "where it cannot
determine a child's autonomy tier from that recorded classification, it MUST
refuse the disposition and surface it, and it MUST NOT substitute
`spec_commitment_hint` for the missing datum. Refusing an admissible disposition
costs an escalation; admitting an inadmissible one silently disposes of a
spec-change slice." So a child carrying NO classification is refused, and that
is the OPPOSITE direction from the pre-dispatch wall's reading of the same
absence — which proceeds, because its own clause makes `dod_gate` the backstop
and because holding there would empty the queue. Each half is stated where it is
required, and the asymmetry is deliberate rather than an oversight.

THE DEADLOCK THE PARAGRAPHS ABOVE DESCRIBE IS STILL AVOIDED, by a different
mechanism than before: a plan ANCHOR MARKER rides the same column as a genuine
commitment and neither is consulted at all now, so an anchored child is disposable
whenever its own classification says the tier does not hold.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro._beads_client import EDGE_PARENT_CHILD, make_beads_client
from livespec_orchestrator_beads_fabro._store_comments import read_work_item_comments
from livespec_orchestrator_beads_fabro.commands._dispatcher_spec_commitments import (
    ratified_proposal_topics,
)
from livespec_orchestrator_beads_fabro.commands._spec_change_tier import SPEC_DIRNAME
from livespec_orchestrator_beads_fabro.commands._spec_change_tier_hold import spec_change_hold
from livespec_orchestrator_beads_fabro.commands._spec_change_tier_record import (
    recorded_spec_change_tier,
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
    def spec_change_tier(cls, *, child_id: str) -> PlanDispositionRefusedError:
        detail = "human-gated by routing and is not session-disposable"
        held = "still held for its linked proposal's ratification"
        subject = f"{child_id} carries a recorded spec-change-tier classification {held}"
        return cls(f"{subject}; such a child is {detail}")

    @classmethod
    def undeterminable_tier(cls, *, child_id: str) -> PlanDispositionRefusedError:
        """The fail-closed refusal: no recorded classification to read the tier from.

        It is a SEPARATE refusal rather than the one above, because the two send
        the maintainer somewhere different: a held child waits for `revise`,
        while this one waits for a classification nothing has taken — and the
        remedy is to let the next intake or dispatch pass classify it.
        """
        remedy = " ".join(
            (
                "the disposition is refused rather than guessed, and",
                "`spec_commitment_hint` is not a substitute for the missing datum.",
                "Let the next intake or dispatch pass classify it.",
            )
        )
        subject = f"{child_id} carries no recorded spec-change-tier classification"
        return cls(f"{subject}, so its autonomy tier cannot be determined; {remedy}")


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
    _refuse_spec_change_tier(client=client, child_id=child_id, config=config)
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
    _refuse_spec_change_tier(client=client, child_id=child_id, config=config)
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


def _refuse_spec_change_tier(*, client: BeadsClient, child_id: str, config: StoreConfig) -> None:
    """Refuse a HELD spec-change-tier child, and refuse an undeterminable one.

    The ratification read is the same model-free one the pre-dispatch wall takes,
    so a child whose topic has ratified and been re-judged `stated` — a record
    reading tier `none` — is admitted here exactly as it is dispatched there.
    """
    recorded = recorded_spec_change_tier(
        comments=[
            comment.text for comment in read_work_item_comments(path=config, work_item_id=child_id)
        ]
    )
    if recorded is None:
        raise PlanDispositionRefusedError.undeterminable_tier(child_id=child_id)
    hold = spec_change_hold(
        work_item_id=child_id,
        recorded=recorded,
        ratified_topics=ratified_proposal_topics(
            spec_root=_spec_root(config=config, client=client)
        ),
    )
    if hold is not None:
        raise PlanDispositionRefusedError.spec_change_tier(child_id=child_id)


def _spec_root(*, config: StoreConfig, client: BeadsClient) -> Path:
    """The governed spec tree of the repository this tenant belongs to.

    `StoreConfig.repo_root` is optional on the read path, so an absent one
    resolves the CURRENT directory's spec tree rather than raising: a plan
    session runs in its own checkout, and the alternative — refusing every
    disposition in a configuration that names no root — would reinstate the
    archive deadlock this module exists to break. A root that carries no spec
    history yields no ratified topic, which keeps a held child held.
    """
    _ = client
    return (config.repo_root or Path.cwd()) / SPEC_DIRNAME


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
