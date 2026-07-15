"""Tests for review-gate telemetry derived from Fabro events."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import DispatchPlan, build_plan
from livespec_orchestrator_beads_fabro.commands._dispatcher_review_gate import (
    ReviewGateEmission,
    ReviewGateTelemetry,
    emit_review_gate_from_fabro_events,
    emit_review_gate_span,
    parse_review_gate_events,
    review_gate_request_line,
)


def test_parse_review_gate_events_approved_on_first_visit() -> None:
    events = _jsonl(
        _stage(node_id="review", timestamp="2026-07-15T00:00:01Z"),
        _edge(
            from_node="review",
            to_node="pr",
            reason="preferred_label",
            preferred_label="approve",
            timestamp="2026-07-15T00:00:02Z",
        ),
    )

    telemetry = parse_review_gate_events(events_jsonl=events)

    assert telemetry == ReviewGateTelemetry(
        verdict="approve",
        fix_rounds=0,
        hit_cap=False,
        shipped_on_cap=False,
    )


def test_parse_review_gate_events_counts_fix_rounds_and_ship_on_cap_order_robust() -> None:
    # Intentionally out of stream order; timestamps decide the terminal review edge.
    events = _jsonl(
        _edge(
            from_node="review",
            to_node="pr",
            reason="unconditional",
            preferred_label=None,
            timestamp="2026-07-15T00:03:00Z",
        ),
        _edge(
            from_node="review",
            to_node="review_fix",
            reason="preferred_label",
            preferred_label="fix",
            timestamp="2026-07-15T00:01:00Z",
        ),
        _edge(
            from_node="review",
            to_node="review_fix",
            reason="preferred_label",
            preferred_label="fix",
            timestamp="2026-07-15T00:02:00Z",
        ),
        _edge(
            from_node="implement",
            to_node="review",
            reason="unconditional",
            preferred_label=None,
            timestamp="2026-07-15T00:00:30Z",
        ),
        {"event": "not-json-review"},
    )

    telemetry = parse_review_gate_events(events_jsonl=events)

    assert telemetry == ReviewGateTelemetry(
        verdict="unknown",
        fix_rounds=2,
        hit_cap=True,
        shipped_on_cap=True,
    )


def test_parse_review_gate_events_distinguishes_malformed_early_ship_from_cap() -> None:
    events = _jsonl(
        _edge(
            from_node="review",
            to_node="pr",
            reason="unconditional",
            preferred_label=None,
            timestamp="2026-07-15T00:01:00Z",
        )
    )

    telemetry = parse_review_gate_events(events_jsonl=events)

    assert telemetry == ReviewGateTelemetry(
        verdict="unknown",
        fix_rounds=0,
        hit_cap=False,
        shipped_on_cap=False,
    )


def test_parse_review_gate_events_ignores_malformed_lines_and_edges() -> None:
    events = "\n".join(
        (
            "",
            "not json",
            json.dumps(["not", "an", "object"]),
            json.dumps({"event": 5}),
            json.dumps({"event": "edge.selected", "properties": {"from_node": "review"}}),
            json.dumps(
                {
                    "event": "edge.selected",
                    "properties": {
                        "from_node": "review",
                        "to_node": 7,
                        "reason": "preferred_label",
                    },
                }
            ),
        )
    )

    telemetry = parse_review_gate_events(events_jsonl=events)

    assert telemetry == ReviewGateTelemetry(
        verdict="unknown",
        fix_rounds=0,
        hit_cap=False,
        shipped_on_cap=False,
    )


def test_parse_review_gate_events_accepts_observed_name_variants_and_timestamp_shapes() -> None:
    events = _jsonl(
        {
            "event": 5,
            "name": "edge.selected",
            "ts": "not-a-date",
            "from_node": "review",
            "to_node": "review_fix",
            "reason": "preferred_label",
            "preferred_label": "fix",
        },
        {
            "event_name": "edge.selected",
            "ts": 3,
            "properties": {
                "from_node": "review",
                "to_node": "review_fix",
                "reason": "preferred_label",
                "preferred_label": "fix",
            },
        },
        {
            "type": "edge.selected",
            "at": "2026-07-15T00:03:00",
            "properties": {
                "from_node": "review",
                "to_node": "pr",
                "reason": "unconditional",
            },
        },
    )

    telemetry = parse_review_gate_events(events_jsonl=events)

    assert telemetry == ReviewGateTelemetry(
        verdict="unknown",
        fix_rounds=2,
        hit_cap=True,
        shipped_on_cap=True,
    )


def test_review_gate_request_line_uses_dispatcher_service_and_typed_attributes() -> None:
    line = review_gate_request_line(
        telemetry=ReviewGateTelemetry(
            verdict="fix",
            fix_rounds=1,
            hit_cap=False,
            shipped_on_cap=False,
        ),
        work_item_id="bd-1",
        dispatch_id="dispatch-1",
        run_id="run-1",
        now_ns=123,
    )

    request = json.loads(line)
    resource = request["resourceSpans"][0]
    resource_attrs = _attrs(resource["resource"]["attributes"])
    span = resource["scopeSpans"][0]["spans"][0]
    attrs = _attrs(span["attributes"])
    assert _attrs([{"key": "dropped", "value": {}}]) == {}

    assert resource_attrs["service.name"] == "livespec-dispatcher"
    assert span["name"] == "review.gate"
    assert attrs["review.verdict"] == "fix"
    assert attrs["review.fix_rounds"] == "1"
    assert attrs["review.hit_cap"] is False
    assert attrs["pr.shipped_on_cap"] is False
    assert attrs["work.item.id"] == "bd-1"
    assert attrs["livespec.dispatch.id"] == "dispatch-1"
    assert attrs["fabro.run_id"] == "run-1"


def test_emit_review_gate_span_appends_one_jsonl_request(tmp_path: Path) -> None:
    spans_path = tmp_path / "spans.jsonl"

    emit_review_gate_span(
        telemetry=ReviewGateTelemetry(
            verdict="approve",
            fix_rounds=0,
            hit_cap=False,
            shipped_on_cap=False,
        ),
        spans_path=spans_path,
        work_item_id="bd-1",
        dispatch_id="dispatch-1",
        run_id="run-1",
        now_ns=123,
    )

    assert len(spans_path.read_text(encoding="utf-8").splitlines()) == 1


def test_emit_review_gate_from_fabro_events_queries_and_journals(tmp_path: Path) -> None:
    plan = _plan(repo=tmp_path)
    runner = _FakeRunner(
        queue=[
            CommandResult(
                exit_code=0,
                stdout=_jsonl(
                    _edge(
                        from_node="review",
                        to_node="pr",
                        reason="preferred_label",
                        preferred_label="approve",
                        timestamp="2026-07-15T00:00:02Z",
                    )
                ),
                stderr="",
            )
        ]
    )
    journal = _Journal()
    spans_path = tmp_path / "review-spans.jsonl"

    emit_review_gate_from_fabro_events(
        emission=ReviewGateEmission(
            plan=plan,
            runner=runner,
            journal=journal,
            spans_path=spans_path,
            work_item_id="bd-1",
            dispatch_id="dispatch-1",
            run_id="run-1",
        )
    )

    assert runner.calls == [(["fabro", "events", "run-1", "--json"], tmp_path)]
    assert json.loads(spans_path.read_text(encoding="utf-8"))["resourceSpans"]
    assert journal.records[-1]["stage"] == "review-gate-telemetry"
    assert journal.records[-1]["review_verdict"] == "approve"


def test_emit_review_gate_from_fabro_events_skips_without_run_id(tmp_path: Path) -> None:
    runner = _FakeRunner(queue=[])
    journal = _Journal()

    emit_review_gate_from_fabro_events(
        emission=ReviewGateEmission(
            plan=_plan(repo=tmp_path),
            runner=runner,
            journal=journal,
            spans_path=tmp_path / "review-spans.jsonl",
            work_item_id="bd-1",
            dispatch_id="dispatch-1",
            run_id=None,
        )
    )

    assert runner.calls == []
    assert journal.records == []


def test_emit_review_gate_from_fabro_events_skips_on_command_failure(tmp_path: Path) -> None:
    runner = _FakeRunner(queue=[CommandResult(exit_code=1, stdout="", stderr="boom")])
    journal = _Journal()
    spans_path = tmp_path / "review-spans.jsonl"

    emit_review_gate_from_fabro_events(
        emission=ReviewGateEmission(
            plan=_plan(repo=tmp_path),
            runner=runner,
            journal=journal,
            spans_path=spans_path,
            work_item_id="bd-1",
            dispatch_id="dispatch-1",
            run_id="run-1",
        )
    )

    assert not spans_path.exists()
    assert journal.records[-1]["reason"] == "fabro events command failed"
    assert journal.records[-1]["exit_code"] == 1


def _jsonl(*events: dict[str, object]) -> str:
    return "\n".join(json.dumps(event) for event in events)


def _edge(
    *,
    from_node: str,
    to_node: str,
    reason: str,
    preferred_label: str | None,
    timestamp: str,
) -> dict[str, object]:
    properties: dict[str, object] = {
        "from_node": from_node,
        "to_node": to_node,
        "reason": reason,
        "label": preferred_label or "",
    }
    if preferred_label is not None:
        properties["preferred_label"] = preferred_label
    return {"event": "edge.selected", "timestamp": timestamp, "properties": properties}


def _stage(*, node_id: str, timestamp: str) -> dict[str, object]:
    return {
        "event": "stage.completed",
        "timestamp": timestamp,
        "node_id": node_id,
        "node_label": node_id,
        "properties": {"attempt": 1, "index": 0, "max_attempts": 1, "status": "ok"},
    }


def _attrs(entries: object) -> dict[str, object]:
    attrs: dict[str, object] = {}
    for entry in cast("list[dict[str, object]]", entries):
        value = cast("dict[str, object]", entry["value"])
        if "stringValue" in value:
            attrs[str(entry["key"])] = value["stringValue"]
        elif "intValue" in value:
            attrs[str(entry["key"])] = value["intValue"]
        elif "boolValue" in value:
            attrs[str(entry["key"])] = value["boolValue"]
    return attrs


def _plan(*, repo: Path) -> DispatchPlan:
    return build_plan(
        repo=repo,
        work_item_id="bd-1",
        workflow_toml=repo / "workflow.toml",
        goal_file=repo / "goal.md",
        fabro_bin="fabro",
        janitor=None,
        janitor_checkout=repo / "janitor",
    )


@dataclass(kw_only=True)
class _FakeRunner:
    queue: list[CommandResult]
    calls: list[tuple[list[str], Path]] = field(default_factory=list)

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
    ) -> CommandResult:
        assert timeout_seconds > 0
        assert env is None
        self.calls.append((argv, cwd))
        return self.queue.pop(0)


@dataclass(kw_only=True)
class _Journal:
    records: list[dict[str, object]] = field(default_factory=list)

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)
