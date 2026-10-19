"""Factory liveness observation for a plan pointer's stamped target run.

THE VERDICT IS THREE-WAY, AND THE THIRD VALUE IS THE WHOLE POINT. "No live run
is driving this target" and "this factory could not be read" are opposite
answers to the only question the caller asks — may a second dispatch start? —
and they were once the same `None`. A gauge that answers not-live when it is
BLINDED turns the duplicate-dispatch refusal into a pass, and the resulting
record reads exactly like a healthy re-dispatch of genuinely idle work.

So every arm that could not MEASURE answers `unobservable` and names what
failed, and `not_live` is reserved for a reading that SUCCEEDED and found no
live run: a ledger read that returned no such record, a record carrying no run
stamp, or an inspection that reported a readable terminal status.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro._beads_client import make_beads_client
from livespec_orchestrator_beads_fabro._store_dispatch_factory import (
    dispatch_factory_from_record,
    dispatch_run_id_from_record,
)
from livespec_orchestrator_beads_fabro.commands._config import (
    resolve_fabro_bin,
    resolve_fabro_factory,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_factory_bin import factory_fabro_bin
from livespec_orchestrator_beads_fabro.commands._dispatcher_factory_registry import (
    factory_registry_unobservable,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import ShellCommandRunner
from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_runs_attribution import (
    NON_TERMINAL_STATUS_KINDS,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port import FabroPort, FabroTarget
from livespec_orchestrator_beads_fabro.commands._plan_next_action import SPEC_OP_KIND

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.commands._plan_next_action import NextAction
    from livespec_orchestrator_beads_fabro.types import StoreConfig

__all__: list[str] = [
    "LIVENESS_LIVE",
    "LIVENESS_NOT_LIVE",
    "LIVENESS_UNOBSERVABLE",
    "RunLiveness",
    "observe_target_run",
]

LIVENESS_LIVE = "live"
LIVENESS_NOT_LIVE = "not-live"
LIVENESS_UNOBSERVABLE = "unobservable"

_INSPECT_TIMEOUT_SECONDS = 60.0


@dataclass(frozen=True, kw_only=True)
class RunLiveness:
    """One reading of whether a live factory run is driving a pointer's target.

    `run_id` is populated ONLY on the `live` verdict. An unobservable reading
    deliberately carries none: the stamp is known, but naming it beside a
    verdict that establishes nothing invites a caller to rewrite the pointer
    onto a run nobody read.
    """

    verdict: str
    run_id: str | None
    detail: str


def observe_target_run(
    *,
    config: StoreConfig,
    epic_id: str,
    action: NextAction,
) -> RunLiveness:
    """Ask the stamped target run's OWN factory whether that run is still live.

    This is the effect boundary replaced by the fake-factory seam in the
    integration proof. A stamp alone is never accepted as liveness: the run is
    inspected against the factory name recorded beside that stamp, through the
    same target and client-bin resolution used by dispatch reconciliation.
    """
    target_id = epic_id if action.kind == SPEC_OP_KIND else action.ref
    record = next(
        (
            candidate
            for candidate in make_beads_client(config=config).list_issues()
            if candidate.get("id") == target_id
        ),
        None,
    )
    if record is None:
        return _not_live(detail=f"the ledger holds no record of target {target_id}")
    run_id = dispatch_run_id_from_record(record=record)
    if run_id is None:
        return _not_live(detail=f"target {target_id} carries no dispatched run stamp")
    return _inspected(config=config, record=record, run_id=run_id)


def _inspected(
    *,
    config: StoreConfig,
    record: dict[str, object],
    run_id: str,
) -> RunLiveness:
    project_root = config.repo_root if config.repo_root is not None else Path.cwd()
    factory = resolve_fabro_factory(
        cwd=project_root,
        factory=dispatch_factory_from_record(record=record),
    )
    # A REGISTRY-BACKED factory whose address did not resolve is answered BEFORE
    # a port exists, because the port would be built on a `server` of None and a
    # bare Fabro target asks whichever engine this host runs. That reading
    # succeeds: it reports a run living on another machine as one the local
    # engine has never heard of, which lands on the `not_live` verdict this
    # module exists to withhold from an unmeasured answer.
    unobservable = factory_registry_unobservable(factory=factory)
    if unobservable is not None:
        return RunLiveness(
            verdict=LIVENESS_UNOBSERVABLE,
            run_id=None,
            detail=(
                f"{unobservable}, so run {run_id} could not be inspected and the"
                " reading is evidence of nothing about whether it is live"
            ),
        )
    port = FabroPort(
        fabro_bin=factory_fabro_bin(
            factory=factory,
            fallback=resolve_fabro_bin(cwd=project_root),
        ),
        target=FabroTarget(server_url=factory.server, dev_token=factory.dev_token),
        runner=ShellCommandRunner(),
        cwd=project_root,
    )
    inspected = port.inspect(run_id=run_id, timeout_seconds=_INSPECT_TIMEOUT_SECONDS)
    if inspected.command.exit_code != 0:
        return RunLiveness(
            verdict=LIVENESS_UNOBSERVABLE,
            run_id=None,
            detail=(
                f"factory {factory.name} refused the inspection of run {run_id}"
                f" with exit code {inspected.command.exit_code}"
            ),
        )
    if inspected.status_kind is None:
        return RunLiveness(
            verdict=LIVENESS_UNOBSERVABLE,
            run_id=None,
            detail=(
                f"factory {factory.name} returned no readable status for run {run_id},"
                " so the reading is evidence of nothing about whether it is live"
            ),
        )
    if inspected.status_kind not in NON_TERMINAL_STATUS_KINDS:
        return _not_live(
            detail=f"run {run_id} stands at the terminal status {inspected.status_kind}"
        )
    return RunLiveness(
        verdict=LIVENESS_LIVE,
        run_id=run_id,
        detail=f"run {run_id} stands at the non-terminal status {inspected.status_kind}",
    )


def _not_live(*, detail: str) -> RunLiveness:
    return RunLiveness(verdict=LIVENESS_NOT_LIVE, run_id=None, detail=detail)
