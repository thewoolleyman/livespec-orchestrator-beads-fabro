"""Regression tests for bd-ib-nf39 dispatcher telemetry loss."""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

import pytest
from livespec_orchestrator_beads_fabro.commands import _dispatcher_otel_wiring
from livespec_orchestrator_beads_fabro.commands._dispatcher_calibration_emit import (
    emit_calibration,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    CommandResult,
    DispatchOutcome,
    FabroRunResult,
    PollPolicy,
    run_dispatch,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_fabro_failure import (
    FabroFailureDetail,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_fabro_terminal import (
    fabro_run_terminal_outcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_otel_wiring import (
    ensure_otel_enrich_driver,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import DispatchPlan
from livespec_orchestrator_beads_fabro.commands._fabro_port import FabroInspectResult
from livespec_orchestrator_beads_fabro.commands._otel_enrich_driver import OtelEnrichDriver
from livespec_orchestrator_beads_fabro.types import WorkItem


@dataclass(kw_only=True)
class _RecordingJournal:
    records: list[dict[str, object]] = field(default_factory=list)

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


@dataclass(kw_only=True)
class _FakeRunner:
    queue: list[CommandResult] = field(default_factory=list)
    calls: list[list[str]] = field(default_factory=list)

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        _ = (argv, cwd, timeout_seconds, env, stdin)
        self.calls.append(argv)
        if self.queue:
            return self.queue.pop(0)
        return CommandResult(exit_code=0, stdout="{}", stderr="")


@dataclass(frozen=True, kw_only=True)
class _FailedFabroLauncher:
    run_id: str = "01RUNFAILED"

    def launch(
        self,
        *,
        plan: DispatchPlan,
        runner: _FakeRunner,
        journal: _RecordingJournal,
    ) -> FabroRunResult:
        _ = (plan, runner, journal)
        return FabroRunResult(
            command=CommandResult(exit_code=1, stdout="", stderr="raw fabro run stderr"),
            run_id=self.run_id,
        )


def test_blocked_terminal_outcome_carries_inspected_failure_detail(tmp_path: Path) -> None:
    failure = FabroFailureDetail(
        cause="You've hit your usage limit.",
        category="deterministic",
        signature="implement|deterministic|provider limit",
        provider_usage_limit=True,
    )
    outcome = fabro_run_terminal_outcome(
        outcome_type=DispatchOutcome,
        plan=_plan(tmp_path=tmp_path),
        run_id="01RUNBLOCKED",
        inspect=FabroInspectResult(
            command=CommandResult(exit_code=0, stdout="{}", stderr=""),
            payload={},
            status_kind="blocked",
            failure=failure,
        ),
        exit_code=1,
        stderr="human gate",
    )

    assert outcome is not None
    assert outcome.status == "blocked"
    assert outcome.fabro_failure_category == "deterministic"
    assert outcome.fabro_failure_cause == "You've hit your usage limit."
    assert outcome.fabro_failure_signature == "implement|deterministic|provider limit"


def test_failed_dispatch_reinspects_when_terminal_inspect_has_no_failure_yet(
    tmp_path: Path,
) -> None:
    runner = _FakeRunner(
        queue=[
            CommandResult(
                exit_code=0,
                stdout=json.dumps([{"status": {"kind": "failed"}}]),
                stderr="",
            ),
            CommandResult(
                exit_code=0,
                stdout=json.dumps(
                    [
                        {
                            "status": {"kind": "failed"},
                            "failure": {
                                "causes": [
                                    "ACP protocol error",
                                    "You've hit your usage limit.",
                                ],
                                "category": "transient_infra",
                                "signature": "implement|transient_infra|provider limit",
                            },
                        }
                    ]
                ),
                stderr="",
            ),
        ]
    )
    journal = _RecordingJournal()
    outcome = run_dispatch(
        plan=_plan(tmp_path=tmp_path),
        runner=runner,
        journal=journal,
        sleep=lambda _seconds: None,
        poll=PollPolicy(attempts=1, interval_seconds=0.0),
        fabro_launcher=_FailedFabroLauncher(),
    )

    assert outcome.status == "failed"
    assert outcome.stage == "fabro-run"
    assert outcome.fabro_failure_category == "deterministic"
    assert outcome.fabro_failure_cause == "You've hit your usage limit."
    assert outcome.fabro_failure_signature == "implement|deterministic|provider limit"
    # `fabro-run-labels` closes the sequence because this failure IS a provider
    # ceiling, and the entitlement it spent is recorded on the factory's run row
    # rather than in the inspect payload. The read is taken once, after the
    # re-inspection that finally produced a failure block — so its position here
    # is also what says the re-inspection ran first.
    assert [record["stage"] for record in journal.records] == [
        "fabro-run",
        "fabro-inspect",
        "fabro-reattach",
        "fabro-inspect",
        "fabro-run-labels",
    ]


def test_failed_terminal_outcome_carries_category_when_failure_has_no_cause(
    tmp_path: Path,
) -> None:
    failure = FabroFailureDetail(
        cause=None,
        category="transient_infra",
        signature="implement|transient_infra|script failed",
    )
    outcome = fabro_run_terminal_outcome(
        outcome_type=DispatchOutcome,
        plan=_plan(tmp_path=tmp_path),
        run_id="01RUNFAILED",
        inspect=FabroInspectResult(
            command=CommandResult(exit_code=0, stdout="{}", stderr=""),
            payload={},
            status_kind="failed",
            failure=failure,
        ),
        exit_code=1,
        stderr="raw fabro run stderr",
    )

    assert outcome is not None
    assert outcome.status == "failed"
    assert (
        outcome.detail
        == "category=transient_infra; signature=implement|transient_infra|script failed"
    )
    assert outcome.fabro_failure_category == "transient_infra"
    assert outcome.fabro_failure_cause is None
    assert outcome.fabro_failure_signature == "implement|transient_infra|script failed"


def test_emit_calibration_appends_honeycomb_span_with_failure_fields(tmp_path: Path) -> None:
    journal_file = tmp_path / "journal.jsonl"
    emit_calibration(
        args=argparse.Namespace(journal=str(journal_file)),
        repo=tmp_path,
        item=_item(),
        outcome=_outcome(
            status="failed",
            fabro_failure_cause="provider quota exhausted",
            fabro_failure_category="deterministic",
            fabro_failure_signature="implement|deterministic|provider quota exhausted",
        ),
        journal=_RecordingJournal(),
        wall_clock_seconds=7.0,
        dispatch_context_size=321,
        runner=_FakeRunner(),
    )

    spans_file = tmp_path / "journal-calibration-spans.jsonl"
    request = json.loads(spans_file.read_text(encoding="utf-8"))
    span = request["resourceSpans"][0]["scopeSpans"][0]["spans"][0]
    attrs = _attrs(span=span)
    assert span["name"] == "dispatcher.calibration"
    assert attrs["work.item.id"] == "bd-ib-nf39"
    assert attrs["converged"] is False
    assert attrs["outcome_class"] == "failed:fabro-run"
    assert attrs["fabro.failure.cause"] == "provider quota exhausted"
    assert attrs["fabro.failure.category"] == "deterministic"
    assert attrs["fabro.failure.signature"] == "implement|deterministic|provider quota exhausted"


def test_otel_driver_tails_calibration_spans_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _without_starting(*, holder: dict[str, object], factory: Callable[[], object]) -> object:
        _ = holder
        return factory()

    monkeypatch.setattr(_dispatcher_otel_wiring, "ensure_receiver_started", _without_starting)
    driver = ensure_otel_enrich_driver(
        args=argparse.Namespace(repo=str(tmp_path), journal=str(tmp_path / "j.jsonl")),
        repo=tmp_path,
        holder={},
    )
    assert isinstance(driver, OtelEnrichDriver)
    assert tmp_path / "j-calibration-spans.jsonl" in {stage.spans_path for stage in driver.stages}


def _item() -> WorkItem:
    return WorkItem(
        id="bd-ib-nf39",
        type="bug",
        status="active",
        title="Capture fabro failure telemetry",
        description="A failed dispatch should explain why.",
        origin="freeform",
        gap_id=None,
        rank="a2",
        assignee=None,
        depends_on=(),
        captured_at="2026-08-22T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
    )


def _outcome(
    *,
    status: str,
    fabro_failure_cause: str,
    fabro_failure_category: str,
    fabro_failure_signature: str,
) -> DispatchOutcome:
    return DispatchOutcome(
        work_item_id="bd-ib-nf39",
        status=status,
        stage="fabro-run",
        pr_number=None,
        merge_sha=None,
        detail="failed",
        fabro_failure_cause=fabro_failure_cause,
        fabro_failure_category=fabro_failure_category,
        fabro_failure_signature=fabro_failure_signature,
    )


def _plan(*, tmp_path: Path) -> DispatchPlan:
    return DispatchPlan(
        repo=tmp_path,
        work_item_id="bd-ib-nf39",
        branch="feat/bd-ib-nf39",
        workflow_toml=tmp_path / "workflow.toml",
        goal_file=tmp_path / "goal.txt",
        fabro_bin="fabro",
        fabro_factory_name="hp",
        fabro_factory_server=None,
        fabro_factory_dev_token=None,
        janitor=("just", "check"),
        janitor_checkout=tmp_path / ".janitor",
        janitor_core_checkout=tmp_path / ".janitor" / ".livespec-core",
        janitor_core_repo_url="https://github.com/thewoolleyman/livespec.git",
        janitor_core_ref="master",
        review_fix_visit_cap=3,
        merge_on_review_cap_outcome="succeeded",
    )


def _attrs(*, span: dict[str, object]) -> dict[str, object]:
    attrs: dict[str, object] = {}
    for raw_attr in span["attributes"]:
        attr = cast("dict[str, object]", raw_attr)
        value = cast("dict[str, object]", attr["value"])
        attrs[str(attr["key"])] = next(iter(value.values()))
    return attrs
