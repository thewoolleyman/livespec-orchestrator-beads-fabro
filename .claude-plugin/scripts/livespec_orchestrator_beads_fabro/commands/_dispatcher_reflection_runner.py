"""Run-body orchestration for dispatcher reflection."""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_reflection_journal import (
    read_journal_records,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_reflection_spans import (
    emit_spans,
    emit_summary,
)

__all__: list[str] = ["RunReflectionConfig", "run_reflection"]


@dataclass(frozen=True, kw_only=True)
class RunReflectionConfig:
    journal_path: Path
    mode: str
    spans_path: Path
    deadline: float
    file_handoff_note: str
    budget_exceeded_message: str


class FindingLike(Protocol):
    @property
    def category(self) -> str: ...

    @property
    def severity(self) -> str: ...

    @property
    def count(self) -> int: ...

    @property
    def subject(self) -> str: ...


class ReportLike(Protocol):
    @property
    def mode(self) -> str: ...

    @property
    def item_count(self) -> int: ...

    @property
    def green_count(self) -> int: ...

    @property
    def failed_count(self) -> int: ...

    @property
    def blocked_count(self) -> int: ...

    @property
    def green_streak(self) -> int: ...

    @property
    def findings(self) -> tuple[FindingLike, ...]: ...


class JournalWriterLike(Protocol):
    def append(self, *, record: dict[str, object]) -> None:
        """Persist one journal record."""
        ...


class Scanner(Protocol):
    def __call__(
        self,
        *,
        outcomes: tuple[DispatchOutcome, ...],
        records: tuple[dict[str, object], ...],
        mode: str,
    ) -> ReportLike:
        """Build a reflection report from outcomes and journal records."""
        ...


def run_reflection(
    *,
    outcomes: tuple[DispatchOutcome, ...],
    journal: JournalWriterLike,
    scan: Scanner,
    config: RunReflectionConfig,
) -> None:
    """Run the scan-emit body (wrapped fail-open by `reflect`)."""
    records = read_journal_records(journal_path=config.journal_path)
    _check_budget(deadline=config.deadline, budget_exceeded_message=config.budget_exceeded_message)
    report = scan(outcomes=outcomes, records=records, mode=config.mode)
    _check_budget(deadline=config.deadline, budget_exceeded_message=config.budget_exceeded_message)
    emit_summary(report=report)
    emit_spans(report=report, spans_path=config.spans_path)
    _check_budget(deadline=config.deadline, budget_exceeded_message=config.budget_exceeded_message)
    journal.append(record=_reflection_record(report=report, mode=config.mode))
    if config.mode == "file" and report.findings:
        journal.append(
            record={
                "stage": "reflection-file-handoff",
                "findings": [
                    {"category": f.category, "severity": f.severity, "count": f.count}
                    for f in report.findings
                ],
                "note": config.file_handoff_note,
            }
        )


def _check_budget(*, deadline: float, budget_exceeded_message: str) -> None:
    if time.monotonic() > deadline:
        raise TimeoutError(budget_exceeded_message)


def _reflection_record(*, report: ReportLike, mode: str) -> dict[str, object]:
    return {
        "stage": "reflection",
        "mode": mode,
        "item_count": report.item_count,
        "green_count": report.green_count,
        "failed_count": report.failed_count,
        "blocked_count": report.blocked_count,
        "green_streak": report.green_streak,
        "findings": [
            {
                "category": f.category,
                "severity": f.severity,
                "count": f.count,
                "subject": f.subject,
            }
            for f in report.findings
        ],
    }
