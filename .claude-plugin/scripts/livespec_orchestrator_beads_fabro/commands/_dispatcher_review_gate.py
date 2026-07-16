"""Review-gate telemetry derived from Fabro run events."""

from __future__ import annotations

import time
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from livespec_orchestrator_beads_fabro.commands._dispatcher_decision_journal import (
    review_gate_ship_on_cap_journal_record,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import (
    DispatchPlan,
    fabro_events_argv,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_review_gate_otlp import (
    emit_review_gate_span,
    review_gate_request_line,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_review_gate_parse import (
    ReviewGateTelemetry,
    parse_review_gate_events,
)

__all__: list[str] = [
    "ReviewGateEmission",
    "ReviewGateTelemetry",
    "emit_review_gate_from_fabro_events",
    "emit_review_gate_span",
    "parse_review_gate_events",
    "review_gate_request_line",
]

_OTLP_SERVICE_NAME = "livespec-dispatcher"
_OTLP_SERVICE_NAMESPACE = "livespec-family"
_OTLP_SCOPE_NAME = "livespec.dispatcher.review-gate"
_OTLP_SCOPE_VERSION = "0.1.0"
_SPAN_KIND_INTERNAL = 1
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

    The helper is fail-soft: telemetry loss must not change the dispatch result.
    Runs without a resolved Fabro run id are pre-run refusals or unobservable CLI
    failures, so there is no event stream to query.
    """
    try:
        _emit_review_gate_from_fabro_events(emission=emission)
    except Exception as exc:
        _append_review_gate_skip(
            emission=emission,
            reason=str(exc) or type(exc).__name__,
            exit_code=None,
        )


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
    telemetry = parse_review_gate_events(events_jsonl=events.stdout)
    emit_review_gate_span(
        telemetry=telemetry,
        spans_path=emission.spans_path,
        work_item_id=emission.work_item_id,
        dispatch_id=emission.dispatch_id,
        run_id=emission.run_id,
        now_ns=time.time_ns(),
    )
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
    if telemetry.shipped_on_cap:
        emission.journal.append(
            record=review_gate_ship_on_cap_journal_record(
                work_item_id=emission.work_item_id,
                run_id=emission.run_id,
                review_verdict=telemetry.verdict,
                review_fix_rounds=telemetry.fix_rounds,
                review_hit_cap=telemetry.hit_cap,
                pr_shipped_on_cap=telemetry.shipped_on_cap,
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
    with suppress(Exception):
        emission.journal.append(record=record)
