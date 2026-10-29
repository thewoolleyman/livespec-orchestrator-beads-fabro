"""Bodies of the `wait` subcommand and the payloads the host CLI prints.

Moved out of `_session_wait_cli` by cohesion: freezing the named targets, running
the wait and rendering its result are one concern, and rendering an observation
is shared with the inventory snapshot. The CLI keeps the parser, the remaining
subcommands and the exporter's lifetime.
"""

from __future__ import annotations

import argparse
import time
from math import isfinite
from pathlib import Path
from typing import TYPE_CHECKING, cast

from livespec_orchestrator_beads_fabro.commands._session_wait_pane import freeze_pane_target
from livespec_orchestrator_beads_fabro.commands._session_wait_telemetry import (
    SessionWaitPublisher,
)
from livespec_orchestrator_beads_fabro.commands._session_wait_types import (
    GateObservation,
    GateTarget,
    WaitRequest,
    WaitTarget,
)
from livespec_orchestrator_beads_fabro.commands.session_wait_inventory import InventorySnapshot

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.commands._session_wait_cli import SessionWaitCliSeams

__all__: list[str] = [
    "observation_payload",
    "snapshot_payload",
    "wait_payload",
]


def observation_payload(*, observation: GateObservation) -> dict[str, object]:
    return {
        "exit_code": observation.exit_code,
        "fresh": observation.fresh,
        "observed_at": observation.observed_at,
        "state": observation.state,
        "target": observation.target.identity,
    }


def snapshot_payload(*, snapshot: InventorySnapshot) -> dict[str, object]:
    return {
        "observation_id": snapshot.observation_id,
        "observed_at": snapshot.observed_at,
        "records": [
            {
                "diagnostic": record.diagnostic,
                "findings": sorted(record.findings),
                "observation_sequence": record.observation_sequence,
                "observations": [
                    observation_payload(observation=observation)
                    for observation in record.observations
                ],
                "record_state": record.record_state,
                "wait_id": record.wait_id,
            }
            for record in snapshot.records
        ],
    }


def frozen_targets(
    *,
    args: argparse.Namespace,
    gate_store_root: Path,
    deadline: float,
) -> tuple[WaitTarget, ...]:
    """Every target this invocation named, frozen as it stands right now.

    Each pane's identity is read within what REMAINS of the one deadline, not
    within a socket timeout of its own. Freezing is an observation of the
    target like any other, so a slow or silent server must not spend time the
    caller never granted: measured before this bound, a 0.1s request against
    a peer that accepted `agent.get` and never answered took 5.01s to refuse.
    """
    gate_ids = cast("list[str] | None", args.gate) or []
    panes = cast("list[list[str]] | None", args.pane) or []
    gates: tuple[WaitTarget, ...] = tuple(
        GateTarget.freeze(gate_store_root=gate_store_root, run_id=run_id) for run_id in gate_ids
    )
    frozen_panes: tuple[WaitTarget, ...] = tuple(
        freeze_pane_target(
            socket_path=Path(socket_path),
            pane_id=pane_id,
            timeout_seconds=max(0.0, deadline - time.monotonic()),
        )
        for socket_path, pane_id in panes
    )
    return gates + frozen_panes


def wait_payload(
    *,
    args: argparse.Namespace,
    primary: Path,
    gate_store_root: Path,
    wait_store_root: Path,
    seams: SessionWaitCliSeams,
    publisher: SessionWaitPublisher,
) -> tuple[dict[str, object], int]:
    """Run the wait and return the payload to print with the exit code it earned.

    The CLI prints the payload itself, so the result reaches stdout from the one
    module that owns stdout and the exporter's bounded shutdown can only follow it.
    """
    from livespec_orchestrator_beads_fabro.commands.session_wait import run_wait

    deadline_seconds = float(args.deadline_seconds)
    started_at = time.monotonic()
    # An invalid deadline freezes nothing: the wait refuses it before any
    # target is observed, and freezing first would spend an unbounded
    # observation on a request that was never going to be armed.
    targets = (
        frozen_targets(
            args=args,
            gate_store_root=gate_store_root,
            deadline=started_at + deadline_seconds,
        )
        if isfinite(deadline_seconds) and deadline_seconds > 0
        else ()
    )
    result = run_wait(
        request=WaitRequest(
            wait_id=str(args.wait_id),
            session_id=str(args.session_id),
            repository=primary,
            deadline_seconds=deadline_seconds,
            targets=targets,
            started_at=started_at,
            publisher=publisher,
        ),
        launcher=seams.launcher(repository=primary),
        wait_store_root=wait_store_root,
        wall_clock=seams.wall_clock,
    )
    payload: dict[str, object] = {
        "command_outcome": result.command_outcome,
        "observations": {
            identity: observation_payload(observation=observation)
            for identity, observation in result.observations.items()
        },
        "trigger_exit_code": result.trigger_exit_code,
        "trigger_target": result.trigger_target,
        "unfinished_targets": list(result.unfinished_targets),
    }
    return payload, int(result.command_outcome not in {"target-ended", "deadline"})
