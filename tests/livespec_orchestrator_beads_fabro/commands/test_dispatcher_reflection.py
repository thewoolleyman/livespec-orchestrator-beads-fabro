"""Tests for the mechanical, fail-open loop-exit reflection stage.

Covers `_dispatcher_reflection` (the NO-LLM scan/emit module) and its
wiring into `dispatcher._run_loop_command` / `_run_dispatch_command`. The
load-bearing invariant under test (loop-reflection-gate best-practices
§6): reflection NEVER changes a dispatch verdict and NEVER blocks loop
exit — the exit code is computed before `reflect` runs and is immutable
by it. The `LIVESPEC_REFLECTION` lever (off / observe / file), the ~60s
time-box, the consecutive-error auto-trip, and the OTLP span emission
(with credential hygiene) are each exercised directly.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import pytest
from livespec_orchestrator_beads_fabro.commands import _dispatcher_reflection as reflection
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_reflection_journal import (
    read_journal_records,
)

# The scrub + attribute discipline lives in the SHARED `_otel_scrub` module
# (29f E1 single source of truth); the reflection emitter consumes it. The
# credential-hygiene tests below address it through its real home (see also
# test_otel_scrub.py for the module's own direct + property-based suite).
from livespec_orchestrator_beads_fabro.commands._otel_scrub import (
    ATTR_MAX_LEN as _ATTR_MAX_LEN,
)
from livespec_orchestrator_beads_fabro.commands._otel_scrub import (
    attr as _attr,
)
from livespec_orchestrator_beads_fabro.commands._otel_scrub import (
    scrub as _scrub,
)


@pytest.fixture(autouse=True)
def reset_auto_trip_fixture() -> None:
    """Every test starts from a clean process-level auto-trip state."""
    reflection.reset_auto_trip()


def _outcome(
    *,
    work_item_id: str = "a-1",
    status: str = "green",
    stage: str = "done",
    pr_number: int | None = 7,
    merge_sha: str | None = "deadbeef",
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


def _journal_records(*, journal_path: Path) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for line in journal_path.read_text(encoding="utf-8").splitlines():
        try:
            parsed: object = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            mapping = cast("dict[object, object]", parsed)
            records.append({str(key): value for key, value in mapping.items()})
    return records


def _stages(*, journal_path: Path) -> list[object]:
    return [rec.get("stage") for rec in _journal_records(journal_path=journal_path)]


def _records(*entries: dict[str, object]) -> tuple[dict[str, object], ...]:
    """Build a journal-records tuple with the `dict[str, object]` element
    type `scan_outcomes` expects (literal dicts otherwise narrow to
    `dict[str, str | int]`, which pyright rejects at the call boundary)."""
    return entries


def _record_finding_categories(*, record: dict[str, object]) -> list[str]:
    """Extract finding categories from a journaled `reflection` record."""
    findings = record["findings"]
    assert isinstance(findings, list)
    categories: list[str] = []
    for finding in cast("list[object]", findings):
        assert isinstance(finding, dict)
        category = cast("dict[object, object]", finding)["category"]
        assert isinstance(category, str)
        categories.append(category)
    return categories


# --------------------------------------------------------------------------
# resolve_mode — the always-wired lever
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("off", "off"),
        ("observe", "observe"),
        ("file", "file"),
        (None, "observe"),
        ("", "observe"),
        ("garbage", "observe"),
    ],
)
def test_resolve_mode_resolves_lever(*, raw: str | None, expected: str) -> None:
    assert reflection.resolve_mode(raw=raw) == expected


# --------------------------------------------------------------------------
# scan_outcomes — the pure mechanical scan (NO LLM)
# --------------------------------------------------------------------------


def test_scan_clusters_failures_blocked_and_degraded() -> None:
    outcomes = (
        _outcome(work_item_id="a-1", status="green", stage="done"),
        _outcome(work_item_id="b-2", status="failed", stage="fabro-run"),
        _outcome(work_item_id="c-3", status="blocked", stage="fabro-run"),
        _outcome(work_item_id="d-4", status="green", stage="janitor-env-degraded"),
    )
    report = reflection.scan_outcomes(outcomes=outcomes, records=(), mode="observe")
    assert report.mode == "observe"
    assert report.item_count == 4
    assert report.green_count == 2
    assert report.failed_count == 1
    assert report.blocked_count == 1
    categories = {finding.category for finding in report.findings}
    assert categories == {"janitor-env-degraded", "failed-cluster", "blocked-at-human-gate"}


def test_scan_reports_journal_signals_timeout_retry_sizing() -> None:
    records = _records(
        {"stage": "fabro-run", "work_item_id": "a-1", "exit_code": 124},
        {"stage": "sizing-warn", "work_item_id": "a-1"},
        {"stage": "pr-update-branch", "work_item_id": "b-2"},
        {"stage": "pr-view", "work_item_id": "c-3"},
        {"stage": "pr-view", "work_item_id": "c-3"},
    )
    report = reflection.scan_outcomes(outcomes=(_outcome(),), records=records, mode="observe")
    categories = {finding.category for finding in report.findings}
    assert "stage-timeout" in categories
    assert "sizing-warn" in categories
    assert "stage-retry" in categories
    retry = next(f for f in report.findings if f.category == "stage-retry")
    # b-2 (pr-update-branch) and c-3 (two pr-views) both flagged as retries.
    assert retry.count == 2


def test_scan_no_signals_yields_no_findings() -> None:
    report = reflection.scan_outcomes(outcomes=(_outcome(),), records=(), mode="observe")
    assert report.findings == ()
    assert report.green_streak == 1


def test_scan_ignores_malformed_record_fields() -> None:
    # Records lacking string work_item_id / stage must be skipped, not crash.
    records = _records(
        {"stage": 123, "work_item_id": "a-1"},
        {"stage": "pr-view", "work_item_id": 999},
        {"exit_code": 124},
        # A sizing-warn whose work_item_id is not a string is ignored.
        {"stage": "sizing-warn", "work_item_id": 7},
        # A timeout record whose work_item_id is not a string is ignored.
        {"stage": "fabro-run", "work_item_id": 7, "exit_code": 124},
    )
    report = reflection.scan_outcomes(outcomes=(_outcome(),), records=records, mode="observe")
    assert {f.category for f in report.findings} == set()


def test_scan_dedupes_repeated_sizing_and_timeout_ids() -> None:
    # The same item appearing twice in a signal contributes one id only
    # (the `item not in ids` guard).
    records = _records(
        {"stage": "sizing-warn", "work_item_id": "a-1"},
        {"stage": "sizing-warn", "work_item_id": "a-1"},
        {"stage": "fabro-run", "work_item_id": "b-2", "exit_code": 124},
        {"stage": "fabro-inspect", "work_item_id": "b-2", "exit_code": 124},
    )
    report = reflection.scan_outcomes(outcomes=(_outcome(),), records=records, mode="observe")
    sizing = next(f for f in report.findings if f.category == "sizing-warn")
    timeout = next(f for f in report.findings if f.category == "stage-timeout")
    assert sizing.count == 1
    assert timeout.count == 1


def test_trailing_green_streak_stops_at_first_non_green() -> None:
    outcomes = (
        _outcome(work_item_id="a-1", status="failed", stage="fabro-run"),
        _outcome(work_item_id="b-2", status="green"),
        _outcome(work_item_id="c-3", status="green"),
    )
    report = reflection.scan_outcomes(outcomes=outcomes, records=(), mode="observe")
    assert report.green_streak == 2


# --------------------------------------------------------------------------
# reflect — observe mode (default), end to end
# --------------------------------------------------------------------------


def test_reflect_observe_writes_record_summary_and_spans(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LIVESPEC_REFLECTION", "observe")
    journal_path = tmp_path / "journal.jsonl"
    spans_path = tmp_path / "spans.jsonl"
    journal = JournalFile(path=journal_path)
    journal.append(record={"stage": "sizing-warn", "work_item_id": "a-1"})
    reflection.reflect(
        outcomes=[_outcome(work_item_id="a-1")],
        journal=journal,
        journal_path=journal_path,
        spans_path=spans_path,
    )
    record = next(
        rec for rec in _journal_records(journal_path=journal_path) if rec["stage"] == "reflection"
    )
    assert record["mode"] == "observe"
    assert record["item_count"] == 1
    assert record["green_count"] == 1
    assert _record_finding_categories(record=record) == ["sizing-warn"]
    # Human summary rides stderr (the loop summary diagnostic channel).
    err = capsys.readouterr().err
    assert "reflection (observe)" in err
    assert "sizing-warn" in err
    # OTLP spans written one ExportTraceServiceRequest per line.
    spans_doc = json.loads(spans_path.read_text(encoding="utf-8").strip())
    resource = spans_doc["resourceSpans"][0]
    svc = {a["key"]: a["value"]["stringValue"] for a in resource["resource"]["attributes"]}
    assert svc["service.name"] == "livespec-dispatcher"
    assert svc["service.namespace"] == "livespec-family"
    spans = resource["scopeSpans"][0]["spans"]
    names = [span["name"] for span in spans]
    assert names == ["reflection.pass", "reflection.finding"]
    # The finding span is a child of the pass span.
    assert spans[1]["parentSpanId"] == spans[0]["spanId"]


def test_reflect_observe_no_findings_summary(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LIVESPEC_REFLECTION", "observe")
    journal_path = tmp_path / "journal.jsonl"
    journal = JournalFile(path=journal_path)
    reflection.reflect(
        outcomes=[_outcome()],
        journal=journal,
        journal_path=journal_path,
        spans_path=tmp_path / "spans.jsonl",
    )
    assert "reflection: no findings" in capsys.readouterr().err


def test_reflect_reads_records_from_disk_journal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The on-disk journal (already flushed by the loop) is the scan's read
    # surface; a timeout record there must surface as a finding.
    monkeypatch.setenv("LIVESPEC_REFLECTION", "observe")
    journal_path = tmp_path / "journal.jsonl"
    journal = JournalFile(path=journal_path)
    journal.append(record={"stage": "fabro-run", "work_item_id": "b-2", "exit_code": 124})
    reflection.reflect(
        outcomes=[_outcome(work_item_id="b-2")],
        journal=journal,
        journal_path=journal_path,
        spans_path=tmp_path / "spans.jsonl",
    )
    record = next(
        rec for rec in _journal_records(journal_path=journal_path) if rec["stage"] == "reflection"
    )
    assert "stage-timeout" in _record_finding_categories(record=record)


def test_reflect_tolerates_missing_journal_and_malformed_lines(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LIVESPEC_REFLECTION", "observe")
    journal_path = tmp_path / "journal.jsonl"
    # A non-JSON line AND a valid-JSON-but-non-dict line must both be
    # skipped, not raise (fail-open scan).
    _ = journal_path.write_text("not json\n42\n", encoding="utf-8")
    journal = JournalFile(path=journal_path)
    reflection.reflect(
        outcomes=[_outcome()],
        journal=journal,
        journal_path=journal_path,
        spans_path=tmp_path / "spans.jsonl",
    )
    assert "reflection" in _stages(journal_path=journal_path)


def test_read_journal_records_empty_when_file_absent(tmp_path: Path) -> None:
    assert read_journal_records(journal_path=tmp_path / "nope.jsonl") == ()


# --------------------------------------------------------------------------
# reflect — off mode (the explicit silence value; still always wired)
# --------------------------------------------------------------------------


def test_reflect_off_is_a_noop(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LIVESPEC_REFLECTION", "off")
    journal_path = tmp_path / "journal.jsonl"
    spans_path = tmp_path / "spans.jsonl"
    reflection.reflect(
        outcomes=[_outcome()],
        journal=JournalFile(path=journal_path),
        journal_path=journal_path,
        spans_path=spans_path,
    )
    assert not journal_path.exists()
    assert not spans_path.exists()
    assert capsys.readouterr().err == ""


# --------------------------------------------------------------------------
# reflect — file mode (additionally journals the out-of-band hand-off)
# --------------------------------------------------------------------------


def test_reflect_file_emits_handoff_record_when_findings(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LIVESPEC_REFLECTION", "file")
    journal_path = tmp_path / "journal.jsonl"
    journal = JournalFile(path=journal_path)
    journal.append(record={"stage": "sizing-warn", "work_item_id": "a-1"})
    reflection.reflect(
        outcomes=[_outcome(work_item_id="a-1")],
        journal=journal,
        journal_path=journal_path,
        spans_path=tmp_path / "spans.jsonl",
    )
    assert "reflection-file-handoff" in _stages(journal_path=journal_path)


def test_reflect_file_no_handoff_when_no_findings(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LIVESPEC_REFLECTION", "file")
    journal_path = tmp_path / "journal.jsonl"
    reflection.reflect(
        outcomes=[_outcome()],
        journal=JournalFile(path=journal_path),
        journal_path=journal_path,
        spans_path=tmp_path / "spans.jsonl",
    )
    stages = _stages(journal_path=journal_path)
    assert "reflection" in stages
    assert "reflection-file-handoff" not in stages


# --------------------------------------------------------------------------
# reflect — fail-open + auto-trip + time-box
# --------------------------------------------------------------------------


def test_reflect_fail_open_catches_error_and_journals_it(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LIVESPEC_REFLECTION", "observe")
    journal_path = tmp_path / "journal.jsonl"
    journal = JournalFile(path=journal_path)
    journal.append(record={"stage": "loop-pick"})
    # A directory at the spans path makes the OTLP write raise; reflect
    # must catch it, journal reflection-error, and never re-raise.
    spans_dir = tmp_path / "spans-as-dir"
    spans_dir.mkdir()
    reflection.reflect(
        outcomes=[_outcome()],
        journal=journal,
        journal_path=journal_path,
        spans_path=spans_dir,
    )
    assert "reflection-error" in _stages(journal_path=journal_path)
    assert "fail-open, verdict unchanged" in capsys.readouterr().err


def test_reflect_auto_trips_after_three_consecutive_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LIVESPEC_REFLECTION", "observe")
    journal_path = tmp_path / "journal.jsonl"
    journal = JournalFile(path=journal_path)
    journal.append(record={"stage": "loop-pick"})
    spans_dir = tmp_path / "spans-as-dir"
    spans_dir.mkdir()
    for _ in range(4):
        reflection.reflect(
            outcomes=[_outcome()],
            journal=journal,
            journal_path=journal_path,
            spans_path=spans_dir,
        )
    stages = _stages(journal_path=journal_path)
    # Exactly three errors recorded: the fourth call short-circuits on the
    # tripped state and does nothing.
    assert stages.count("reflection-error") == 3
    assert "reflection-tripped" in stages


def test_reflect_resets_error_streak_after_a_clean_pass(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LIVESPEC_REFLECTION", "observe")
    journal_path = tmp_path / "journal.jsonl"
    journal = JournalFile(path=journal_path)
    spans_dir = tmp_path / "spans-as-dir"
    spans_dir.mkdir()
    # Two errors, then a clean pass resets the streak below the threshold.
    reflection.reflect(
        outcomes=[_outcome()], journal=journal, journal_path=journal_path, spans_path=spans_dir
    )
    reflection.reflect(
        outcomes=[_outcome()], journal=journal, journal_path=journal_path, spans_path=spans_dir
    )
    reflection.reflect(
        outcomes=[_outcome()],
        journal=journal,
        journal_path=journal_path,
        spans_path=tmp_path / "good-spans.jsonl",
    )
    reflection.reflect(
        outcomes=[_outcome()], journal=journal, journal_path=journal_path, spans_path=spans_dir
    )
    stages = _stages(journal_path=journal_path)
    assert stages.count("reflection-error") == 3
    assert "reflection-tripped" not in stages


def test_reflect_time_box_bails_fail_open(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LIVESPEC_REFLECTION", "observe")
    # Force the monotonic clock past the deadline so the first budget
    # check raises; reflect must catch it as a reflection-error (fail-open).
    clock = iter([0.0, 61.0, 1000.0, 1000.0])
    monkeypatch.setattr(reflection.time, "monotonic", lambda: next(clock))
    journal_path = tmp_path / "journal.jsonl"
    journal = JournalFile(path=journal_path)
    reflection.reflect(
        outcomes=[_outcome()],
        journal=journal,
        journal_path=journal_path,
        spans_path=tmp_path / "spans.jsonl",
    )
    errors = [
        rec
        for rec in _journal_records(journal_path=journal_path)
        if rec["stage"] == "reflection-error"
    ]
    assert errors
    assert "time budget" in str(errors[0]["reason"])


# --------------------------------------------------------------------------
# credential hygiene (cc-otel-gap-analysis.md §3.6)
# --------------------------------------------------------------------------


def test_scrub_redacts_credential_shaped_url() -> None:
    redacted = _scrub(value="https://x-access-token:ghp_secretsecret@github.com/org/repo")
    assert redacted == "[redacted-credential-shaped-value]"


def test_scrub_passes_and_truncates_plain_value() -> None:
    assert _scrub(value="plain") == "plain"
    long_value = "x" * (_ATTR_MAX_LEN + 50)
    assert len(_scrub(value=long_value)) == _ATTR_MAX_LEN


def test_attr_typing_int_bool_and_string() -> None:
    assert _attr(key="k", value=True) == {"key": "k", "value": {"boolValue": True}}
    assert _attr(key="k", value=5) == {"key": "k", "value": {"intValue": "5"}}
    assert _attr(key="k", value="s") == {"key": "k", "value": {"stringValue": "s"}}
