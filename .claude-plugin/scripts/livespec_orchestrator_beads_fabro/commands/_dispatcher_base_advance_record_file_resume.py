"""Journal the eligible-record-files hand-off before Scenario 184 resumes."""

from __future__ import annotations

from typing import Protocol, cast

__all__: list[str] = ["journal_record_file_resume"]


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
