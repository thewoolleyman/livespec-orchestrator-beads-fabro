"""Tests for the Dispatcher's per-dispatch calibration telemetry (yfsv4j).

Covers the pure `_dispatcher_calibration` derivation module (the outcome
SIGNAL + mechanical SIZE PROXIES the spec enumerates) and its wiring into
`dispatcher._dispatch_one` via `_emit_calibration`. The load-bearing
contract under test (livespec-impl-beads SPECIFICATION/contracts.md
§"Dispatcher grooming behavior" / §"Calibration telemetry and the single
Fabro tweak"): the Dispatcher MUST emit calibration telemetry — an
outcome signal plus mechanical size proxies — recorded on the EXISTING
journal so it rides the journal → Honeycomb leg, with NO new always-on
service. The wiring stage is FAIL-OPEN: a probe error never crashes the
already-final verdict.

Hermetic: the pure builder is exercised directly; the wiring is driven
with an injected recording journal, an injected `_FakeRunner` for the
merged-PR diff-size probe, and a real `CostSink` seeded via a synthetic
cost span. No real fabro run, gh call, CC session, or Honeycomb egress.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field, replace
from pathlib import Path

from livespec_impl_beads.commands._dispatcher_calibration import (
    CalibrationRecord,
    acceptance_count,
    bounced_to_regroom,
    build_calibration_record,
    calibration_journal_record,
    fix_loop_count,
    outcome_class,
    spec_surface_touched,
)
from livespec_impl_beads.commands._dispatcher_cost_sink import CostSink
from livespec_impl_beads.commands._dispatcher_engine import CommandResult, DispatchOutcome
from livespec_impl_beads.commands.dispatcher import (
    _calibration_token_cost,  # pyright: ignore[reportPrivateUsage]
    _cost_sink_path,  # pyright: ignore[reportPrivateUsage]
    _emit_calibration,  # pyright: ignore[reportPrivateUsage]
    _merged_pr_diff_size,  # pyright: ignore[reportPrivateUsage]
    _parse_pr_diff_size,  # pyright: ignore[reportPrivateUsage]
    _read_journal_records_for,  # pyright: ignore[reportPrivateUsage]
)
from livespec_impl_beads.types import WorkItem


@dataclass(kw_only=True)
class _RecordingJournal:
    records: list[dict[str, object]] = field(default_factory=list)

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


@dataclass(kw_only=True)
class _FakeRunner:
    """Scripted CommandRunner: returns the queued result, logs the argv."""

    stdout: str = ""
    exit_code: int = 0
    calls: list[list[str]] = field(default_factory=list)

    def run(self, *, argv: list[str], cwd: Path, timeout_seconds: float) -> CommandResult:
        assert timeout_seconds > 0
        assert isinstance(cwd, Path)
        self.calls.append(argv)
        return CommandResult(exit_code=self.exit_code, stdout=self.stdout, stderr="")


@dataclass(kw_only=True)
class _RaisingRunner:
    """A runner whose probe raises — drives the fail-open supervisor branch."""

    def run(self, *, argv: list[str], cwd: Path, timeout_seconds: float) -> CommandResult:
        _ = (argv, cwd, timeout_seconds)
        raise RuntimeError("probe blew up")


def _item(**overrides: object) -> WorkItem:
    base = WorkItem(
        id="livespec-impl-beads-c1",
        type="feature",
        status="open",
        title="A calibration item",
        description="Do the thing.",
        origin="freeform",
        gap_id=None,
        priority=2,
        assignee=None,
        depends_on=(),
        captured_at="2026-06-11T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
    )
    return replace(base, **overrides)


def _outcome(
    *,
    work_item_id: str = "livespec-impl-beads-c1",
    status: str = "green",
    stage: str = "done",
    pr_number: int | None = 7,
    merge_sha: str | None = "abc123",
    detail: str = "merged, post-merge janitor green",
) -> DispatchOutcome:
    return DispatchOutcome(
        work_item_id=work_item_id,
        status=status,
        stage=stage,
        pr_number=pr_number,
        merge_sha=merge_sha,
        detail=detail,
    )


def _args(*, journal: Path) -> argparse.Namespace:
    return argparse.Namespace(journal=str(journal))


def _cost_span(*, work_item_id: str, input_tokens: int) -> dict[str, object]:
    """A synthetic CC cost-bearing span keyed by `work.item.id`."""
    return {
        "name": "claude_code.llm_request",
        "attributes": [
            {"key": "work.item.id", "value": {"stringValue": work_item_id}},
            {"key": "request_id", "value": {"stringValue": "req-1"}},
            {"key": "model", "value": {"stringValue": "claude-opus-4-8"}},
            {"key": "input_tokens", "value": {"intValue": str(input_tokens)}},
            {"key": "output_tokens", "value": {"intValue": "0"}},
        ],
    }


# --- the pure builder: the full field set (spec list, one-to-one) --------


def test_build_calibration_record_populates_every_spec_field() -> None:
    """The record carries the spec's full outcome-signal + size-proxy field set."""
    item = _item(
        type="bug",
        gap_id="G-1",
        depends_on=("d1", "d2", "d3"),
        description="- one\n- two\nScenario: foo\nGiven a thing",
    )
    record = build_calibration_record(
        item=item,
        outcome=_outcome(),
        repo_name="livespec-impl-beads",
        journal_records=(
            {"work_item_id": item.id, "stage": "pr-view"},
            {"work_item_id": item.id, "stage": "pr-view"},
            {"work_item_id": item.id, "stage": "pr-update-branch"},
        ),
        wall_clock_seconds=12.5,
        token_cost_micros=4200,
        dispatch_context_size=900,
        merged_pr_diff_size=145,
    )
    # outcome signal
    assert record.converged is True
    assert record.fix_loop_count == 2
    assert record.outcome_class == "green"
    assert record.wall_clock_seconds == 12.5
    assert record.token_cost_micros == 4200
    assert record.bounced_to_regroom is False
    # mechanical size proxies
    assert record.acceptance_count == 4
    assert record.merged_pr_diff_size == 145
    assert record.dependency_fan_out == 3
    assert record.spec_surface_touched is True
    assert record.dispatch_context_size == 900
    assert record.archetype == "bug"
    assert record.repo == "livespec-impl-beads"
    assert record.work_item_id == item.id


