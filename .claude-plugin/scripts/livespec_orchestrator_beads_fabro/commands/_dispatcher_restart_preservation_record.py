"""Durable restart-preservation comment writes that never block a factory restart."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.errors import (
    BeadsCommandError,
    BeadsConnectionError,
    BeadsMappingError,
    BeadsTenantMissingError,
    ConnectionPrefixMissingError,
    WorkItemNotFoundError,
)

__all__: list[str] = ["RestartPreservationComment", "append_restart_preservation_comment"]

_LEDGER_WRITE_ERRORS = (
    WorkItemNotFoundError,
    BeadsCommandError,
    BeadsConnectionError,
    BeadsMappingError,
    BeadsTenantMissingError,
    ConnectionPrefixMissingError,
    OSError,
)


@dataclass(frozen=True, kw_only=True)
class RestartPreservationComment:
    """The names a restart-preservation comment must leave durable."""

    work_item_id: str
    run_id: str
    factory: str
    body: str


def append_restart_preservation_comment(
    *,
    repo: Path,
    journal: JournalFile,
    comment: RestartPreservationComment,
    resolve_config: Callable[..., object],
    append_comment: Callable[..., object],
) -> None:
    """Journal an unwritable comment while allowing the restart sweep to proceed."""
    try:
        _ = append_comment(
            path=resolve_config(repo=repo),
            work_item_id=comment.work_item_id,
            body=comment.body,
        )
    except _LEDGER_WRITE_ERRORS as error:
        journal.append(
            record={
                "stage": "restart-preserved-tree-record-error",
                "work_item_id": comment.work_item_id,
                "run_id": comment.run_id,
                "factory": comment.factory,
                "reason": type(error).__name__,
            }
        )
