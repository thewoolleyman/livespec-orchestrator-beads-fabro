"""Review-gate telemetry derived from Fabro run events."""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from returns.functions import tap
from returns.result import Success

from livespec_orchestrator_beads_fabro.commands._dispatcher_decision_journal import (
    auto_disposition_journal_record,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import (
    DispatchPlan,
    fabro_events_argv,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_review_gate_parse import (
    ReviewGateTelemetry,
    parse_review_gate_events,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_review_gate_span import (
    emit_review_gate_span,
    review_gate_request_line,
)

__all__: list[str] = [
    "ReviewGateEmission",
    "ReviewGateTelemetry",
    "emit_review_gate_from_fabro_events",
    "emit_review_gate_span",
    "parse_review_gate_events",
    "review_gate_request_line",
]

_FABRO_EVENTS_TIMEOUT_SECONDS = 60.0


class CommandRunner(Protocol):
    """Subprocess seam needed to query `fabro events`."""

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
    ) -> CommandResult:
        """Run argv and return a completed command result."""
        ...


class CommandResult(Protocol):
    """Command result fields consumed by the review-gate helper."""

    @property
    def exit_code(self) -> int: ...

    @property
    def stdout(self) -> str: ...

    @property
    def stderr(self) -> str: ...


class JournalWriter(Protocol):
    """Append-only journal seam."""

    def append(self, *, record: dict[str, object]) -> None:
        """Persist one journal record."""
        ...


@dataclass(frozen=True, kw_only=True)
class ReviewGateEmission:
    """Inputs needed to query Fabro events and emit the review-gate span."""

    plan: DispatchPlan
    runner: CommandRunner
    journal: JournalWriter
    spans_path: Path
    work_item_id: str
    dispatch_id: str
    run_id: str | None


def emit_review_gate_from_fabro_events(*, emission: ReviewGateEmission) -> None:
    """Query Fabro events for a terminal run and append the review-gate span.

    Runs without a resolved Fabro run id are pre-run refusals or unobservable CLI
    failures, so there is no event stream to query. A failed `fabro events`
    command is an expected telemetry miss and is journaled as a skip.
    Unexpected span or journal write errors propagate after the dispatcher's
    critical post-run dispositions have already committed.
    """
    _emit_review_gate_from_fabro_events(emission=emission)


def _emit_review_gate_from_fabro_events(*, emission: ReviewGateEmission) -> None:
    if emission.run_id is None:
        _append_review_gate_skip(
            emission=emission,
            reason="fabro run id unavailable",
            exit_code=None,
        )
        return
    events = emission.runner.run(
        argv=fabro_events_argv(plan=emission.plan, run_id=emission.run_id),
        cwd=emission.plan.repo,
        timeout_seconds=_FABRO_EVENTS_TIMEOUT_SECONDS,
    )
    if events.exit_code != 0:
        _append_review_gate_skip(
            emission=emission,
            reason="fabro events command failed",
            exit_code=events.exit_code,
        )
        return
    telemetry = parse_review_gate_events(
        events_jsonl=events.stdout,
        review_fix_visit_cap=emission.plan.review_fix_visit_cap,
    )
    _ = (
        Success(telemetry)
        .map(tap(lambda value: _emit_review_gate_span(emission=emission, telemetry=value)))
        .map(tap(lambda value: _append_review_gate_telemetry(emission=emission, telemetry=value)))
    )


def _emit_review_gate_span(*, emission: ReviewGateEmission, telemetry: ReviewGateTelemetry) -> None:
    emit_review_gate_span(
        telemetry=telemetry,
        spans_path=emission.spans_path,
        work_item_id=emission.work_item_id,
        dispatch_id=emission.dispatch_id,
        run_id=emission.run_id or "",
        now_ns=time.time_ns(),
    )


def _append_review_gate_telemetry(
    *, emission: ReviewGateEmission, telemetry: ReviewGateTelemetry
) -> None:
    emission.journal.append(
        record={
            "stage": "review-gate-telemetry",
            "work_item_id": emission.work_item_id,
            "run_id": emission.run_id,
            "review_verdict": telemetry.verdict,
            "review_fix_rounds": telemetry.fix_rounds,
            "review_hit_cap": telemetry.hit_cap,
            "pr_shipped_on_cap": telemetry.shipped_on_cap,
        }
    )
    _append_review_gate_disposition(emission=emission, telemetry=telemetry)


def _append_review_gate_disposition(
    *, emission: ReviewGateEmission, telemetry: ReviewGateTelemetry
) -> None:
    if telemetry.shipped_on_cap:
        emission.journal.append(
            record=auto_disposition_journal_record(
                work_item_id=emission.work_item_id,
                disposition="ship-on-cap",
                governing_settings=("merge_on_review_cap", "review_fix_cap"),
            )
        )
        return
    if telemetry.hit_cap:
        emission.journal.append(
            record=auto_disposition_journal_record(
                work_item_id=emission.work_item_id,
                disposition="cap-exceeded-escalation",
                governing_settings=("review_fix_cap",),
            )
        )


def _append_review_gate_skip(
    *, emission: ReviewGateEmission, reason: str, exit_code: int | None
) -> None:
    record: dict[str, object] = {
        "stage": "review-gate-telemetry-skipped",
        "work_item_id": emission.work_item_id,
        "run_id": emission.run_id,
        "reason": reason,
    }
    if exit_code is not None:
        record["exit_code"] = exit_code
    emission.journal.append(record=record)
