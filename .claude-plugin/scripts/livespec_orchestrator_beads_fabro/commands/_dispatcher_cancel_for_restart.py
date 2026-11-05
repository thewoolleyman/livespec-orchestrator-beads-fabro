"""Preserve eligible factory runs before an attended factory restart.

This command is deliberately separate from reconciliation: a restart is an
operator-requested sweep of *live* runs, not an orphan decision.  The only
run which has work worth recovering here is one which has already passed its
janitor.  Its committed files are copied through the forge Git Data API before
the factory's HTTP cancellation endpoint is called.
"""

from __future__ import annotations

import argparse
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from livespec_orchestrator_beads_fabro._store_comments import append_work_item_comment
from livespec_orchestrator_beads_fabro.commands._config import (
    resolve_fabro_bin,
    resolve_fabro_factory,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import (
    JournalFile,
    ShellCommandRunner,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_journal_tail import journal_tail_records
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import journal_path, store_config
from livespec_orchestrator_beads_fabro.commands._dispatcher_preserved_tree import publish_run_tree
from livespec_orchestrator_beads_fabro.commands._dispatcher_preserved_tree_base import (
    run_base_commit,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_preserved_tree_publish import (
    STEP_FILES_READ,
    PreservedTree,
    PublishFailure,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_preserved_tree_record import (
    unpreserved_tree_body,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port import FabroPort, FabroTarget
from livespec_orchestrator_beads_fabro.commands._fabro_port_http import FabroHttpPort
from livespec_orchestrator_beads_fabro.commands._fabro_port_records import FabroRunSummary
from livespec_orchestrator_beads_fabro.io import write_stderr, write_stdout

__all__: list[str] = [
    "add_cancel_for_restart_arguments",
    "cancel_for_restart",
    "run_cancel_for_restart_command",
]

_PS_TIMEOUT_SECONDS = 60.0
_STATE_TIMEOUT_SECONDS = 60.0
_CANCEL_TIMEOUT_SECONDS = 120.0


@dataclass(frozen=True, kw_only=True)
class RestartRun:
    """The live factory record needed by the restart cancellation sequence."""

    run_id: str
    work_item_id: str | None
    janitor_succeeded: bool


@dataclass(frozen=True, kw_only=True)
class RestartSweep:
    """The sweep-wide collaborators every preservation attempt shares."""

    repo: Path
    factory: str
    http: FabroHttpPort
    journal: JournalFile
    records: tuple[dict[str, object], ...]
    runner: ShellCommandRunner


def add_cancel_for_restart_arguments(*, parser: argparse.ArgumentParser) -> None:
    """Add the narrow, explicitly factory-addressed restart surface."""
    _ = parser.add_argument("--factory", required=True)
    _ = parser.add_argument("--repo", default=None)
    _ = parser.add_argument("--journal", default=None)


def run_cancel_for_restart_command(*, args: argparse.Namespace) -> int:
    """Cancel active factory runs, preserving janitor-green committed trees first."""
    repo = Path(args.repo) if args.repo is not None else Path.cwd()
    factory = resolve_fabro_factory(cwd=repo, factory=args.factory)
    if factory.server is None:
        write_stderr(
            text=(
                "dispatcher cancel-for-restart refused: "
                f"factory {factory.name} has no server url\n"
            )
        )
        return 2
    runner = ShellCommandRunner()
    port = FabroPort(
        fabro_bin=factory.fabro_bin or resolve_fabro_bin(cwd=repo),
        target=FabroTarget(server_url=factory.server, dev_token=factory.dev_token),
        runner=runner,
        cwd=repo,
    )
    journal = JournalFile(path=journal_path(args=args, repo=repo))
    result = cancel_for_restart(
        repo=repo,
        factory=factory.name,
        port=port,
        journal=journal,
        records=journal_tail_records(journal_path=journal.path),
        runner=runner,
    )
    for line in result:
        _ = write_stdout(text=line + "\n")
    return 0


def cancel_for_restart(
    *,
    repo: Path,
    factory: str,
    port: FabroPort,
    journal: JournalFile,
    records: tuple[dict[str, object], ...],
    runner: ShellCommandRunner,
) -> tuple[str, ...]:
    """Perform one preservation-before-cancellation sweep over a factory's live runs.

    A failed *file read* is the one best-effort arm: it leaves an explicit
    ``livespec-preserved-tree`` comment then cancellation continues, because a
    restart cannot wait on a server tree it cannot read.  Any later forge
    publication failure leaves that eligible run alive: cancelling it would
    violate the ordering guarantee that a preservation ref exists first.
    """
    listed = port.live_ps(timeout_seconds=_PS_TIMEOUT_SECONDS)
    if listed.command.exit_code != 0:
        return (f"ERROR factory={factory} could not list active runs",)
    output: list[str] = []
    http = port.server_api()
    sweep = RestartSweep(
        repo=repo, factory=factory, http=http, journal=journal, records=records, runner=runner
    )
    for summary in listed.runs:
        run = _restart_run(summary=summary, http=http)
        if run is None:
            continue
        allowed = True
        if run.janitor_succeeded:
            allowed = _preserve_before_cancel(sweep=sweep, run=run)
        if not allowed:
            output.append(f"HELD {run.run_id} factory={factory} preservation-ref-missing")
            continue
        cancelled = http.cancel(run_id=run.run_id, timeout_seconds=_CANCEL_TIMEOUT_SECONDS)
        if cancelled.succeeded:
            output.append(f"CANCELLED {run.run_id} factory={factory}")
        else:
            output.append(f"ERROR {run.run_id} factory={factory} cancellation-failed")
    return tuple(output)


def _restart_run(*, summary: FabroRunSummary, http: FabroHttpPort) -> RestartRun | None:
    """Read the run state once to decide whether its janitor has succeeded."""
    state = http.run_state(run_id=summary.run_id, timeout_seconds=_STATE_TIMEOUT_SECONDS)
    if not state.succeeded:
        return None
    return RestartRun(
        run_id=summary.run_id,
        work_item_id=summary.work_item_id,
        janitor_succeeded=_janitor_succeeded(payload=state.payload),
    )


def _preserve_before_cancel(*, sweep: RestartSweep, run: RestartRun) -> bool:
    """Publish one eligible run, returning whether cancellation may proceed."""
    if run.work_item_id is None:
        return False
    base = run_base_commit(records=sweep.records, work_item_id=run.work_item_id)
    if base is None:
        return False
    published = publish_run_tree(
        port=sweep.http,
        runner=sweep.runner,
        repo=sweep.repo,
        work_item_id=run.work_item_id,
        run_id=run.run_id,
        base_commit=base,
    )
    if isinstance(published, PreservedTree):
        sweep.journal.append(
            record={
                "stage": "restart-preserved-tree",
                "work_item_id": run.work_item_id,
                "run_id": run.run_id,
                "factory": sweep.factory,
                "preservation_ref": published.ref,
                "base_commit": base,
            }
        )
        return True
    _record_unpreserved(
        sweep=sweep, run_id=run.run_id, work_item_id=run.work_item_id, failure=published
    )
    # The stated recovery arm authorizes cancellation after an unreadable file
    # read only.  A forge failure does not prove a ref exists, so leave the run
    # untouched for the operator rather than losing its only recoverable tree.
    return published.step == STEP_FILES_READ


def _record_unpreserved(
    *, sweep: RestartSweep, run_id: str, work_item_id: str, failure: PublishFailure
) -> None:
    """Durably name an unreadable tree before the restart cancels its run."""
    sweep.journal.append(
        record={
            "stage": "restart-preserved-tree-unpreserved",
            "work_item_id": work_item_id,
            "run_id": run_id,
            "factory": sweep.factory,
            "failed_step": failure.step,
            "detail": failure.detail,
        }
    )
    # The body deliberately contains the required marker and the files-read
    # step, while the free-form factory diagnostic stays in the journal.
    append_work_item_comment(
        path=store_config(repo=sweep.repo),
        work_item_id=work_item_id,
        body=unpreserved_tree_body(
            work_item_id=work_item_id,
            run_id=run_id,
            factory=sweep.factory,
            failure=failure,
        ),
    )


def _janitor_succeeded(*, payload: object | None) -> bool:
    """Whether the server's state projection records a succeeded janitor node.

    Fabro has emitted both ``{node, status}`` and ``{name, state}`` stage
    records.  Walking mappings keeps the decision tied to one run-state read
    while accepting both observed shapes; a plain text match would let another
    node's diagnostic fabricate a green janitor.
    """
    return any(_is_green_janitor(record=record) for record in _mappings(value=payload))


def _mappings(*, value: object | None) -> Iterable[Mapping[str, object]]:
    if isinstance(value, dict):
        record = cast("dict[object, object]", value)
        strings = {str(key): held for key, held in record.items()}
        yield strings
        for nested in record.values():
            yield from _mappings(value=nested)
    elif isinstance(value, list):
        for nested in cast("list[object]", value):
            yield from _mappings(value=nested)


def _is_green_janitor(*, record: Mapping[str, object]) -> bool:
    node = record.get("node", record.get("name", record.get("stage")))
    status = record.get("status", record.get("state", record.get("outcome")))
    return (
        isinstance(node, str)
        and node == "janitor"
        and isinstance(status, str)
        and status in {"succeeded", "success", "green"}
    )
