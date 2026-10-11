"""The pre-dispatch Fabro currency gate over a whole selection.

The SELECTION-level entry point of the Fabro-currency-admission clause of
`SPECIFICATION/contracts.md`, and the ONE surface every dispatch path — the
single dispatch, the drain, the autonomous loop and the resume — reaches through
`_dispatcher_pre_dispatch_wall`. One shared predicate rather than one per path is
the clause's own requirement; wiring it into the shared wall is what makes that
structural instead of a claim about four sequences that could drift.

IT IS FIRST IN THE WALL, and that position is load-bearing rather than tidy. The
proof-assets gate CREATES a repository prerelease and the Codex credential gate
SPENDS a bounded provider renewal, so refusing an unadmissible ENGINE after
either of them would pay for a dispatch that could never run. It is also the only
refusal whose answer is a property of the FACTORY rather than of the items, so it
can be settled before anything about the selection is read.

AN EMPTY SELECTION IS ANSWERED WITHOUT ANY READ. The drain reaches the wall on
every pass that finds no ready work, so this is the common case; grading there
would spend a paginated forge round trip and one engine round trip per configured
target on a pass that was never going to dispatch.

THE JOURNAL RECORD IS PER TARGET, NOT PER ITEM. Currency is a property of the
serving engine, so a record per item would report one fact N times and invite a
reader to believe N measurements were taken. The refusal itself is returned ONCE
for the same reason.

A TARGET THAT DECLARES NO SERVER IS NOT EVALUATED, AND SAYS SO. Every condition
the clause enumerates is a fact about a build some server is SERVING, and every
Definition-of-Done assertion is written about "a dispatch whose selected factory
SERVES" something; the implicit single-factory `default` target declares no
server at all, so there is no server to ask and no serving commit to resolve. It
is therefore recorded under `FABRO_CURRENCY_UNEVALUATED_STAGE` — non-blocking,
naming the target and the reason — rather than refused or passed over in silence.
Refusing it instead would impose an admission condition on every repository that
has not declared a factory, which is a change no clause here asks for; passing it
in silence would read as a currency reading that was taken and succeeded, which is
the fail-open this gate exists to close. The surfaced record is what keeps the
bound measurable rather than assumed. Do NOT turn this into a configurable
exemption: the discriminator is the structural absence of a server to ask, not an
operator's choice, and a key an operator could set is a key that would be set.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._config import FactoryTarget
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandRunner
from livespec_orchestrator_beads_fabro.commands._dispatcher_fabro_currency import (
    CONDITION_TRANSITION_ADMITTED,
    FabroCurrencyVerdict,
    fabro_currency_verdict,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_fabro_currency_sources import (
    ObservationReading,
    fabro_currency_subject,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_fabro_release_observation import (
    release_observation_reading,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_factory_bin import (
    factory_effective_fabro_bin,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_factory_ledger import (
    dispatch_factory_targets,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import (
    JournalFile,
    ShellCommandRunner,
)
from livespec_orchestrator_beads_fabro.io import write_stderr
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "FABRO_CURRENCY_REFUSED_STAGE",
    "FABRO_CURRENCY_TRANSITION_STAGE",
    "FABRO_CURRENCY_UNEVALUATED_STAGE",
    "currency_instant",
    "fabro_currency_refusal",
]

# The journal stage a refused currency reading is recorded under. Distinct from
# the plugin-currency stages: those grade the orchestrator's own build against
# its release branch, and this one grades the ENGINE a dispatch would land on.
FABRO_CURRENCY_REFUSED_STAGE = "dispatcher-fabro-currency-refused"

# The stage a target with no declared server is recorded under: non-blocking,
# and deliberately NOT the refused stage, so a reader counting refusals is not
# handed a dispatch that was admitted.
FABRO_CURRENCY_UNEVALUATED_STAGE = "dispatcher-fabro-currency-unevaluated"

# The stage the one admitted transition is recorded under: non-blocking, and its
# own stage rather than a refusal, because the dispatch proceeds. It is written
# AND printed, because a notice only in the journal is a notice nobody reads at
# the moment it matters.
FABRO_CURRENCY_TRANSITION_STAGE = "dispatcher-fabro-currency-transition"


def currency_instant() -> datetime:
    """The instant currency is evaluated at, as the record reports it."""
    return datetime.now(timezone.utc)


def fabro_currency_refusal(
    *,
    args: argparse.Namespace,
    repo: Path,
    items: Sequence[WorkItem],
    journal: JournalFile,
    runner: CommandRunner | None = None,
    now: datetime | None = None,
) -> str | None:
    """The gate over one selection: an operator-facing refusal, or `None`.

    The two seams are resolved HERE rather than threaded from the wall so the
    wall keeps one call shape for every refusal it runs, and so a test can stand
    in exactly the two things that leave the process.
    """
    resolved_runner = runner if runner is not None else ShellCommandRunner()
    evaluated_at = now if now is not None else currency_instant()
    if not items:
        return None
    targets = dispatch_factory_targets(
        args=args, repo=repo, work_item_ids=[item.id for item in items]
    )
    _record_unevaluated(targets=targets, journal=journal)
    serving = [factory for factory in targets if factory.server is not None]
    if not serving:
        return None
    reading = release_observation_reading(repo=repo, runner=resolved_runner, now=evaluated_at)
    verdicts = [
        _verdict(
            args=args,
            factory=factory,
            repo=repo,
            runner=resolved_runner,
            reading=reading,
            now=evaluated_at,
        )
        for factory in serving
    ]
    return _reported(verdicts=verdicts, journal=journal)


def _record_unevaluated(*, targets: Sequence[FactoryTarget], journal: JournalFile) -> None:
    """Surface every target the predicate has no server to ask about.

    Recorded BEFORE the release reading, and the serverless case returns before
    taking one at all: a repository that declares no factory server must not spend
    a paginated forge round trip to be told there was nothing to evaluate.
    """
    for factory in targets:
        if factory.server is not None:
            continue
        journal.append(
            record={
                "stage": FABRO_CURRENCY_UNEVALUATED_STAGE,
                "target": factory.name,
                "reason": "no-declared-server",
                "detail": (
                    f"factory target {factory.name!r} declares no server, so it has no"
                    " serving integration commit to resolve and Fabro currency was not"
                    " evaluated for it"
                ),
                "blocking": False,
            }
        )


def _verdict(
    *,
    args: argparse.Namespace,
    factory: FactoryTarget,
    repo: Path,
    runner: CommandRunner,
    reading: ObservationReading,
    now: datetime,
) -> FabroCurrencyVerdict:
    """One target's verdict, driven by the engine client that target declares.

    The per-factory client is re-resolved rather than taken from `args.fabro_bin`
    because a target declaring its own `bin` is talked to through that binary;
    asking one factory's client about another factory's engine is the
    wrong-population reading this gate exists to prevent.
    """
    effective = factory_effective_fabro_bin(args=args, factory=factory)
    fabro_bin = effective if effective is not None else str(getattr(args, "fabro_bin", "fabro"))
    subject = fabro_currency_subject(
        factory=factory, fabro_bin=fabro_bin, runner=runner, cwd=repo, reading=reading
    )
    return fabro_currency_verdict(subject=subject, now=now)


def _reported(*, verdicts: Sequence[FabroCurrencyVerdict], journal: JournalFile) -> str | None:
    """Journal every refusing verdict, then return the FIRST refusal's detail.

    Every refusal is journaled before any is returned, because a second
    misconfigured target is a fact an operator needs even though only one message
    can be printed; a loop that returned on the first would leave the other
    target's state unrecorded until the first was fixed.
    """
    for verdict in verdicts:
        if verdict.condition != CONDITION_TRANSITION_ADMITTED:
            continue
        # SURFACED ON BOTH CHANNELS. The clause forbids describing this base as
        # in-window, and a dispatch that merely proceeded would do exactly that
        # by saying nothing: the operator's own record of the run would be
        # identical to a current engine's.
        journal.append(
            record={
                "stage": FABRO_CURRENCY_TRANSITION_STAGE,
                "target": verdict.target,
                "condition": verdict.condition,
                "detail": verdict.detail,
                "blocking": False,
            }
        )
        _ = write_stderr(text=f"{verdict.detail}\n")
    refusals = [verdict for verdict in verdicts if not verdict.admitted]
    for verdict in refusals:
        journal.append(
            record={
                "stage": FABRO_CURRENCY_REFUSED_STAGE,
                "target": verdict.target,
                "condition": verdict.condition,
                "detail": verdict.detail,
                "blocking": True,
            }
        )
    if not refusals:
        return None
    return refusals[0].detail
