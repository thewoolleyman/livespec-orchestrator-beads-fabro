"""Journal the eligible-record-files hand-off before Scenario 184 resumes."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol, TypeVar, cast

from livespec_orchestrator_beads_fabro.commands._dispatcher_base_advance import (
    BASE_ADVANCED_AFTER_ARMING,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_base_advance_record_files import (
    record_file_resume_paths,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome

__all__: list[str] = [
    "journal_record_file_resume",
    "resume_overtaken_record_files",
    "resume_record_file_conflict",
]

_ResumeOutcome = TypeVar("_ResumeOutcome")


class _JournalWriter(Protocol):
    """The append-only journal seam shared by the Dispatcher terminal paths."""

    def append(self, *, record: dict[str, object]) -> None:
        """Persist one structured Dispatcher journal row."""


def journal_record_file_resume(
    *,
    journal: _JournalWriter,
    work_item_id: str,
    run_id: str | None,
    pr_number: int | None,
    pr_head: str,
    **measurements: str | tuple[str, ...],
) -> None:
    """Record the complete measured hand-off before the automatic resume.

    The caller invokes this only after `record_file_resume_paths` proved the
    non-empty set is wholly declared.  Keeping the row here, rather than
    rebuilding it at a later lifecycle step, makes the journal the exact record
    of the run, pull request, heads and paths that admitted the automatic path.
    """
    default_branch_tip = cast("str", measurements["default_branch_tip"])
    conflicted_paths = cast("tuple[str, ...]", measurements["conflicted_paths"])
    journal.append(
        record={
            "stage": "base-advanced-record-files-resume",
            "work_item_id": work_item_id,
            "run_id": run_id,
            "pr_number": pr_number,
            "pr_head": pr_head,
            "default_branch_tip": default_branch_tip,
            "conflicted_paths": list(conflicted_paths),
        }
    )


def resume_record_file_conflict(  # noqa: PLR0913 -- each field is a separately measured contract requirement.
    *,
    journal: _JournalWriter,
    work_item_id: str,
    run_id: str | None,
    pr_number: int | None,
    pr_head: str,
    default_branch_tip: str,
    conflicted_paths: tuple[str, ...],
    resolve_ready: Callable[..., None],
    resume: Callable[..., _ResumeOutcome],
) -> _ResumeOutcome:
    """Journal, release, and resume the one record-file-only conflict arm.

    The callbacks keep the ordering here while their callers keep ownership of
    the lifecycle and resume mechanisms.  In particular, this function cannot
    accidentally resume before the durable row and ready transition exist.
    """
    journal_record_file_resume(
        journal=journal,
        work_item_id=work_item_id,
        run_id=run_id,
        pr_number=pr_number,
        pr_head=pr_head,
        default_branch_tip=default_branch_tip,
        conflicted_paths=conflicted_paths,
    )
    resolve_ready(work_item_id=work_item_id)
    return resume(work_item_id=work_item_id)


def resume_overtaken_record_files(
    *,
    outcome: DispatchOutcome,
    config_text: str,
    journal: _JournalWriter,
    resolve_ready: Callable[..., None],
    resume: Callable[..., DispatchOutcome],
) -> DispatchOutcome | None:
    """Resume an overtaken armed pull request whose conflicts are all declared record files.

    Returns the resumed dispatch's outcome, or `None` for every ending this arm
    does not admit: an outcome that is not the overtaken-arming cause, a
    conflict set that could not be measured, a head or tip the forge never
    reported, or any conflicted path that is not a declared record file.
    """
    measured = outcome.base_advanced
    if measured is None or measured.cause != BASE_ADVANCED_AFTER_ARMING:
        return None
    if (
        measured.conflicted_paths is None
        or measured.pr_head is None
        or measured.default_branch_tip is None
    ):
        return None
    paths = record_file_resume_paths(
        config_text=config_text, conflicted_paths=measured.conflicted_paths
    )
    if paths is None:
        return None
    return resume_record_file_conflict(
        journal=journal,
        work_item_id=outcome.work_item_id,
        run_id=outcome.fabro_run_id,
        pr_number=outcome.pr_number,
        pr_head=measured.pr_head,
        default_branch_tip=measured.default_branch_tip,
        conflicted_paths=paths,
        resolve_ready=resolve_ready,
        resume=resume,
    )
