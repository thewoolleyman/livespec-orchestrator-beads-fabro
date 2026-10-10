"""Factory liveness observation for a plan pointer's stamped target run."""

from __future__ import annotations

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
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import ShellCommandRunner
from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_runs_attribution import (
    NON_TERMINAL_STATUS_KINDS,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port import FabroPort, FabroTarget

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.commands._plan_next_action import NextAction
    from livespec_orchestrator_beads_fabro.types import StoreConfig

__all__: list[str] = [
    "live_factory_run_id",
]

_INSPECT_TIMEOUT_SECONDS = 60.0


def live_factory_run_id(  # pragma: no cover
    *,
    config: StoreConfig,
    action: NextAction,
) -> str | None:
    """Return the stamped target run only while its own factory says it is live.

    This is the effect boundary replaced by the fake-factory seam in the
    integration proof. A stamp alone is never accepted as liveness: the run is
    inspected against the factory name recorded beside that stamp, through the
    same target and client-bin resolution used by dispatch reconciliation.
    """
    record = next(
        (
            candidate
            for candidate in make_beads_client(config=config).list_issues()
            if candidate.get("id") == action.ref
        ),
        None,
    )
    if record is None:
        return None
    run_id = dispatch_run_id_from_record(record=record)
    if run_id is None:
        return None
    project_root = config.repo_root if config.repo_root is not None else Path.cwd()
    factory = resolve_fabro_factory(
        cwd=project_root,
        factory=dispatch_factory_from_record(record=record),
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
    if inspected.command.exit_code != 0 or inspected.status_kind not in NON_TERMINAL_STATUS_KINDS:
        return None
    return run_id
