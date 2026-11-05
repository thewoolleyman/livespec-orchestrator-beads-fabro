"""The two journal records recovery routing writes, and the refusal it reports.

`SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback priority"
→ "Recovery from the failed run's preserved work" requires two durable records:
one for a HELD item — "the journal carries one `recovery-held` record naming the
item and the measurement that could not be taken, every applicable non-fallback
refusal with its existing remedy in the order the resume's refusals are listed,
or both" — and, for a seed, one that "MUST name the source run, remote, immutable
commit SHA, and preservation reference".

WHY ONE STAGE CARRIES EVERY NON-HELD ROUTE. `resume`, `seeded` and `fresh` are
three answers to ONE question, and a reader asking "which route did this item
take" must not have to know the answer in order to pick the stage to grep for.
The route is therefore a FIELD, and every ordinary row writes the SAME key set
with nulls where a route has nothing to say. A fresh route retaining a stale
preservation reference additionally names the preserved base and default-branch
pin-bump commit that made the seed unsafe. The `fresh`-after-absence row IS that
ordinary row, which is how "A confirmed absence of preserved work permits a plain
dispatch from the default branch, with that loss recorded" is recorded without a
stage of its own.

WHY `recovery-held` IS A SEPARATE STAGE RATHER THAN A FOURTH ROUTE VALUE. A held
item did not take a route; it was not admitted at all. A reader filtering for
"what did this pass launch" must not match the row that says nothing launched —
the same reason `_dispatcher_stall_disposition` keeps its release and its
needs-human terminals on separate stages rather than on one row with a field.

WHY THE REPORT IS BUILT HERE AND NOT AT THE REFUSING CALL SITE. Under
`dispatch --item` a hold "is a precondition error (exit `3`) naming the item and
the measurement or the non-fallback refusals with their remedies, before any run
exists, as `resume --item` refuses today". The journal row and the operator
message name the same two things, so they are rendered from one place: two
renderers is how an operator comes to read a remedy the journal does not record.
"""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_routes import (
    RecoveryHold,
    RecoveryLoss,
    RecoveryRoute,
    RecoverySeed,
)

__all__: list[str] = [
    "PRESERVED_WORK_ABSENT",
    "PRESERVED_WORK_VERIFIED",
    "RECOVERY_HELD_STAGE",
    "RECOVERY_ROUTE_STAGE",
    "recovery_held_record",
    "recovery_held_report",
    "recovery_route_record",
]

RECOVERY_ROUTE_STAGE = "recovery-route"
RECOVERY_HELD_STAGE = "recovery-held"

# What the route row says about preserved work, for the two routes that measured
# it. `absent` is the LOSS the clause requires recording; `verified` is the seed's
# own precondition. Every other route leaves the field null, because it never
# asked — which is a third fact, not a shorthand for absence.
PRESERVED_WORK_VERIFIED = "verified"
PRESERVED_WORK_ABSENT = "absent"


def recovery_route_record(
    *,
    recovery_route: RecoveryRoute,
) -> dict[str, object]:
    """One non-held route's row, with the SAME key set whichever route it is.

    `source_run_id` is served by EITHER payload, because the two name the same
    thing about the same run: the seed names the run whose work is being resumed
    from, and the loss names the run whose work is being written off. A row that
    carried the run only for a seed would leave the one route that DISCARDS work
    as the one route whose subject is unnamed.

    `preservation_sources_asked` is written only by the loss, and the asymmetry is
    deliberate rather than an omission: a `seeded` row names the source that
    ANSWERED, under `preservation_ref`, which says strictly more than the list of
    sources that were asked. Only a confirmed absence has an asked-set with no
    answer to point at, which is exactly why the clause requires that one
    recorded.
    """
    record: dict[str, object] = {
        "stage": RECOVERY_ROUTE_STAGE,
        "work_item_id": recovery_route.work_item_id,
        "route": recovery_route.route,
        "preserved_work": recovery_route.preserved_work,
        "source_run_id": _source_run_id(seed=recovery_route.seed, loss=recovery_route.loss),
        "remote": None if recovery_route.seed is None else recovery_route.seed.remote,
        "commit_sha": None if recovery_route.seed is None else recovery_route.seed.commit_sha,
        "preservation_ref": (
            None if recovery_route.seed is None else recovery_route.seed.preservation_ref
        ),
        "preservation_sources_asked": (
            None if recovery_route.loss is None else list(recovery_route.loss.sources_asked)
        ),
    }
    if (
        recovery_route.preserved_base_commit is not None
        and recovery_route.default_branch_commit is not None
    ):
        record["preserved_base_commit"] = recovery_route.preserved_base_commit
        record["default_branch_commit"] = recovery_route.default_branch_commit
    return record


def _source_run_id(*, seed: RecoverySeed | None, loss: RecoveryLoss | None) -> str | None:
    """The earlier run this row's route is about, from whichever payload names it.

    At most one of the two is ever set — a route is seeded from preserved work or
    taken after its confirmed absence, never both — so the order between them
    decides nothing and is not a precedence.
    """
    if seed is not None:
        return seed.source_run_id
    return None if loss is None else loss.source_run_id


def recovery_held_record(*, work_item_id: str, hold: RecoveryHold) -> dict[str, object]:
    """The one row a held item writes, naming every reason it was held.

    BOTH lists are written on every row, empty where they do not apply, because
    the clause admits a hold caused by a measurement, by a non-fallback refusal,
    "or both" — so a reader cannot tell which to expect from the stage alone.
    """
    return {
        "stage": RECOVERY_HELD_STAGE,
        "work_item_id": work_item_id,
        "measurements": [one.name for one in hold.measurements],
        "details": [one.detail for one in hold.measurements],
        "refusals": list(hold.refusals),
    }


def recovery_held_report(*, work_item_id: str, hold: RecoveryHold) -> str:
    """The operator-facing refusal `dispatch --item` exits 3 with.

    EVERY reason, never the first: the resume's own conjunction rule applies for
    the same reason it applies there — an operator told only the first reason acts
    on it and drives straight into the one they were never told about.
    """
    lines = "".join(
        f"  - {one}\n"
        for one in (
            *(f"{one.name}: {one.detail}" for one in hold.measurements),
            *hold.refusals,
        )
    )
    return (
        f"ERROR: recovery routing held {work_item_id}; it stays ready, it was not"
        f" admitted, and no run was created:\n{lines}"
    )
