"""The factory measurement a resume takes for its earlier run."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandRunner
from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_runs_attribution import (
    NON_TERMINAL_STATUS_KINDS,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_reflection_journal import (
    read_journal_records,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_resume_refusals import (
    LiveRun,
    live_runs_from_pairs,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_resume_run_record import (
    executing_node_from_payload,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port import FabroPort, FabroTarget
from livespec_orchestrator_beads_fabro.commands._run_attribution import journaled_run_ids
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = ["FactoryReading", "read_factory"]

_PS_TIMEOUT_SECONDS = 60.0
_INSPECT_TIMEOUT_SECONDS = 60.0


@dataclass(frozen=True, kw_only=True)
class FactoryReading:
    """What one factory answered about the earlier run of one item.

    `observed` false means the factory could not be asked. It is deliberately not
    the same value as an answering factory holding nothing alive, which carries
    the same empty `live_runs`: one authorizes a resume, the other refuses it.

    `executing_node` is `None` both when the factory no longer holds the run and
    when it holds it but names no stage, because the clause gives those one
    treatment — the verdict of the latest record decides instead.
    """

    observed: bool
    live_runs: tuple[LiveRun, ...]
    executing_node: str | None
    record: object | None = None


def read_factory(
    *,
    args: argparse.Namespace,
    repo: Path,
    item: WorkItem,
    journal_path: Path,
    earlier_run_id: str | None,
    runner: CommandRunner,
) -> FactoryReading:
    """Ask the resolved factory which runs of this item live and where one was."""
    port = FabroPort(
        fabro_bin=args.fabro_bin,
        target=_factory_target(args=args),
        runner=runner,
        cwd=repo,
    )
    ps = port.ps(timeout_seconds=_PS_TIMEOUT_SECONDS)
    if ps.command.exit_code != 0:
        return FactoryReading(observed=False, live_runs=(), executing_node=None)
    journaled = frozenset(
        journaled_run_ids(
            records=read_journal_records(journal_path=journal_path), work_item_id=item.id
        )
    )
    attributed = [run for run in ps.runs if run.run_id in journaled or run.work_item_id == item.id]
    live = live_runs_from_pairs(
        pairs=[
            (run.run_id, run.status_kind or "unknown")
            for run in attributed
            if run.status_kind in NON_TERMINAL_STATUS_KINDS
        ]
    )
    held = earlier_run_id is not None and any(run.run_id == earlier_run_id for run in ps.runs)
    if not held:
        return FactoryReading(observed=True, live_runs=live, executing_node=None)
    inspected = port.inspect(
        run_id=earlier_run_id if earlier_run_id is not None else "",
        timeout_seconds=_INSPECT_TIMEOUT_SECONDS,
    )
    return FactoryReading(
        observed=True,
        live_runs=live,
        executing_node=executing_node_from_payload(payload=inspected.payload),
        record=inspected.payload,
    )


def _factory_target(*, args: argparse.Namespace) -> FabroTarget:
    """The resolved factory, or the client's own default when none was pinned."""
    target = getattr(args, "fabro_factory_target", None)
    return FabroTarget(
        server_url=getattr(target, "server", None),
        dev_token=getattr(target, "dev_token", None),
    )