def test_build_calibration_record_unobservable_proxies_are_none() -> None:
    """Unobservable cost / diff size record as None, never a false zero."""
    record = build_calibration_record(
        item=_item(),
        outcome=_outcome(status="failed", stage="fabro-run", pr_number=None, merge_sha=None),
        repo_name="repo",
        journal_records=(),
        wall_clock_seconds=None,
        token_cost_micros=None,
        dispatch_context_size=10,
        merged_pr_diff_size=None,
    )
    assert record.converged is False
    assert record.wall_clock_seconds is None
    assert record.token_cost_micros is None
    assert record.merged_pr_diff_size is None
    assert record.fix_loop_count == 0
    assert record.acceptance_count == 0
    assert record.spec_surface_touched is False


def test_outcome_class_green_collapses_to_status() -> None:
    assert outcome_class(outcome=_outcome(status="green", stage="done")) == "green"


def test_outcome_class_non_green_carries_stage() -> None:
    failed = _outcome(status="failed", stage="janitor-post-merge")
    assert outcome_class(outcome=failed) == "failed:janitor-post-merge"


def test_bounced_to_regroom_only_on_stalled_non_convergence() -> None:
    stalled = _outcome(status="stalled-no-progress", stage="fabro-run")
    assert bounced_to_regroom(outcome=stalled) is True
    assert bounced_to_regroom(outcome=_outcome(status="green")) is False
    assert bounced_to_regroom(outcome=_outcome(status="failed", stage="fabro-run")) is False


def test_fix_loop_count_counts_extra_views_and_update_branches() -> None:
    """One extra pr-view beyond baseline + each pr-update-branch is one loop."""
    records = (
        {"work_item_id": "a", "stage": "pr-view"},
        {"work_item_id": "a", "stage": "pr-view"},
        {"work_item_id": "a", "stage": "pr-update-branch"},
        {"work_item_id": "b", "stage": "pr-view"},  # other item, ignored
        {"work_item_id": "a", "stage": "fabro-run"},  # unrelated stage, ignored
    )
    assert fix_loop_count(records=records, work_item_id="a") == 2


def test_fix_loop_count_clean_single_pass_is_zero() -> None:
    records = ({"work_item_id": "a", "stage": "pr-view"},)
    assert fix_loop_count(records=records, work_item_id="a") == 0


def test_acceptance_count_sums_bullets_and_gherkin() -> None:
    item = _item(description="- a\n* b\nScenario: x\nGiven y\nWhen z\nThen w\nplain prose")
    # two bullets + four gherkin markers
    assert acceptance_count(item=item) == 6


def test_acceptance_count_bare_prose_is_zero() -> None:
    assert acceptance_count(item=_item(description="Just a sentence with no structure.")) == 0


def test_spec_surface_touched_true_for_gap_tied() -> None:
    assert spec_surface_touched(item=_item(origin="gap-tied", gap_id="G-9")) is True


