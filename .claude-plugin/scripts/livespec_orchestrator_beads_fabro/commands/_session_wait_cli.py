"""JSON host CLI for bounded waits, inventory checks, and receipt ack."""

from __future__ import annotations

import argparse
import json
import os
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Protocol

from livespec_orchestrator_beads_fabro.commands._session_obligation_cli import (
    add_obligation_parsers,
    complete_command,
    launch_command,
)
from livespec_orchestrator_beads_fabro.commands._session_telemetry_export import (
    SessionTelemetry,
)
from livespec_orchestrator_beads_fabro.commands._session_wait_ack import ack_wait
from livespec_orchestrator_beads_fabro.commands._session_wait_commands import (
    snapshot_payload,
    wait_payload,
)
from livespec_orchestrator_beads_fabro.commands._session_wait_gate import (
    resolve_primary_repository,
)
from livespec_orchestrator_beads_fabro.commands._session_wait_records import (
    process_generation_token,
)
from livespec_orchestrator_beads_fabro.commands._session_wait_routing import (
    default_wait_launcher,
    observe_wait_target,
)
from livespec_orchestrator_beads_fabro.commands._session_wait_telemetry import (
    SessionWaitPublisher,
    associations_from_environ,
)
from livespec_orchestrator_beads_fabro.commands._session_wait_types import (
    ProbeLauncher,
)
from livespec_orchestrator_beads_fabro.commands.session_wait_inventory import (
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


_GATE_STATE_NAME = "telemetry-state.state"


def _roots(*, primary: Path, use_tmp_directory: bool) -> tuple[Path, Path]:
    base = primary / "tmp" if use_tmp_directory else primary
    return base / "gate-runs", base / "session-waits"


def _wait_command(
    *,
    args: argparse.Namespace,
    primary: Path,
    gate_store_root: Path,
    wait_store_root: Path,
    seams: SessionWaitCliSeams,
    publisher: SessionWaitPublisher,
) -> int:
    payload, code = wait_payload(
        args=args,
        primary=primary,
        gate_store_root=gate_store_root,
        wait_store_root=wait_store_root,
        seams=seams,
        publisher=publisher,
    )
    _ = write_stdout(text=json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return code


def _inventory_command(
    *,
    command: str,
    wait_store_root: Path,
    seams: SessionWaitCliSeams,
    publisher: SessionWaitPublisher,
) -> int:
    snapshot = inventory_waits(
        wait_store_root=wait_store_root,
        observed_at=seams.wall_clock(),
        observe_target=seams.observe_target,
        process_generation=seams.process_generation,
    )
    _ = write_stdout(
        text=json.dumps(snapshot_payload(snapshot=snapshot), indent=2, sort_keys=True) + "\n"
    )
    publisher.inventory(snapshot=snapshot)
    has_findings = any(record.findings for record in snapshot.records)
    return int(command == "check" and has_findings)


def _ack_command(
    *,
    args: argparse.Namespace,
    wait_store_root: Path,
    seams: SessionWaitCliSeams,
    publisher: SessionWaitPublisher,
) -> int:
    result = ack_wait(
        wait_store_root=wait_store_root,
        wait_id=str(args.wait_id),
        session_id=str(args.session_id),
        acknowledged_at=seams.wall_clock(),
        retention_limit=100,
        publisher=publisher,
    )
    _ = write_stdout(text=json.dumps(asdict(result), indent=2, sort_keys=True) + "\n")
    return int(result.status != "receipt-acknowledged")


@dataclass(frozen=True, kw_only=True)
class _Invocation:
    args: argparse.Namespace
    primary: Path
    gate_store_root: Path
    wait_store_root: Path
    seams: SessionWaitCliSeams
    publisher: SessionWaitPublisher


def main(*, argv: list[str] | None = None, seams: SessionWaitCliSeams = _DEFAULT_SEAMS) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    primary = seams.primary_repository(repository=Path(str(args.repo)))
    gate_store_root, wait_store_root = _roots(
        primary=primary,
        use_tmp_directory=seams.use_tmp_directory,
    )
    # The exporter is closed AFTER the command has produced its result, so the
    # bounded shutdown allowance can never sit on a wait's deadline path. An
    # unconfigured host says so once on stderr; the result is unchanged.
    environ = dict(os.environ)
    telemetry = SessionTelemetry.from_environ(environ=environ)
    publisher = SessionWaitPublisher(
        sink=telemetry,
        associations=associations_from_environ(environ=environ),
        gate_path=wait_store_root / _GATE_STATE_NAME,
    )
    try:
        return _dispatch_command(
            parser=parser,
            invocation=_Invocation(
                args=args,
                primary=primary,
                gate_store_root=gate_store_root,
                wait_store_root=wait_store_root,
                seams=seams,
                publisher=publisher,
            ),
        )
    finally:
        _ = telemetry.close()


def _dispatch_command(*, parser: argparse.ArgumentParser, invocation: _Invocation) -> int:
    args = invocation.args
    primary = invocation.primary
    gate_store_root = invocation.gate_store_root
    wait_store_root = invocation.wait_store_root
    seams = invocation.seams
    publisher = invocation.publisher
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
            publisher=publisher,
        )
    if command in {"inventory", "check"}:
        return _inventory_command(
            command=command,
            wait_store_root=wait_store_root,
            seams=seams,
            publisher=publisher,
        )
    if command == "launch":
        return launch_command(
            args=args,
            primary=primary,
            gate_store_root=gate_store_root,
            wall_clock=seams.wall_clock,
            telemetry=publisher.sink,
        )
    if command == "complete":
        return complete_command(
            primary=primary, telemetry=publisher.sink, wall_clock=seams.wall_clock
        )
    return _ack_command(
        args=args, wait_store_root=wait_store_root, seams=seams, publisher=publisher
    )
