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
The route is therefore a FIELD, and every row writes the SAME key set with nulls
where a route has nothing to say — the discipline the reclaim's own hold record
states: "an operator reading the journal should not have to know which arm fired
to know which keys to expect." The `fresh`-after-absence row IS that row, which
is how "A confirmed absence of preserved work permits a plain dispatch from the
default branch, with that loss recorded" is recorded without a stage of its own.

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
    work_item_id: str,
    route: str,
    seed: RecoverySeed | None = None,
    preserved_work: str | None = None,
) -> dict[str, object]:
    """One non-held route's row, with the SAME key set whichever route it is."""
    return {
        "stage": RECOVERY_ROUTE_STAGE,
        "work_item_id": work_item_id,
        "route": route,
        "preserved_work": preserved_work,
        "source_run_id": None if seed is None else seed.source_run_id,
        "remote": None if seed is None else seed.remote,
        "commit_sha": None if seed is None else seed.commit_sha,
        "preservation_ref": None if seed is None else seed.preservation_ref,
    }


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
