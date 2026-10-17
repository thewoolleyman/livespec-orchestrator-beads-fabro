"""The routes recovery routing assigns, and what each one carries into a launch.

`SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback priority"
→ "Recovery from the failed run's preserved work" names four routes — `resume`,
`seeded`, `fresh` and `held` — and says the first that holds is the route. This
module is the GRAMMAR: the four names, and the per-route state a launch path
needs in order to execute one. The DECISION lives in
`_dispatcher_recovery_routing`, which has to read the forge and the factory, and
the records live in `_dispatcher_recovery_records`; keeping the values here is
what lets both of those be read on their own.

WHY THE ROUTE IS A VALUE RATHER THAN A FLAG ON THE ARGUMENTS. The clause is
explicit about where route state may live: "After admission, each launch path
MUST execute every admitted item's route on that item's own copy of the dispatch
arguments... Route-specific state MUST NOT be written to arguments shared by the
wave." A drain hands one namespace to a wave of items, so a route written onto
that namespace is a route applied to every item in it — and the result is a
perfectly well-formed dispatch of the wrong tree. Carrying the route as a value
keyed by work-item id makes the per-item application the only thing a launch path
CAN do.

WHY `RecoveryResume` RESTATES THE ANCHOR RATHER THAN CARRYING IT. A
`ResumeAnchor` is what the forge and the journal SAY; this is what the launch
DOES, and the two are deliberately different shapes. The anchor carries the proof
record it was read off, which a launch has no use for, and it carries no pull
request number or earlier-run identifiers, which the `resume` record does. A
route that carried the anchor would leave each launch path re-deriving the other
half, and two paths re-deriving one thing is how they come to disagree.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__: list[str] = [
    "ROUTE_FRESH",
    "ROUTE_RESUME",
    "RecoveryResume",
    "RecoveryRoute",
]

# The routes, as the clause names them. `held` and `seeded` arrive with the
# measurements that produce them.
ROUTE_FRESH = "fresh"
ROUTE_RESUME = "resume"


@dataclass(frozen=True, kw_only=True)
class RecoveryResume:
    """Everything a `resume` route hands its launch, and nothing else.

    `workflow_name` is the name the EARLIER dispatch record carries, which the
    clause makes a requirement rather than a default: the resumed run "runs the
    workflow the earlier dispatch record names". It is `None` for a journal
    written by a build predating that field, which leaves the ordinary variant
    precedence to resolve the item's own recorded pin — the same graph.

    `earlier_run_ids` is PLURAL because the earlier run answers to more than one
    identifier, and the attribution clause accepts "either identifier the
    Dispatcher can attribute": recording only the one the anchoring record
    happened to carry would link half the pair.
    """

    entry_node: str
    head: str
    pull_request: int
    earlier_run_ids: tuple[str, ...]
    source: str
    workflow_name: str | None


@dataclass(frozen=True, kw_only=True)
class RecoveryRoute:
    """One item's assigned route, with whatever that route needs to be executed.

    ONE type for every route rather than one per route, because every consumer
    asks the same two questions — which route is this, and what does it carry —
    and a union would make each of them a type test before either question could
    be asked. The per-route payload is optional and exactly one of them is set
    for the routes that have one, which `_dispatcher_recovery_routing` is the
    sole constructor of.
    """

    work_item_id: str
    route: str
    resume: RecoveryResume | None = None
