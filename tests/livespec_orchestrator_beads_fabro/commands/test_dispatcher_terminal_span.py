"""Terminal dispatch telemetry for outcome and ACP-attempt accounting."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from livespec_orchestrator_beads_fabro.commands._dispatcher_correlation import DispatchCorrelation
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_terminal_span import (
    ATTEMPT_SPAN_NAME,
    TERMINAL_SPAN_NAME,
    TerminalAttempt,
    emit_terminal_span,
    terminal_attempts,
    terminal_outcome,
    terminal_request_line,
)
from livespec_orchestrator_beads_fabro.commands._otel_scrub import ATTRIBUTE_ALLOWLIST

from tests.livespec_orchestrator_beads_fabro.commands.test_dispatcher_loop_finish import (
    _item,
    _plan,
)
from tests.livespec_orchestrator_beads_fabro.commands.test_dispatcher_loop_finish import (
    _outcome as _finish_outcome,
)


def _outcome(*, status: str = "green", verdict: str | None = None) -> DispatchOutcome:
    return DispatchOutcome(
        work_item_id="bd-ib-welwbc",
        status=status,
        stage="fabro-run",
        verdict=verdict,
        pr_number=None,
        merge_sha=None,
        detail="terminal",
    )


def _correlation() -> DispatchCorrelation:
    return DispatchCorrelation(
        work_item_id="bd-ib-welwbc",
        dispatch_id="01M6NF6MZCVHJ9MGY1FQNJH1R7",
        factory="petri",
    )


def _start(*, index: int, instant: str, model: str | None) -> dict[str, object]:
    record: dict[str, object] = {
        "type": "agent.acp.started",
        "node": "implement",
        "node_visit": 1,
        "candidate_index": index,
        "occurred_at": instant,
        "primary_generation": "generation-a",
    }
    if model is not None:
        record["model"] = model
    return record


def _attrs(span: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for entry in span["attributes"]:
        value = entry["value"]
        if "arrayValue" in value:
            result[entry["key"]] = tuple(
                item["stringValue"] for item in value["arrayValue"]["values"]
            )
        else:
            result[entry["key"]] = next(iter(value.values()))
    return result


def test_terminal_span_records_succeeded_outcome_and_every_fallback_attempt() -> None:
    """The terminal span parents every attempt and preserves its observed model."""
    attempts = terminal_attempts(
        events_payload={
            "events": [
                _start(index=0, instant="2026-11-05T10:00:00Z", model="primary-model"),
                _start(index=1, instant="2026-11-05T10:00:02Z", model="fallback-model"),
            ]
        },
        terminal_at_ns=1_762_336_810_000_000_000,
    )

    payload = json.loads(
        terminal_request_line(
            correlation=_correlation(),
            outcome=_outcome(),
            attempts=attempts,
            started_at_ns=1,
            ended_at_ns=2,
        )
    )
    resource = payload["resourceSpans"][0]
    spans = resource["scopeSpans"][0]["spans"]
    terminal, primary, fallback = spans

    assert resource["resource"]["attributes"][0] == {
        "key": "service.name",
        "value": {"stringValue": "livespec-dispatcher"},
    }
    assert terminal["name"] == TERMINAL_SPAN_NAME
    assert _attrs(terminal) == {
        "work.item.id": "bd-ib-welwbc",
        "livespec.dispatch.id": "01M6NF6MZCVHJ9MGY1FQNJH1R7",
        "livespec.dispatch.factory": "petri",
        "livespec.dispatch.outcome": "succeeded",
        "livespec.dispatch.attempt_count": "2",
    }
    assert [span["name"] for span in (primary, fallback)] == [ATTEMPT_SPAN_NAME, ATTEMPT_SPAN_NAME]
    assert all(span["parentSpanId"] == terminal["spanId"] for span in (primary, fallback))
    assert _attrs(primary) == {
        "livespec.dispatch.id": "01M6NF6MZCVHJ9MGY1FQNJH1R7",
        "livespec.dispatch.attempt.index": "0",
        "livespec.dispatch.attempt.fallback": False,
        "acp.model": "primary-model",
    }
    assert _attrs(fallback) == {
        "livespec.dispatch.id": "01M6NF6MZCVHJ9MGY1FQNJH1R7",
        "livespec.dispatch.attempt.index": "1",
        "livespec.dispatch.attempt.fallback": True,
        "acp.model": "fallback-model",
    }


def test_terminal_attempts_marks_an_unobserved_model_without_fabricating_one() -> None:
    """An attempt with no confirmed model exposes that omission to the receiver."""
    attempts = terminal_attempts(
        events_payload=[_start(index=0, instant="2026-11-05T10:00:00Z", model=None)],
        terminal_at_ns=7,
    )

    payload = json.loads(
        terminal_request_line(
            correlation=_correlation(),
            outcome=_outcome(status="failed"),
            attempts=attempts,
            started_at_ns=3,
            ended_at_ns=2,
        )
    )
    attempt = payload["resourceSpans"][0]["scopeSpans"][0]["spans"][1]

    assert attempt["endTimeUnixNano"] == attempt["startTimeUnixNano"]
    assert _attrs(attempt) == {
        "livespec.dispatch.id": "01M6NF6MZCVHJ9MGY1FQNJH1R7",
        "livespec.dispatch.attempt.index": "0",
        "livespec.dispatch.attempt.fallback": False,
        "livespec.dispatch.unavailable_fields": ("acp.model",),
    }
    assert "acp.model" not in _attrs(attempt)


def test_terminal_outcomes_cover_the_closed_dispatch_vocabulary() -> None:
    """Every dispatcher disposition maps to one allowed terminal outcome."""
    cases = (
        (_outcome(), "succeeded"),
        (_outcome(status="cancelled"), "cancelled"),
        (_outcome(status="stalled-no-progress"), "cancelled"),
        (_outcome(status="run-wall-budget-exceeded"), "cancelled"),
        (_outcome(status="abandoned"), "abandoned"),
        (_outcome(status="run-unobservable"), "abandoned"),
        (_outcome(status="rework"), "rework"),
        (_outcome(status="blocked", verdict="rework"), "rework"),
        (_outcome(status="blocked", verdict="rework-pending"), "rework"),
        (_outcome(status="failed"), "failed"),
    )

    assert tuple(terminal_outcome(outcome=outcome) for outcome, _ in cases) == tuple(
        expected for _, expected in cases
    )
    assert {
        "livespec.dispatch.outcome",
        "livespec.dispatch.attempt_count",
        "livespec.dispatch.attempt.index",
        "livespec.dispatch.attempt.fallback",
        "livespec.dispatch.unavailable_fields",
        "acp.model",
    } <= ATTRIBUTE_ALLOWLIST


def test_terminal_span_is_absent_without_correlation_and_appendable_with_it(tmp_path: Path) -> None:
    """No dispatch id emits nothing; a correlated dispatch writes exactly one request."""
    path = tmp_path / "nested" / "spans.jsonl"

    emit_terminal_span(
        correlation=None,
        outcome=_outcome(),
        attempts=(),
        spans_path=path,
        started_at_ns=1,
        ended_at_ns=1,
    )
    assert not path.exists()
    assert not path.parent.exists()

    emit_terminal_span(
        correlation=_correlation(),
        outcome=_outcome(),
        attempts=(
            TerminalAttempt(
                index=0,
                fallback=False,
                started_at_ns=4,
                ended_at_ns=5,
                model="model-a",
            ),
        ),
        spans_path=path,
        started_at_ns=1,
        ended_at_ns=2,
    )

    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    assert (
        json.loads(lines[0])["resourceSpans"][0]["scopeSpans"][0]["spans"][0]["name"]
        == TERMINAL_SPAN_NAME
    )


def test_terminal_attempts_refuses_an_unreadable_event_payload() -> None:
    """An unreadable event stream invents neither attempts nor model values."""
    assert terminal_attempts(events_payload="not json", terminal_at_ns=1) is None


def test_terminal_span_names_an_unobserved_attempt_count_instead_of_reporting_zero() -> None:
    """Unobserved attempts omit the count, name it, and emit no child spans."""
    payload = json.loads(
        terminal_request_line(
            correlation=_correlation(),
            outcome=_outcome(),
            attempts=None,
            started_at_ns=1,
            ended_at_ns=2,
        )
    )
    spans = payload["resourceSpans"][0]["scopeSpans"][0]["spans"]

    assert len(spans) == 1
    attrs = _attrs(spans[0])
    assert "livespec.dispatch.attempt_count" not in attrs
    assert attrs["livespec.dispatch.unavailable_fields"] == ("livespec.dispatch.attempt_count",)


def _finish(*, monkeypatch: Any, tmp_path: Path, outcome: DispatchOutcome, emitter: Any) -> Any:
    import argparse

    from livespec_orchestrator_beads_fabro.commands import _dispatcher_loop_finish as module
    from livespec_orchestrator_beads_fabro.commands._dispatcher_dispatch_id_journal import (
        DispatchJournalIdentity,
    )
    from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile

    def dispose(**kwargs: object) -> DispatchOutcome:
        return cast("DispatchOutcome", kwargs["outcome"])

    def emit_review(**_: object) -> None:
        return None

    monkeypatch.setattr(module, "emit_terminal_span", emitter)
    return module.finish_dispatch(
        args=argparse.Namespace(),
        repo=tmp_path,
        item=_item(),
        journal=JournalFile(path=tmp_path / "journal.jsonl"),
        plan=_plan(repo=tmp_path),
        outcome=outcome,
        started_at=0.0,
        goal_text="goal",
        token_supplier=lambda: "token",
        identity=DispatchJournalIdentity(dispatch_id="dispatch-7", dispatch_factory="hp"),
        spans=tmp_path / "spans.jsonl",
        dispose=dispose,
        emit_review=emit_review,
    )


def test_finish_reports_zero_attempts_only_when_no_fabro_run_was_made(
    monkeypatch: Any, tmp_path: Path
) -> None:
    """A dispatch with no run id genuinely made no attempts, so the count is zero."""
    emitted: list[dict[str, object]] = []

    def emitter(**kwargs: object) -> None:
        emitted.append(kwargs)

    outcome = _finish_outcome(detail="done")
    no_run = DispatchOutcome(
        work_item_id=outcome.work_item_id,
        status=outcome.status,
        stage=outcome.stage,
        pr_number=outcome.pr_number,
        merge_sha=outcome.merge_sha,
        detail=outcome.detail,
        fabro_run_id=None,
    )
    _ = _finish(monkeypatch=monkeypatch, tmp_path=tmp_path, outcome=no_run, emitter=emitter)

    assert emitted[0]["attempts"] == ()


def test_finish_keeps_the_result_when_the_terminal_span_cannot_be_appended(
    monkeypatch: Any, tmp_path: Path
) -> None:
    """A local append failure never rewrites the dispatch result."""

    def emitter(**_: object) -> None:
        raise OSError("disk full")

    outcome = DispatchOutcome(
        work_item_id="bd-ib-5d5aue",
        status="green",
        stage="fabro-run",
        pr_number=None,
        merge_sha=None,
        detail="done",
        fabro_run_id=None,
    )
    result = _finish(monkeypatch=monkeypatch, tmp_path=tmp_path, outcome=outcome, emitter=emitter)

    assert result.detail == "done"
