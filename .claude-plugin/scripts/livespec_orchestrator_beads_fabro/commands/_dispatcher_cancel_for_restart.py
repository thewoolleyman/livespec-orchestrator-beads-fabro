"""Preserve janitor-green factory runs before a planned restart cancels them."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, cast

from livespec_orchestrator_beads_fabro._store_comments import append_work_item_comment
from livespec_orchestrator_beads_fabro.commands._config import FactoryTarget as FactoryConfigTarget
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandRunner
from livespec_orchestrator_beads_fabro.commands._dispatcher_goal import minijinja_openers_in_text
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import (
    JournalFile,
    ShellCommandRunner,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_journal_rows import journal_records
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import store_config
from livespec_orchestrator_beads_fabro.commands._dispatcher_preserved_tree import publish_run_tree
from livespec_orchestrator_beads_fabro.commands._dispatcher_preserved_tree_base import (
    run_base_commit,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_preserved_tree_publish import (
    STEP_TREE,
    PreservedTree,
    PublishFailure,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_preserved_tree_record import (
    preserved_tree_body,
    unpreserved_tree_body,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port import FabroPort, FabroTarget
from livespec_orchestrator_beads_fabro.commands._fabro_port_http import (
    FabroHttpPort,
    FabroHttpResult,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port_node_outcomes import (
    fabro_node_outcomes,
    fabro_stage_node,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port_records import fabro_inspect_record

__all__: list[str] = ["cancel_for_restart", "cancel_runs"]

_INSPECT_TIMEOUT_SECONDS = 120.0
_PS_TIMEOUT_SECONDS = 120.0
_CANCEL_TIMEOUT_SECONDS = 120.0


class RestartPort(Protocol):
    """The factory operations a restart uses, bound to one selected server."""

    def live_ps(self, *, timeout_seconds: float) -> object: ...

    def inspect(self, *, run_id: str, timeout_seconds: float) -> object: ...

    def server_api(self) -> RestartApi: ...


class RestartApi(Protocol):
    """The two server routes the restart owns for an active run."""

    def run_files(self, *, run_id: str, timeout_seconds: float) -> FabroHttpResult: ...

    def cancel(self, *, run_id: str, timeout_seconds: float) -> FabroHttpResult: ...


class CommentWriter(Protocol):
    """The append-only ledger comment seam."""

    def __call__(self, *, item: str, body: str) -> None: ...


@dataclass(frozen=True, kw_only=True)
class _PreservationRequest:
    """All facts and seams that identify one active run's preservation."""

    runner: CommandRunner
    repo: Path
    factory: str
    run_id: str
    item: str
    records: tuple[dict[str, object], ...]
    port: RestartPort
    comment_writer: CommentWriter


def cancel_for_restart(
    *, repo: Path, factory: str, target: FactoryConfigTarget, fabro_bin: str
) -> int:
    """Cancel the selected factory's live runs after preserving green work."""
    runner = ShellCommandRunner()
    port = FabroPort(
        fabro_bin=fabro_bin,
        target=FabroTarget(server_url=target.server, dev_token=target.dev_token),
        runner=runner,
        cwd=repo,
    )
    records = tuple(
        dict(record)
        for record in journal_records(
            journal=JournalFile(path=repo / "tmp" / "fabro-dispatch-journal.jsonl")
        )
    )
    return cancel_runs(
        port=port,
        runner=runner,
        repo=repo,
        factory=factory,
        records=records,
        comment_writer=_comment_writer(repo=repo),
    )


def cancel_runs(
    *,
    port: RestartPort,
    runner: CommandRunner,
    repo: Path,
    factory: str,
    records: tuple[dict[str, object], ...],
    comment_writer: CommentWriter,
) -> int:
    """Preserve every green run in the live inventory, then cancel every run."""
    listing = port.live_ps(timeout_seconds=_PS_TIMEOUT_SECONDS)
    command = getattr(listing, "command", None)
    if getattr(command, "exit_code", 1) != 0:
        return 1
    for run in cast("tuple[object, ...]", getattr(listing, "runs", ())):
        run_id = getattr(run, "run_id", None)
        if not isinstance(run_id, str) or not run_id:
            continue
        inspected = port.inspect(run_id=run_id, timeout_seconds=_INSPECT_TIMEOUT_SECONDS)
        item = getattr(run, "work_item_id", None)
        payload = getattr(inspected, "payload", None)
        if isinstance(item, str) and item and _janitor_green(payload=payload):
            _preserve(
                request=_PreservationRequest(
                    runner=runner,
                    repo=repo,
                    factory=factory,
                    run_id=run_id,
                    item=item,
                    records=records,
                    port=port,
                    comment_writer=comment_writer,
                )
            )
        _ = port.server_api().cancel(run_id=run_id, timeout_seconds=_CANCEL_TIMEOUT_SECONDS)
    return 0


def _janitor_green(*, payload: object) -> bool:
    """Whether the factory record says janitor succeeded and draft publication did not."""
    record = fabro_inspect_record(payload=payload)
    if record is None:
        return False
    checkpoint = record.get("checkpoint")
    outcomes = fabro_node_outcomes(
        record=record,
        checkpoint=cast("dict[str, Any]", checkpoint) if isinstance(checkpoint, dict) else {},
    )
    states = {
        fabro_stage_node(stage=stage): outcome.get("status") for stage, outcome in outcomes.items()
    }
    return states.get("janitor") == "succeeded" and states.get("publish_draft") != "succeeded"


def _preserve(*, request: _PreservationRequest) -> None:
    """Publish one green run's committed tree, then leave its durable comment."""
    base = run_base_commit(records=request.records, work_item_id=request.item)
    published: PreservedTree | PublishFailure
    if base is None:
        published = PublishFailure(step=STEP_TREE, detail="the run's base commit was not recorded")
    else:
        published = publish_run_tree(
            port=cast("FabroHttpPort", request.port.server_api()),
            runner=request.runner,
            repo=request.repo,
            work_item_id=request.item,
            run_id=request.run_id,
            base_commit=base,
        )
    body = _comment_body(
        item=request.item,
        run_id=request.run_id,
        factory=request.factory,
        base=base,
        published=published,
    )
    if not minijinja_openers_in_text(source="livespec-preserved-tree", text=body):
        request.comment_writer(item=request.item, body=body)


def _comment_body(
    *,
    item: str,
    run_id: str,
    factory: str,
    base: str | None,
    published: PreservedTree | PublishFailure,
) -> str:
    """Render the success or fail-soft preservation comment for one cancelled run."""
    if isinstance(published, PreservedTree):
        return preserved_tree_body(
            work_item_id=item,
            run_id=run_id,
            factory=factory,
            base_commit=base or "",
            preserved=published,
        )
    return unpreserved_tree_body(
        work_item_id=item,
        run_id=run_id,
        factory=factory,
        failure=published,
    )


def _comment_writer(*, repo: Path) -> CommentWriter:
    """Bind an append-only comment write to this command's target repository."""

    def write(*, item: str, body: str) -> None:
        append_work_item_comment(path=store_config(repo=repo), work_item_id=item, body=body)

    return write
