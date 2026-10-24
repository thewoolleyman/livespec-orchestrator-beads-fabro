"""One provider-limit-released run, costed from its own record on its own factory.

`SPECIFICATION/contracts.md` section "Factory-configurable ACP fallback
priority" -> "Cost follows every attempt": "For every run released under
'Provider-limit release and re-dispatch' ... the Dispatcher MUST journal one
attempt-cost record carrying the attempt's token use and elapsed time per node
attempt wherever the run record exposes them, priced under the rules below, or
marked cost-unobservable."

THE IMPURE HALF, AND THE ONLY ONE THAT REACHES A FACTORY.
`_dispatcher_cost_attempts.attempt_cost_record` decides what the record SAYS
and `_dispatcher_provider_limit_disposition` decides WHEN one lands; this reads
the two things the run's own record exposes and hands them over. That is the
same read/record/perform split the release's hold takes one module over, and it
is what keeps every field of the record exercisable with no factory at all.

A RECORD IS OWED FOR EVERY RELEASED RUN, SO NO ARM HERE RETURNS NOTHING. Every
unreadable input degrades to "this half was not exposed" -- no declared server,
no run id, a refused `events`, a refused `ps` -- and the record still lands,
stating what could be read. A reading that returned `None` would leave the
released attempt with no observation, which the sequence fold cannot tell apart
from a run that genuinely cost nothing; the clause's own alternative is "marked
cost-unobservable", not "omitted".

THE TWO READS FAIL INDEPENDENTLY AND NEITHER DARKENS THE OTHER, which is the
decision most easily collapsed into one guard. A refused event stream leaves
the engine's whole-run figure perfectly readable, so darkening the cost there
would report a measured charge as unobservable; a refused `ps` leaves the
attempts readable, so dropping them would report an engine that exposed nothing
per attempt. Each half is asked for on its own and reported on its own.

THE FIGURE COMES FROM `fabro ps -a --json` AND NOT FROM `fabro inspect`, which
is a MEASUREMENT rather than a preference: `_dispatcher_cost`'s own
investigation found `inspect` does not carry `total_usd_micros` at all, while
every `ps` run record carries the key. So this reads the same canonical source
the fail-closed cost gate reads, and becomes priced on the same day the engine
starts populating it.

THE FACTORY IS RESOLVED BY THE RELEASE'S OWN NAME rather than from the item's
recorded dispatch stamp. The release was read off the terminal of the run being
costed, so its factory is the host that run actually executed on, and a stamp
re-read here could name a LATER dispatch's factory -- where the clean answer is
a run that does not exist. It also keeps this reading off the ledger, which
matters because its one caller is a fail-soft post-run disposition.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._acp_attempt_windows import AcpAttemptWindow
from livespec_orchestrator_beads_fabro.commands._config import (
    FactoryTarget,
    resolve_fabro_bin,
    resolve_fabro_factory,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_cost_attempts import (
    ATTEMPT_COST_RELEASED_RUN,
    attempt_cost_record,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_cost_chain import run_attempt_windows
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandRunner
from livespec_orchestrator_beads_fabro.commands._dispatcher_factory_bin import factory_fabro_bin
from livespec_orchestrator_beads_fabro.commands._dispatcher_provider_limit_classify import (
    ProviderLimitRelease,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_shell_runner import ShellCommandRunner
from livespec_orchestrator_beads_fabro.commands._fabro_port import FabroPort, FabroTarget
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt

__all__: list[str] = ["released_run_attempt_cost_record"]

# Every failure a configuration read or an engine invocation can raise here.
# This runs inside a fail-soft post-run disposition whose item is already
# released, so an unreadable input degrades to an unexposed half rather than
# propagating -- the same posture `_dispatcher_cost_chain` takes for the gate.
_RECOVERABLE = (AttributeError, KeyError, OSError, RuntimeError, TypeError, ValueError)

# Generous for one `ps` against a reachable factory, and bounded so an
# unresponsive one costs the disposition a minute rather than its item. The
# same figure the cost gate's own probe uses.
_PS_TIMEOUT_SECONDS = 60.0


@dataclass(frozen=True, kw_only=True)
class _Exposed:
    """What one run's own record exposed about its attempts and its cost.

    The pair rides one value rather than two returns so the two independent
    readings are taken together against ONE resolved factory and one run id:
    resolving twice would be two readings of a configuration that can change
    between them, and the disagreement would be invisible because each read
    produces a well-formed half.
    """

    windows: tuple[AcpAttemptWindow, ...]
    usd_micros: int | None


def released_run_attempt_cost_record(
    *,
    repo: Path,
    work_item_id: str,
    release: ProviderLimitRelease,
    occurred_at: str,
    runner: CommandRunner | None = None,
) -> dict[str, object]:
    """The one attempt-cost observation this released run is recorded as."""
    factory = _factory(repo=repo, name=release.factory)
    run_id = release.run_id
    exposed = (
        _Exposed(windows=(), usd_micros=None)
        if factory is None or run_id is None
        else _exposed(
            repo=repo,
            run_id=run_id,
            factory=factory,
            runner=ShellCommandRunner() if runner is None else runner,
        )
    )
    return attempt_cost_record(
        source=ATTEMPT_COST_RELEASED_RUN,
        work_item_id=work_item_id,
        factory=release.factory,
        run_id=run_id,
        node_attempt=release.node_attempt,
        occurred_at=occurred_at,
        windows=exposed.windows,
        usd_micros=exposed.usd_micros,
    )


def _factory(*, repo: Path, name: str) -> FactoryTarget | None:
    """The named factory with an address, or `None` when none resolves.

    `None` rather than a target carrying `server=None`, because that value is
    what an unconfigured repository holds and every engine invocation reads it
    as the ambient LOCAL engine -- which would survey whichever Fabro this host
    runs and report a clean reading taken on the wrong machine.
    """
    resolved = attempt(
        action=lambda: resolve_fabro_factory(cwd=repo, factory=name), exceptions=_RECOVERABLE
    )
    if isinstance(resolved, AttemptFailure) or resolved.server is None:
        return None
    return resolved


def _exposed(*, repo: Path, run_id: str, factory: FactoryTarget, runner: CommandRunner) -> _Exposed:
    """Both halves of what this run's record exposes, each asked for on its own."""
    return _Exposed(
        windows=run_attempt_windows(repo=repo, run_id=run_id, factory=factory, runner=runner),
        usd_micros=_engine_usd_micros(repo=repo, run_id=run_id, factory=factory, runner=runner),
    )


