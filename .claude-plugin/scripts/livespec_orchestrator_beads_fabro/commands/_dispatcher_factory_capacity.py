"""One overflow candidate's capacity, read from that candidate's OWN server.

The factory-overflow-selection clause of `SPECIFICATION/contracts.md` names two
figures per candidate and one place to read them from: "For each candidate the
Dispatcher MUST read, from that candidate's own Fabro server at selection time,
its non-terminal run count and its own `max_concurrent_runs`." This module is
that read, plus the grade of it; `_dispatcher_overflow_selection` is the ranking
over several of them.

WHY `unreadable` IS A FIELD AND NOT AN ABSENT PAIR OF NUMBERS. The clause gives
four ways a candidate goes unmeasured — "whose read fails, times out, is
unparseable, or" the registry cannot resolve — and every one of them "MUST count
as having no free slot". A saturated candidate ALSO has no free slot, so the two
reach the ranking identically and would be indistinguishable in the journal
record the clause requires. The reason is carried so the record can say which
measurement stopped it, exactly as the publish-branch reclaim's held rows do.

WHY A `max_concurrent_runs` BELOW 1 IS NOT AN UNREADABLE READ. The clause lists
it beside the three read failures, and in its EFFECT it is identical — no free
slot — but in its EVIDENCE it is the opposite: the server answered, and what it
said is that it will start nothing. Carrying it as a reported figure is what lets
the journal show `0 of 0` rather than a reason that sends an operator to debug a
read that worked.

WHY `None` IS NEVER COERCED TO A ZERO, in either figure. A run count of zero is
an idle factory and a ceiling of zero is a stopped scheduler; both are real
readings a server can give. A coerced zero is therefore indistinguishable from a
measurement, and in the run-count direction it is the one coercion that sends
work to a server nobody could reach — which the clause's own fail-closed sentence
exists to prevent.

WHY THE REGISTRY IS RESOLVED FIRST AND GRADED HERE. "A registry-backed candidate
MUST be resolved through the host registry before its server is read", and an
unresolvable one "counts as having no free slot". Both fall out of resolving the
target first: `FactoryTarget.server` carries the registry's address when the
registry answered, and `FactoryTarget.registry.detail` is non-None exactly when
it did not. Grading it here rather than letting the read fail is what makes the
journal name the registry instead of reporting a factory that declares no server
— which is the same value an unconfigured entry carries and a completely
different remedy.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from livespec_orchestrator_beads_fabro.commands._acp_factory_run_reader import FactoryRunReader
from livespec_orchestrator_beads_fabro.commands._config import resolve_fabro_factory
from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_runs_attribution import (
    NON_TERMINAL_STATUS_KINDS,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port_records import FabroRunSummary

__all__: list[str] = [
    "UNREADABLE_CEILING",
    "UNREADABLE_REGISTRY",
    "UNREADABLE_RUN_BOARD",
    "UNREADABLE_SERVER_UNDECLARED",
    "CapacityReader",
    "FactoryCapacity",
    "read_factory_capacity",
]

# The four reasons a candidate goes unmeasured, one per measurement that can
# fail. Each is a stable token an operator can grep the dispatch journal for.
UNREADABLE_REGISTRY = "registry-unresolvable"
UNREADABLE_SERVER_UNDECLARED = "server-undeclared"
UNREADABLE_RUN_BOARD = "run-board-unreadable"
UNREADABLE_CEILING = "scheduler-ceiling-unreadable"

_MINIMUM_USABLE_CEILING = 1


@dataclass(frozen=True, kw_only=True)
class FactoryCapacity:
    """What ONE candidate's own server reported, or why it reported nothing.

    `run_count` and `max_concurrent_runs` are non-None exactly when `unreadable`
    is None. The invariant is kept by construction — every arm below either
    returns both figures or returns a reason — rather than asserted, because a
    half-populated reading would rank a candidate on a figure nobody measured.
    """

    factory: str
    run_count: int | None
    max_concurrent_runs: int | None
    unreadable: str | None

    @property
    def free_slot(self) -> bool:
        """Whether this candidate's count is below its own ceiling.

        A ceiling below 1 is no free slot however low the count: the clause says
        so, and a server that will start nothing has no room for this dispatch
        whatever its board looks like.
        """
        if self.run_count is None or self.max_concurrent_runs is None:
            return False
        if self.max_concurrent_runs < _MINIMUM_USABLE_CEILING:
            return False
        return self.run_count < self.max_concurrent_runs

    @property
    def utilization(self) -> float | None:
        """The count divided by the ceiling, or `None` when that is not a number.

        `None` for every candidate with no usable ceiling, which is every
        candidate `free_slot` already excludes — so the ranking never divides by
        a zero it has not already discarded.
        """
        if self.run_count is None or self.max_concurrent_runs is None:
            return None
        if self.max_concurrent_runs < _MINIMUM_USABLE_CEILING:
            return None
        return self.run_count / self.max_concurrent_runs

    @property
    def ranking_key(self) -> float:
        """This candidate's utilization for the ranking, SATURATED when unmeasured.

        The ranking only ever asks this of a candidate `free_slot` admitted, and
        every such candidate's `utilization` is a number — so the saturated value
        is unreachable from the selection. It is spelled as 1.0 rather than
        omitted because a caller that reached here with an unmeasured candidate
        must rank it LAST: a `None` would raise inside the comparison and take
        the dispatch down with a type error instead of a decision, and a 0.0
        would make the one candidate nobody could measure win outright.
        """
        return 1.0 if self.utilization is None else self.utilization

    def journal_fields(self) -> Mapping[str, object]:
        """This candidate's row of the overflow-selection journal record.

        Every key is written on every row, nulls included: an omitted key is what
        a row from a build predating this clause looks like, so a reader could
        not tell "this candidate reported nothing" from "this candidate was
        never asked".
        """
        return {
            "factory": self.factory,
            "run_count": self.run_count,
            "max_concurrent_runs": self.max_concurrent_runs,
            "unreadable": self.unreadable,
        }


class CapacityReader(Protocol):
    """The two factory-native reads one candidate's capacity is measured by."""

    def list_runs(self, *, factory: str) -> tuple[FabroRunSummary, ...] | None: ...

    def scheduler_max_concurrent_runs(self, *, factory: str) -> int | None: ...


