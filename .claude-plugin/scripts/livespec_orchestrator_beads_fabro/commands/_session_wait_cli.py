"""JSON host CLI for bounded waits, inventory checks, and receipt ack."""

from __future__ import annotations

import argparse
import json
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Protocol, cast

from livespec_orchestrator_beads_fabro.commands._session_wait_gate import (
    GateStatusLauncher,
    observe_gate_target,
    resolve_primary_repository,
)
from livespec_orchestrator_beads_fabro.commands._session_wait_records import (
    ack_wait,
    process_generation_token,
)
from livespec_orchestrator_beads_fabro.commands._session_wait_types import (
    GateObservation,
    GateTarget,
    ProbeLauncher,
    WaitRequest,
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
    launcher=GateStatusLauncher,
    observe_target=observe_gate_target,
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
    _ = wait.add_argument("--gate", action="append", required=True)
    ack = subparsers.add_parser("ack")
    _ = ack.add_argument("--repo", required=True)
    _ = ack.add_argument("--session-id", required=True)
    _ = ack.add_argument("--wait-id", required=True)
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


def _wait_command(
    *,
    args: argparse.Namespace,
    primary: Path,
    gate_store_root: Path,
    wait_store_root: Path,
    seams: SessionWaitCliSeams,
) -> int:
    from livespec_orchestrator_beads_fabro.commands.session_wait import run_wait

    gate_ids = cast("list[str]", args.gate)
    targets = tuple(
        GateTarget.freeze(gate_store_root=gate_store_root, run_id=run_id) for run_id in gate_ids
    )
    result = run_wait(
        request=WaitRequest(
            wait_id=str(args.wait_id),
            session_id=str(args.session_id),
            repository=primary,
            deadline_seconds=float(args.deadline_seconds),
            targets=targets,
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
    args = _build_parser().parse_args(argv)
    primary = seams.primary_repository(repository=Path(str(args.repo)))
    gate_store_root, wait_store_root = _roots(
        primary=primary,
        use_tmp_directory=seams.use_tmp_directory,
    )
    command = str(args.command)
    if command == "wait":
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
    return _ack_command(args=args, wait_store_root=wait_store_root, seams=seams)