def test_spec_surface_touched_true_for_spec_commitment_hint() -> None:
    assert spec_surface_touched(item=_item(spec_commitment_hint="commitment-1")) is True


def test_spec_surface_touched_false_for_freeform() -> None:
    assert spec_surface_touched(item=_item(gap_id=None, spec_commitment_hint=None)) is False


def test_calibration_journal_record_flattens_every_field() -> None:
    """The journal record names stage `calibration` and rides every field flat."""
    record = CalibrationRecord(
        work_item_id="w-1",
        converged=True,
        fix_loop_count=1,
        outcome_class="green",
        wall_clock_seconds=3.0,
        token_cost_micros=99,
        bounced_to_regroom=False,
        acceptance_count=2,
        merged_pr_diff_size=50,
        dependency_fan_out=1,
        spec_surface_touched=True,
        dispatch_context_size=40,
        archetype="task",
        repo="repo",
    )
    journal = calibration_journal_record(record=record)
    assert journal["stage"] == "calibration"
    assert journal["work_item_id"] == "w-1"
    assert journal["converged"] is True
    assert journal["fix_loop_count"] == 1
    assert journal["outcome_class"] == "green"
    assert journal["wall_clock_seconds"] == 3.0
    assert journal["token_cost_micros"] == 99
    assert journal["bounced_to_regroom"] is False
    assert journal["acceptance_count"] == 2
    assert journal["merged_pr_diff_size"] == 50
    assert journal["dependency_fan_out"] == 1
    assert journal["spec_surface_touched"] is True
    assert journal["dispatch_context_size"] == 40
    assert journal["archetype"] == "task"
    assert journal["repo"] == "repo"


# --- the diff-size probe parse ------------------------------------------


def test_parse_pr_diff_size_sums_additions_and_deletions() -> None:
    assert _parse_pr_diff_size(stdout='{"additions": 120, "deletions": 25}') == 145


def test_parse_pr_diff_size_unparseable_is_none() -> None:
    assert _parse_pr_diff_size(stdout="not json") is None


def test_parse_pr_diff_size_non_object_is_none() -> None:
    assert _parse_pr_diff_size(stdout="[1, 2, 3]") is None


def test_parse_pr_diff_size_missing_fields_is_none() -> None:
    assert _parse_pr_diff_size(stdout='{"additions": 12}') is None


def test_merged_pr_diff_size_reads_green_pr(tmp_path: Path) -> None:
    runner = _FakeRunner(stdout='{"additions": 30, "deletions": 12}')
    size = _merged_pr_diff_size(repo=tmp_path, outcome=_outcome(), runner=runner)
    assert size == 42
    assert runner.calls[0][:3] == ["gh", "pr", "view"]


def test_merged_pr_diff_size_non_green_is_none(tmp_path: Path) -> None:
    runner = _FakeRunner()
    failed = _outcome(status="failed", stage="fabro-run", pr_number=None)
    assert _merged_pr_diff_size(repo=tmp_path, outcome=failed, runner=runner) is None
    assert runner.calls == []  # no probe for a non-green outcome


def test_merged_pr_diff_size_green_without_pr_is_none(tmp_path: Path) -> None:
    runner = _FakeRunner()
    assert (
        _merged_pr_diff_size(repo=tmp_path, outcome=_outcome(pr_number=None), runner=runner) is None
    )
    assert runner.calls == []


def test_merged_pr_diff_size_gh_failure_is_none(tmp_path: Path) -> None:
    runner = _FakeRunner(exit_code=1)
    assert _merged_pr_diff_size(repo=tmp_path, outcome=_outcome(), runner=runner) is None


# --- the journal read-back ----------------------------------------------


def test_read_journal_records_for_parses_and_skips_garbage(tmp_path: Path) -> None:
    journal = tmp_path / "journal.jsonl"
    # A valid record, an undecodable line (skipped at the JSONDecodeError),
    # a valid-JSON-but-non-dict line (skipped at the isinstance guard), and
    # a second valid record — only the two dict records survive.
    _ = journal.write_text(
        '{"work_item_id": "a", "stage": "pr-view"}\nnot-json\n[1, 2, 3]\n{"stage": "outcome"}\n',
        encoding="utf-8",
    )
    records = _read_journal_records_for(args=_args(journal=journal), repo=tmp_path)
    assert len(records) == 2
    assert records[0]["stage"] == "pr-view"


def test_read_journal_records_for_missing_file_is_empty(tmp_path: Path) -> None:
    records = _read_journal_records_for(
        args=_args(journal=tmp_path / "absent.jsonl"), repo=tmp_path
    )
    assert records == ()


# --- the derived token cost ---------------------------------------------


