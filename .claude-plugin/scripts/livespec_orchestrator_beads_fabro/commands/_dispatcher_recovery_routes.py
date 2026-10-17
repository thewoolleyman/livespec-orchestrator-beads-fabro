"""The routes recovery routing assigns, and what each one carries into a launch.

`SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback priority"
→ "Recovery from the failed run's preserved work" names four routes — `resume`,
`seeded`, `fresh` and `held` — and says the first that holds is the route. This
module is the GRAMMAR: the four names, and the per-route state a launch path
needs in order to execute one. The DECISION lives in
`_dispatcher_recovery_routing`, which has to read the forge and the factory; the
preserved-work READING lives in `_dispatcher_recovery_preserved`; and the journal
records live in `_dispatcher_recovery_records`. Keeping the values here is what
lets each of those be read on its own, and it is why the value types live HERE
rather than beside the readings that produce them — a grammar that imported its
own readers could not be the thing all three of them agree on.

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
    "ROUTE_HELD",
    "ROUTE_RESUME",
    "ROUTE_SEEDED",
    "RecoveryHold",
    "RecoveryMeasurement",
    "RecoveryResume",
    "RecoveryRoute",
    "RecoverySeed",
]

# The four routes, as the clause names them.
ROUTE_FRESH = "fresh"
ROUTE_RESUME = "resume"
ROUTE_SEEDED = "seeded"
ROUTE_HELD = "held"


@dataclass(frozen=True, kw_only=True)
class RecoveryMeasurement:
    """One measurement routing could not take, and what the item's reader is told.

    The NAME is a stable token an operator greps the journal for; the DETAIL is
    the prose the surface that could not measure already renders, carried rather
    than re-worded so the journal row and the refusal an operator reads say the
    same thing about the same read.
    """

    name: str
    detail: str


@dataclass(frozen=True, kw_only=True)
class RecoveryHold:
    """Every reason one item was held, in the order the resume's refusals are listed.

    BOTH fields rather than one list, because the clause distinguishes them and
    their remedies differ in kind: a measurement that could not be taken is
    retried automatically by the next pass, while a non-fallback refusal names a
    remedy a human or another valve has to perform.
    """

    measurements: tuple[RecoveryMeasurement, ...] = ()
    refusals: tuple[str, ...] = ()


@dataclass(frozen=True, kw_only=True)
class RecoverySeed:
    """The four things a seed record must name, resolved from one origin read."""

    source_run_id: str
    remote: str
    commit_sha: str
    preservation_ref: str


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
    be asked. At most one of the three payloads is set, which
    `_dispatcher_recovery_routing` is the sole constructor of.
    """

    work_item_id: str
    route: str
    resume: RecoveryResume | None = None
    seed: RecoverySeed | None = None
    hold: RecoveryHold | None = None
