"""ONE SUCCESSFUL availability attempt derived from a factory run.

The retirement counterpart of `_acp_factory_hold_records`, and a leaf for the
same reason: nothing here performs IO, reads configuration or takes a clock, so
every decision about what one successful attempt IDENTIFIES is exercisable with
no factory at all. `_acp_factory_hold_evidence` owns the read that produces
these attempts; `_acp_hold_retirement` owns what they then falsify.

`SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback
priority": "Bounded expiry, later matching execution, and operator clearance are
the only hold-retirement routes. A node attempt that starts after a domain
observation and succeeds against the same hold key retires only that older
domain record; a later success by the exact candidate identity retires only its
older candidate record." And, in the same section: "Observations, successful
availability confirmations, and operator clearances MUST each be recorded as a
factory-native record on the participating factory whose evidence they create or
retire -- a confirmation by the factory run that confirmed it ... so retirement
is reconstructible from the same source as observation."

THAT LAST SENTENCE IS WHY THIS CARRIES NO JOURNAL LINE while its hold
counterpart does. The succeeding RUN is itself the factory-native record of the
confirmation, so the retirement is re-derived from the factory on every
admission evaluation rather than mirrored into a repository-local journal. A
journalled retirement would be a second account of one run, and the one it is
derived from is the only one that decides anything.

THE START INSTANT IS THE RUN'S OWN, AND IT IS A LOWER BOUND ON EVERY NODE
ATTEMPT THE RUN CONTAINS -- which is the conservative direction and the whole
reason it is the figure recorded. The retirement rule asks whether the attempt
began AFTER the observation; a run that began after it cannot contain a node
attempt that began before it, so a success dated from the run's start retires
only holds the attempt genuinely post-dates. Dating it from the run's
COMPLETION would be the opposite error: a run already executing when the outage
was observed would finish afterwards and clear a live hold the contract says it
proves nothing about.

THE DOMAIN SET IS THE ONE KEY THE RUN RECORDED, never a broader one. A
candidate's full domain set is its `availability_key` plus every override its
own domain signatures declare, and those signatures are the DECLARING
repository's configuration -- which this repository does not hold for a peer's
candidates and must not guess at. So the derived attempt claims exactly the
allowance its labels name; a hold on a shared pool is retired by a run that
recorded that pool, and by no other.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__: list[str] = [
    "FactorySuccessObservation",
]


@dataclass(frozen=True, kw_only=True)
class FactorySuccessObservation:
    """One SUCCEEDED node attempt, as the factory's own records identify it.

    The identifying fields mirror `FactoryHoldObservation` field for field, so
    one reader can produce both from one row and one per-run record, and
    `repository` is OPTIONAL for the same reason: an `omitempty`-sparse row
    carries no repository label, and a derived name would report a dispatch
    nobody made.

    `started_at` is the RUN's start rather than the node attempt's, which is
    the lower bound the module docstring explains. `candidate_key` is optional
    because the labels record WHAT ran separately from WHOSE allowance it
    spent, and an attempt missing it still retires the right domain record.

    THERE IS DELIBERATELY NO `run_reference` HERE, where the failure
    counterpart carries one. That property exists to make a derived hold's
    `observation_id` stable across two Dispatchers reading one attempt; a
    confirmation mints no record and no id, because the succeeding RUN is
    itself the factory-native record of it. Adding one would be a surface
    nothing reads, and the fields below already name the run it came from.
    """

    factory: str
    repository: str | None
    run_id: str
    node_attempt: str
    availability_key: str
    candidate_key: str | None
    started_at: str