def test_calibration_token_cost_reads_seeded_sink(tmp_path: Path) -> None:
    journal = tmp_path / "journal.jsonl"
    args = _args(journal=journal)
    sink = CostSink(path=_cost_sink_path(args=args, repo=tmp_path))
    sink.accumulate_span(span=_cost_span(work_item_id="livespec-impl-beads-c1", input_tokens=1000))
    cost = _calibration_token_cost(args=args, repo=tmp_path, outcome=_outcome())
    assert cost is not None
    assert cost > 0


def test_calibration_token_cost_unobservable_is_none(tmp_path: Path) -> None:
    cost = _calibration_token_cost(
        args=_args(journal=tmp_path / "journal.jsonl"),
        repo=tmp_path,
        outcome=_outcome(),
    )
    assert cost is None


# --- the fail-open wiring stage -----------------------------------------


def test_emit_calibration_appends_one_calibration_record(tmp_path: Path) -> None:
    """The happy path journals exactly one flat `calibration` record."""
    journal_file = tmp_path / "journal.jsonl"
    recording = _RecordingJournal()
    runner = _FakeRunner(stdout='{"additions": 10, "deletions": 5}')
    _emit_calibration(
        args=_args(journal=journal_file),
        repo=tmp_path,
        item=_item(),
        outcome=_outcome(),
        journal=recording,
        wall_clock_seconds=7.0,
        dispatch_context_size=321,
        runner=runner,
    )
    calibration = [r for r in recording.records if r.get("stage") == "calibration"]
    assert len(calibration) == 1
    record = calibration[0]
    assert record["converged"] is True
    assert record["merged_pr_diff_size"] == 15
    assert record["dispatch_context_size"] == 321
    assert record["wall_clock_seconds"] == 7.0
    assert record["repo"] == tmp_path.name


def test_emit_calibration_failed_outcome_skips_diff_probe(tmp_path: Path) -> None:
    """A failed outcome records None diff size and never probes gh."""
    recording = _RecordingJournal()
    runner = _FakeRunner()
    _emit_calibration(
        args=_args(journal=tmp_path / "journal.jsonl"),
        repo=tmp_path,
        item=_item(),
        outcome=_outcome(status="failed", stage="fabro-run", pr_number=None, merge_sha=None),
        journal=recording,
        wall_clock_seconds=2.0,
        dispatch_context_size=10,
        runner=runner,
    )
    record = next(r for r in recording.records if r.get("stage") == "calibration")
    assert record["converged"] is False
    assert record["merged_pr_diff_size"] is None
    assert record["outcome_class"] == "failed:fabro-run"
    assert runner.calls == []


def test_emit_calibration_is_fail_open_on_probe_error(tmp_path: Path) -> None:
    """A raising probe is journaled as calibration-error, never propagated."""
    recording = _RecordingJournal()
    _emit_calibration(
        args=_args(journal=tmp_path / "journal.jsonl"),
        repo=tmp_path,
        item=_item(),
        outcome=_outcome(),
        journal=recording,
        wall_clock_seconds=1.0,
        dispatch_context_size=5,
        runner=_RaisingRunner(),
    )
    errors = [r for r in recording.records if r.get("stage") == "calibration-error"]
    assert len(errors) == 1
    assert errors[0]["reason"] == "RuntimeError"
    assert errors[0]["work_item_id"] == "livespec-impl-beads-c1"
    # No calibration record was journaled — the build never completed.
    assert not any(r.get("stage") == "calibration" for r in recording.records)


def test_emit_calibration_reads_fix_loops_from_flushed_journal(tmp_path: Path) -> None:
    """The fix-loop count derives from the on-disk journal the engine flushed."""
    journal_file = tmp_path / "journal.jsonl"
    _ = journal_file.write_text(
        json.dumps({"work_item_id": "livespec-impl-beads-c1", "stage": "pr-view"})
        + "\n"
        + json.dumps({"work_item_id": "livespec-impl-beads-c1", "stage": "pr-view"})
        + "\n"
        + json.dumps({"work_item_id": "livespec-impl-beads-c1", "stage": "pr-update-branch"})
        + "\n",
        encoding="utf-8",
    )
    recording = _RecordingJournal()
    _emit_calibration(
        args=_args(journal=journal_file),
        repo=tmp_path,
        item=_item(),
        outcome=_outcome(),
        journal=recording,
        wall_clock_seconds=1.0,
        dispatch_context_size=5,
        runner=_FakeRunner(stdout='{"additions": 1, "deletions": 1}'),
    )
    record = next(r for r in recording.records if r.get("stage") == "calibration")
    assert record["fix_loop_count"] == 2
