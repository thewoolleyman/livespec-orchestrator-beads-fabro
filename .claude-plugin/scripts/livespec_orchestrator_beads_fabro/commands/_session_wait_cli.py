"""JSON host CLI for bounded waits, inventory checks, and receipt ack."""

from __future__ import annotations

import argparse
import json
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from math import isfinite
from pathlib import Path
from typing import Protocol, cast

from livespec_orchestrator_beads_fabro.commands._session_obligation_cli import (
    add_obligation_parsers,
    complete_command,
    launch_command,
)
from livespec_orchestrator_beads_fabro.commands._session_wait_ack import ack_wait
from livespec_orchestrator_beads_fabro.commands._session_wait_gate import (
    resolve_primary_repository,
)
from livespec_orchestrator_beads_fabro.commands._session_wait_pane import freeze_pane_target
from livespec_orchestrator_beads_fabro.commands._session_wait_records import (
    process_generation_token,
)
from livespec_orchestrator_beads_fabro.commands._session_wait_routing import (
    default_wait_launcher,
    observe_wait_target,
)
from livespec_orchestrator_beads_fabro.commands._session_wait_types import (
    GateObservation,
    GateTarget,
    ProbeLauncher,
    WaitRequest,
    WaitTarget,
)
from livespec_orchestrator_beads_fabro.commands.session_wait_inventory import (
    InventorySnapshot,
    ProcessGeneration,
    TargetObserver,
    inventory_waits,
)
from livespec_orchestrator_beads_fabro.io import write_stdout

__all__: list[str] = [
    "SessionWaitCliSeams",
    "main",
]


class PrimaryRepository(Protocol):
    def __call__(self, *, repository: Path) -> Path: ...


class LauncherFactory(Protocol):
    def __call__(self, *, repository: Path) -> ProbeLauncher: ...


@dataclass(frozen=True, kw_only=True)
class SessionWaitCliSeams:
    primary_repository: PrimaryRepository
    launcher: LauncherFactory
    observe_target: TargetObserver
    process_generation: ProcessGeneration
    wall_clock: Callable[[], float]
    use_tmp_directory: bool = False


_DEFAULT_SEAMS = SessionWaitCliSeams(
    primary_repository=resolve_primary_repository,
    launcher=default_wait_launcher,
    observe_target=observe_wait_target,
    process_generation=process_generation_token,
    wall_clock=time.time,
    use_tmp_directory=True,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="session-wait")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("inventory", "check"):
        inventory = subparsers.add_parser(command)
        _ = inventory.add_argument("--repo", required=True)
    wait = subparsers.add_parser("wait")
    _ = wait.add_argument("--repo", required=True)
    _ = wait.add_argument("--session-id", required=True)
    _ = wait.add_argument("--wait-id", required=True)
    _ = wait.add_argument("--deadline-seconds", required=True, type=float)
    _ = wait.add_argument("--gate", action="append")
    # Two values rather than one delimited string: a Herdr pane id carries a
    # colon by construction (`w1:p1`) and a socket path may carry a colon or
    # a space, so any delimiter this surface chose would be ambiguous for its
    # own arguments.
    _ = wait.add_argument("--pane", action="append", nargs=2, metavar=("SOCKET", "PANE_ID"))
    ack = subparsers.add_parser("ack")
    _ = ack.add_argument("--repo", required=True)
    _ = ack.add_argument("--session-id", required=True)
    _ = ack.add_argument("--wait-id", required=True)
    add_obligation_parsers(add_parser=subparsers.add_parser)
    return parser


def _roots(*, primary: Path, use_tmp_directory: bool) -> tuple[Path, Path]:
    base = primary / "tmp" if use_tmp_directory else primary
    return base / "gate-runs", base / "session-waits"


def _observation_payload(*, observation: GateObservation) -> dict[str, object]:
    return {
        "exit_code": observation.exit_code,
        "fresh": observation.fresh,
        "observed_at": observation.observed_at,
        "state": observation.state,
        "target": observation.target.identity,
    }


