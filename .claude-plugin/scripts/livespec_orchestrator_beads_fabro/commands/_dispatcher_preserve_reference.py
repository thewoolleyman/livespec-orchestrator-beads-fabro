"""Preserve failed/blocked Fabro run work by reference on the ledger."""

from __future__ import annotations

import argparse
import tempfile
from dataclasses import dataclass
from pathlib import Path

from livespec_orchestrator_beads_fabro._beads_client import make_beads_client
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandRunner,
    DispatchOutcome,
    JournalWriter,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import ShellCommandRunner
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import store_config
from livespec_orchestrator_beads_fabro.commands._dispatcher_preserve_reference_body import (
    FABRO_DIFF_ARTIFACT_GLOB,
    artifact_pointer_body,
    dump_failed_body,
    error_pointer_body,
    missing_artifact_body,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port import FabroPort, FabroTarget
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt
from livespec_orchestrator_beads_fabro.errors import (
    BeadsCommandError,
    BeadsConnectionError,
    BeadsMappingError,
    BeadsTenantMissingError,
    ConnectionPrefixMissingError,
    WorkItemNotFoundError,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "PointerRecord",
    "pointer_record_for_run",
    "preserve_checkpointed_work_reference",
]

_DUMP_TIMEOUT_SECONDS = 300.0
_LEDGER_WRITE_ERRORS = (
    WorkItemNotFoundError,
    BeadsCommandError,
    BeadsConnectionError,
    BeadsMappingError,
    BeadsTenantMissingError,
)


@dataclass(frozen=True, kw_only=True)
class PointerRecord:
    body: str
    digest: str
    artifact_present: bool
    run_id: str
    server_url: str


def preserve_checkpointed_work_reference(
    *,
    args: argparse.Namespace,
    repo: Path,
    item: WorkItem,
    outcome: DispatchOutcome,
    journal: JournalWriter,
    runner: CommandRunner | None = None,
) -> None:
    """Write a preserve-by-reference comment for failed/blocked Fabro runs."""
    if outcome.status not in {"blocked", "failed"}:
        return
    run_id = outcome.fabro_run_id
    target = getattr(args, "fabro_factory_target", None)
    server = getattr(target, "server", None)
    server_url = server if isinstance(server, str) and server else None
    if run_id is None or server_url is None:
        journal.append(
            record={
                "stage": "preserve-by-reference-skipped",
                "work_item_id": item.id,
                "reason": "missing-run-or-server",
                "run_id": run_id,
                "factory_server_url": server_url,
            }
        )
        return
    command_runner = runner if runner is not None else ShellCommandRunner()
    pointer = attempt(
        action=lambda: pointer_record_for_run(
            fabro_bin=str(args.fabro_bin),
            repo=repo,
            item_id=item.id,
            run_id=run_id,
            server_url=server_url,
            command_runner=command_runner,
        ),
        exceptions=(OSError,),
    )
    if isinstance(pointer, AttemptFailure):
        body, digest = error_pointer_body(
            run_id=run_id,
            server_url=server_url,
            error=pointer.error,
        )
        _write_error(
            journal=journal,
            item_id=item.id,
            reason=type(pointer.error).__name__,
            pointer=PointerRecord(
                body=body,
                digest=digest,
                artifact_present=False,
                run_id=run_id,
                server_url=server_url,
            ),
        )
        return
    _write_comment(
        repo=repo,
        item_id=item.id,
        journal=journal,
        pointer=pointer,
    )


def pointer_record_for_run(
    *,
    fabro_bin: str,
    repo: Path,
    item_id: str,
    run_id: str,
    server_url: str,
    command_runner: CommandRunner,
) -> PointerRecord:
    """Export one run and build the pointer body that references it.

    PUBLIC because the run reconciler preserves work for runs no dispatch of
    this process ever launched, so it has no `DispatchOutcome` to hand the
    outcome-shaped entry point above — but it must produce the SAME pointer
    body, or a pointer written by one path would not be recognized by the
    other's read-back.

    The export goes through a `FabroPort` built from the SAME `server_url` the
    pointer body prints, so the record names the factory the bytes actually
    came from and this module issues no engine invocation of its own.
    """
    port = FabroPort(
        fabro_bin=fabro_bin,
        target=FabroTarget(server_url=server_url),
        runner=command_runner,
        cwd=repo,
    )
    with tempfile.TemporaryDirectory(prefix=f"fabro-preserve-{item_id}-") as raw_dir:
        output_dir = Path(raw_dir)
        dumped = port.dump(
            run_id=run_id,
            output_dir=output_dir,
            timeout_seconds=_DUMP_TIMEOUT_SECONDS,
        ).command
        artifacts = tuple(
            sorted(path for path in output_dir.glob(FABRO_DIFF_ARTIFACT_GLOB) if path.is_file())
        )
        artifact_present = dumped.exit_code == 0 and bool(artifacts)
        if dumped.exit_code != 0:
            body, digest = dump_failed_body(
                run_id=run_id,
                server_url=server_url,
                command=dumped,
                fabro_bin=fabro_bin,
            )
        elif artifacts:
            body, digest = artifact_pointer_body(
                run_id=run_id,
                server_url=server_url,
                artifacts=artifacts,
                export_dir=output_dir,
                fabro_bin=fabro_bin,
            )
        else:
            body, digest = missing_artifact_body(
                run_id=run_id, server_url=server_url, fabro_bin=fabro_bin
            )
    return PointerRecord(
        body=body,
        digest=digest,
        artifact_present=artifact_present,
        run_id=run_id,
        server_url=server_url,
    )


def _write_comment(
    *,
    repo: Path,
    item_id: str,
    journal: JournalWriter,
    pointer: PointerRecord,
) -> None:
    written = attempt(
        action=lambda: make_beads_client(config=store_config(repo=repo)).add_comment(
            issue_id=item_id,
            body=pointer.body,
        ),
        exceptions=(*_LEDGER_WRITE_ERRORS, ConnectionPrefixMissingError),
    )
    if isinstance(written, AttemptFailure):
        _write_error(
            journal=journal,
            item_id=item_id,
            reason=type(written.error).__name__,
            pointer=pointer,
        )
        return
    journal.append(
        record={
            "stage": "preserve-by-reference",
            "work_item_id": item_id,
            "artifact_path": FABRO_DIFF_ARTIFACT_GLOB,
            "artifact_present": pointer.artifact_present,
            "run_id": pointer.run_id,
            "factory_server_url": pointer.server_url,
            "artifact_digest": pointer.digest,
        }
    )


def _write_error(
    *,
    journal: JournalWriter,
    item_id: str,
    reason: str,
    pointer: PointerRecord,
) -> None:
    journal.append(
        record={
            "stage": "preserve-by-reference-error",
            "work_item_id": item_id,
            "reason": reason,
            "run_id": pointer.run_id,
            "factory_server_url": pointer.server_url,
            "artifact_digest": pointer.digest,
            "pointer_body": pointer.body,
        }
    )
