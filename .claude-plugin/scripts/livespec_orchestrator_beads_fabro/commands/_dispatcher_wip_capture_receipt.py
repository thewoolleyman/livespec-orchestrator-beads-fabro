"""The fail-soft ledger receipt for an ended run's newest WIP capture."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from livespec_orchestrator_beads_fabro._store_comments import (
    append_work_item_comment,
    read_work_item_comments,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandRunner,
    JournalWriter,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_goal import (
    minijinja_openers_in_text,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import ShellCommandRunner
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import store_config
from livespec_orchestrator_beads_fabro.commands._dispatcher_preserved_tree_record import (
    PRESERVED_TREE_MARKER,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_terminal_ref_measurement import (
    PreservedRef,
    terminal_ref_lines,
    terminal_refs,
)
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt
from livespec_orchestrator_beads_fabro.errors import (
    BeadsCommandError,
    BeadsConnectionError,
    BeadsMappingError,
    BeadsTenantMissingError,
    ConnectionPrefixMissingError,
    WorkItemNotFoundError,
)

__all__: list[str] = [
    "WipCapture",
    "WipCaptureUnobservable",
    "latest_wip_capture",
    "receipt_body",
    "record_wip_capture_receipt",
]

_WIP_REF_PREFIX = "refs/livespec/wip"
_REMOTE = "origin"
_GIT_TIMEOUT_SECONDS = 5.0
_LS_REMOTE_FIELDS = 2
_RECEIPT_ERROR_STAGE = "wip-capture-receipt-error"
_LEDGER_ERRORS: tuple[type[Exception], ...] = (
    WorkItemNotFoundError,
    BeadsCommandError,
    BeadsConnectionError,
    BeadsMappingError,
    BeadsTenantMissingError,
    ConnectionPrefixMissingError,
)


@dataclass(frozen=True, kw_only=True)
class WipCapture:
    """One immutable work-in-progress ref and the commit origin reports at it."""

    ref: str
    commit: str


@dataclass(frozen=True, kw_only=True)
class WipCaptureUnobservable:
    """Origin declined the capture listing, so absence cannot be claimed."""

    detail: str


def latest_wip_capture(
    *, work_item_id: str, run_id: str, refs: dict[str, str]
) -> WipCapture | None:
    """The highest numeric capture in this exact work-item/run namespace."""
    prefix = f"{_WIP_REF_PREFIX}/{work_item_id}/{run_id}/"
    captures = [
        (int(suffix), WipCapture(ref=ref, commit=commit))
        for ref, commit in refs.items()
        if ref.startswith(prefix) and (suffix := ref.removeprefix(prefix)).isdecimal()
    ]
    return None if not captures else max(captures, key=lambda capture: capture[0])[1]


def record_wip_capture_receipt(
    *,
    repo: Path,
    work_item_id: str,
    run_id: str,
    factory: str,
    journal: JournalWriter,
    runner: CommandRunner | None = None,
) -> None:
    """Name this non-merged run's capture without delaying its disposition."""
    try:
        _record_wip_capture_receipt(
            repo=repo,
            work_item_id=work_item_id,
            run_id=run_id,
            factory=factory,
            journal=journal,
            runner=runner,
        )
    except (*_LEDGER_ERRORS, OSError):
        return


def _record_wip_capture_receipt(
    *,
    repo: Path,
    work_item_id: str,
    run_id: str,
    factory: str,
    journal: JournalWriter,
    runner: CommandRunner | None,
) -> None:
    """Read, deduplicate and append one receipt, letting the caller fail soft."""
    active_runner = runner if runner is not None else ShellCommandRunner()
    comments = _comments(repo=repo, work_item_id=work_item_id)
    observed = _read_capture(
        runner=active_runner, repo=repo, work_item_id=work_item_id, run_id=run_id
    )
    body = receipt_body(
        work_item_id=work_item_id,
        run_id=run_id,
        factory=factory,
        observed=observed,
        terminal_refs=terminal_refs(
            runner=active_runner, repo=repo, run_id=run_id, comments=comments
        ),
    )
    if any(getattr(comment, "text", None) == body for comment in comments):
        return
    findings = minijinja_openers_in_text(source=PRESERVED_TREE_MARKER, text=body)
    if findings:
        _error(journal=journal, work_item_id=work_item_id, run_id=run_id, reason="template-opener")
        return
    append_work_item_comment(path=store_config(repo=repo), work_item_id=work_item_id, body=body)


def _read_capture(
    *, runner: CommandRunner, repo: Path, work_item_id: str, run_id: str
) -> WipCapture | WipCaptureUnobservable | None:
    result = runner.run(
        argv=["git", "ls-remote", _REMOTE, f"{_WIP_REF_PREFIX}/{work_item_id}/{run_id}/*"],
        cwd=repo,
        timeout_seconds=_GIT_TIMEOUT_SECONDS,
    )
    if result.exit_code != 0:
        return WipCaptureUnobservable(detail=f"git ls-remote exited {result.exit_code}")
    refs = {
        fields[1]: fields[0]
        for line in result.stdout.splitlines()
        if len(fields := line.split()) == _LS_REMOTE_FIELDS
    }
    return latest_wip_capture(work_item_id=work_item_id, run_id=run_id, refs=refs)


def receipt_body(
    *,
    work_item_id: str,
    run_id: str,
    factory: str,
    observed: WipCapture | WipCaptureUnobservable | None,
    terminal_refs: tuple[PreservedRef, ...],
) -> str:
    lines = [
        PRESERVED_TREE_MARKER,
        "",
        f"work-item: {work_item_id}",
        f"run id: {run_id}",
        f"factory: {factory}",
    ]
    if isinstance(observed, WipCapture):
        lines.extend(
            [
                f"work-in-progress ref: {observed.ref}",
                f"commit id: {observed.commit}",
            ]
        )
    elif isinstance(observed, WipCaptureUnobservable):
        lines.append("work-in-progress preservation could not be determined")
    elif not terminal_refs:
        lines.append("the run preserved no tree; the run has no work-in-progress ref")
    lines.extend(terminal_ref_lines(refs=terminal_refs))
    return "\n".join(lines)


def _comments(*, repo: Path, work_item_id: str) -> tuple[object, ...]:
    """Read durable records once; an unreadable ledger supplies no candidates."""
    comments = attempt(
        action=lambda: read_work_item_comments(
            path=store_config(repo=repo), work_item_id=work_item_id
        ),
        exceptions=(*_LEDGER_ERRORS, OSError),
    )
    return () if isinstance(comments, AttemptFailure) else tuple(comments)


def _error(*, journal: JournalWriter, work_item_id: str, run_id: str, reason: str) -> None:
    try:
        journal.append(
            record={
                "stage": _RECEIPT_ERROR_STAGE,
                "work_item_id": work_item_id,
                "run_id": run_id,
                "reason": reason,
            }
        )
    except OSError:
        return