def _engine_usd_micros(
    *, repo: Path, run_id: str, factory: FactoryTarget, runner: CommandRunner
) -> int | None:
    """The engine's own figure for this run, or `None` when it reports none."""
    read = attempt(
        action=lambda: _ps_usd_micros(repo=repo, run_id=run_id, factory=factory, runner=runner),
        exceptions=_RECOVERABLE,
    )
    return None if isinstance(read, AttemptFailure) else read


def _ps_usd_micros(
    *, repo: Path, run_id: str, factory: FactoryTarget, runner: CommandRunner
) -> int | None:
    """Ask the run's own factory for its cost figure, matched on the run id.

    Matched BY RUN ID and never taken from the head of the listing, for the
    reason `_fabro_executed_candidate`'s own read gives: a factory serves every
    repository on its host, so another repository's row is a well-formed figure
    belonging to somebody else's dispatch.
    """
    port = FabroPort(
        fabro_bin=factory_fabro_bin(factory=factory, fallback=resolve_fabro_bin(cwd=repo)),
        target=FabroTarget(server_url=factory.server, dev_token=factory.dev_token),
        runner=runner,
        cwd=repo,
    )
    listed = port.ps(timeout_seconds=_PS_TIMEOUT_SECONDS)
    if listed.command.exit_code != 0:
        return None
    for run in listed.runs:
        if run.run_id == run_id:
            return run.total_usd_micros
    return None