def _snapshot_payload(*, snapshot: InventorySnapshot) -> dict[str, object]:
    return {
        "observation_id": snapshot.observation_id,
        "observed_at": snapshot.observed_at,
        "records": [
            {
                "diagnostic": record.diagnostic,
                "findings": sorted(record.findings),
                "observation_sequence": record.observation_sequence,
                "observations": [
                    _observation_payload(observation=observation)
                    for observation in record.observations
                ],
                "record_state": record.record_state,
                "wait_id": record.wait_id,
            }
            for record in snapshot.records
        ],
    }


def _frozen_targets(
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


def _wait_command(
    *,
    args: argparse.Namespace,
    primary: Path,
    gate_store_root: Path,
    wait_store_root: Path,
    seams: SessionWaitCliSeams,
) -> int:
    from livespec_orchestrator_beads_fabro.commands.session_wait import run_wait

    deadline_seconds = float(args.deadline_seconds)
    started_at = time.monotonic()
    # An invalid deadline freezes nothing: the wait refuses it before any
    # target is observed, and freezing first would spend an unbounded
    # observation on a request that was never going to be armed.
    targets = (
        _frozen_targets(
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
        ),
        launcher=seams.launcher(repository=primary),
        wait_store_root=wait_store_root,
        wall_clock=seams.wall_clock,
    )
    payload: dict[str, object] = {
        "command_outcome": result.command_outcome,
        "observations": {
            identity: _observation_payload(observation=observation)
            for identity, observation in result.observations.items()
        },
        "trigger_exit_code": result.trigger_exit_code,
        "trigger_target": result.trigger_target,
        "unfinished_targets": list(result.unfinished_targets),
    }
    _ = write_stdout(text=json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return int(result.command_outcome not in {"target-ended", "deadline"})


def _inventory_command(
    *,
    command: str,
    wait_store_root: Path,
    seams: SessionWaitCliSeams,
) -> int:
    snapshot = inventory_waits(
        wait_store_root=wait_store_root,
        observed_at=seams.wall_clock(),
        observe_target=seams.observe_target,
        process_generation=seams.process_generation,
    )
    _ = write_stdout(
        text=json.dumps(_snapshot_payload(snapshot=snapshot), indent=2, sort_keys=True) + "\n"
    )
    has_findings = any(record.findings for record in snapshot.records)
    return int(command == "check" and has_findings)


def _ack_command(
    *, args: argparse.Namespace, wait_store_root: Path, seams: SessionWaitCliSeams
) -> int:
    result = ack_wait(
        wait_store_root=wait_store_root,
        wait_id=str(args.wait_id),
        session_id=str(args.session_id),
        acknowledged_at=seams.wall_clock(),
        retention_limit=100,
    )
    _ = write_stdout(text=json.dumps(asdict(result), indent=2, sort_keys=True) + "\n")
    return int(result.status != "receipt-acknowledged")


def main(*, argv: list[str] | None = None, seams: SessionWaitCliSeams = _DEFAULT_SEAMS) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    primary = seams.primary_repository(repository=Path(str(args.repo)))
    gate_store_root, wait_store_root = _roots(
        primary=primary,
        use_tmp_directory=seams.use_tmp_directory,
    )
    command = str(args.command)
    if command == "wait":
        # Neither target option is individually required — a wait may watch
        # gates, panes or both — so the at-least-one rule is enforced here.
        # Arming with no target at all would block for the whole deadline and
        # then report a clean expiry, which reads as a wait that observed
        # something and saw nothing end.
        if not (args.gate or args.pane):
            parser.error("wait requires at least one --gate or --pane target")
        return _wait_command(
            args=args,
            primary=primary,
            gate_store_root=gate_store_root,
            wait_store_root=wait_store_root,
            seams=seams,
        )
    if command in {"inventory", "check"}:
        return _inventory_command(
            command=command,
            wait_store_root=wait_store_root,
            seams=seams,
        )
    if command == "launch":
        return launch_command(
            args=args,
            primary=primary,
            gate_store_root=gate_store_root,
            wall_clock=seams.wall_clock,
        )
    if command == "complete":
        return complete_command(primary=primary)
    return _ack_command(args=args, wait_store_root=wait_store_root, seams=seams)