def read_factory_capacity(
    *,
    repo: Path,
    factory: str,
    reader: CapacityReader | None = None,
) -> FactoryCapacity:
    """Measure one candidate, or report which measurement stopped it.

    The target is resolved BEFORE either read, which is what satisfies the
    clause's registry ordering and what lets an unresolvable registry be named
    as such rather than surfacing as a factory with no server.
    """
    target = resolve_fabro_factory(cwd=repo, factory=factory)
    if target.registry.declared and target.registry.detail is not None:
        return _unmeasured(factory=factory, reason=UNREADABLE_REGISTRY)
    if target.server is None:
        return _unmeasured(factory=factory, reason=UNREADABLE_SERVER_UNDECLARED)
    resolved = FactoryRunReader(repo=repo) if reader is None else reader
    runs = resolved.list_runs(factory=factory)
    if runs is None:
        return _unmeasured(factory=factory, reason=UNREADABLE_RUN_BOARD)
    ceiling = resolved.scheduler_max_concurrent_runs(factory=factory)
    if ceiling is None:
        return _unmeasured(factory=factory, reason=UNREADABLE_CEILING)
    return FactoryCapacity(
        factory=factory,
        run_count=_non_terminal_count(runs=runs),
        max_concurrent_runs=ceiling,
        unreadable=None,
    )


def _non_terminal_count(*, runs: tuple[FabroRunSummary, ...]) -> int:
    """How many of this factory's rows are NON-TERMINAL.

    The set is the run reconciler's own `NON_TERMINAL_STATUS_KINDS` rather than a
    second list spelled here, for the reason the idle-slot board gives: two lists
    would be two authorities on what a live run is, and they would disagree the
    moment one gained a status. Counting every row instead would report a
    long-lived factory as permanently saturated — hp listed 1626 rows on
    2026-10-12, nearly all of them terminal.
    """
    return len([run for run in runs if run.status_kind in NON_TERMINAL_STATUS_KINDS])


def _unmeasured(*, factory: str, reason: str) -> FactoryCapacity:
    return FactoryCapacity(
        factory=factory,
        run_count=None,
        max_concurrent_runs=None,
        unreadable=reason,
    )
