"""Tests for the post-dispatch Fabro `run_turn` telemetry assertion."""

from __future__ import annotations

import json
from argparse import Namespace
from pathlib import Path
from typing import cast

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import run_turn_sink_path
from livespec_orchestrator_beads_fabro.commands._dispatcher_reflection_journal import (
    items_with_run_turn_absence,
    read_journal_records,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_run_turn_diagnostics import (
    RunTurnTraceRequest,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_run_turn_guard import (
    append_run_turn_checks,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_run_turn_sink import RunTurnSink


def _outcome(*, work_item_id: str, status: str = "green") -> DispatchOutcome:
    return DispatchOutcome(
        work_item_id=work_item_id,
        status=status,
        stage="done",
        pr_number=7,
        merge_sha="abc123",
        detail="merged",
    )


def _records(*, path: Path) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        parsed = json.loads(line)
        assert isinstance(parsed, dict)
        records.append(cast("dict[str, object]", parsed))
    return records


def _args(*, journal: Path) -> Namespace:
    return Namespace(journal=journal)


def test_run_turn_sink_path_is_host_global_for_the_fabro_dataset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state_home = tmp_path / "state"
    monkeypatch.setenv("XDG_STATE_HOME", str(state_home))
    first = run_turn_sink_path(
        args=_args(journal=tmp_path / "repo-a" / "tmp" / "journal.jsonl"),
        repo=tmp_path / "repo-a",
    )
    second = run_turn_sink_path(
        args=_args(journal=tmp_path / "repo-b" / "tmp" / "journal.jsonl"),
        repo=tmp_path / "repo-b",
    )

    expected = state_home / "livespec-orchestrator-beads-fabro" / "run-turn-exports" / "fabro.json"
    assert first == expected
    assert second == expected


def test_append_run_turn_checks_rejects_a_global_only_run_turn_marker(tmp_path: Path) -> None:
    """A global `fabro.run_turn` marker attributes an export to NO dispatch.

    The sink is host-global (see the path test above), so this key is the
    last-export timestamp of whichever dispatch exported most recently —
    possibly another repository's. Counting it satisfied every concurrent
    dispatch's check from one unrelated export.
    """
    journal_path = tmp_path / "journal.jsonl"
    journal = JournalFile(path=journal_path)
    journal.append(
        record={
            "stage": "dispatch-id",
            "work_item_id": "bd-ib-demo",
            "dispatch_id": "disp-1",
            "started_at_epoch": 20.0,
        }
    )
    sink_path = tmp_path / "run-turn.json"
    _ = sink_path.write_text(json.dumps({"fabro.run_turn": 30.0}), encoding="utf-8")

    append_run_turn_checks(
        outcomes=(_outcome(work_item_id="bd-ib-demo"),),
        journal=journal,
        journal_path=journal_path,
        sink=RunTurnSink(path=sink_path),
    )

    check = _records(path=journal_path)[-1]
    assert check["run_turn_exported"] is False


def test_append_run_turn_checks_journals_green_outcome_presence(tmp_path: Path) -> None:
    journal_path = tmp_path / "journal.jsonl"
    journal = JournalFile(path=journal_path)
    journal.append(
        record={"stage": "dispatch-id", "work_item_id": "bd-ib-demo", "dispatch_id": "disp-1"}
    )
    sink = RunTurnSink(path=tmp_path / "run-turn.json")
    _ = sink.record_export(
        span={"name": "run_turn"},
        resource_attrs={"livespec.dispatch.id": "disp-1"},
        dataset="fabro",
        at=10.0,
    )

    append_run_turn_checks(
        outcomes=(_outcome(work_item_id="bd-ib-demo"),),
        journal=journal,
        journal_path=journal_path,
        sink=sink,
    )

    check = _records(path=journal_path)[-1]
    assert {
        key: check[key] for key in ("dispatch_id", "run_turn_exported", "stage", "work_item_id")
    } == {
        "dispatch_id": "disp-1",
        "run_turn_exported": True,
        "stage": "run-turn-telemetry-check",
        "work_item_id": "bd-ib-demo",
    }


@pytest.mark.parametrize(
    ("exported_at", "expected"),
    [
        pytest.param(10.0, False, id="before-this-dispatch-started"),
        pytest.param(30.0, True, id="after-this-dispatch-started"),
    ],
)
def test_append_run_turn_checks_dates_a_correlated_export_against_the_start(
    *, tmp_path: Path, exported_at: float, expected: bool
) -> None:
    """A dispatch's own ids recur across its re-dispatches, so the instant decides.

    `disp-old` is this item's PREVIOUS dispatch id, and the work-item id is
    the same every time, so a key matching on identity alone would let a
    months-old export discharge today's check.
    """
    journal_path = tmp_path / "journal.jsonl"
    journal = JournalFile(path=journal_path)
    journal.append(
        record={
            "stage": "dispatch-id",
            "work_item_id": "bd-ib-old",
            "dispatch_id": "disp-old",
            "started_at_epoch": 20.0,
        }
    )
    sink = RunTurnSink(path=tmp_path / "run-turn.json")
    _ = sink.record_export(
        span={"name": "run_turn"},
        resource_attrs={"work.item.id": "bd-ib-old", "livespec.dispatch.id": "disp-old"},
        dataset="fabro",
        at=exported_at,
    )

    append_run_turn_checks(
        outcomes=(_outcome(work_item_id="bd-ib-old"),),
        journal=journal,
        journal_path=journal_path,
        sink=sink,
    )

    check = _records(path=journal_path)[-1]
    assert check["work_item_id"] == "bd-ib-old"
    assert check["run_turn_exported"] is expected


def test_append_run_turn_checks_attributes_an_export_to_one_of_two_dispatches(
    tmp_path: Path,
) -> None:
    """One dispatch's export discharges that dispatch's check and no other's.

    Both dispatches are in flight, both are green, and the single export
    carries only `disp-1`'s ids. The receiver-level observation — "some
    `run_turn` export succeeded since you started" — is true for BOTH, which
    is exactly why it cannot stand in for attribution; it is journaled beside
    the verdict instead of folded into it.
    """
    journal_path = tmp_path / "journal.jsonl"
    journal = JournalFile(path=journal_path)
    for work_item_id, dispatch_id, started in (
        ("bd-ib-one", "disp-1", 10.0),
        ("bd-ib-two", "disp-2", 20.0),
    ):
        journal.append(
            record={
                "stage": "dispatch-id",
                "work_item_id": work_item_id,
                "dispatch_id": dispatch_id,
                "started_at_epoch": started,
            }
        )
    sink = RunTurnSink(path=tmp_path / "run-turn.json")
    _ = sink.record_export(
        span={"name": "run_turn"},
        resource_attrs={"work.item.id": "bd-ib-one", "livespec.dispatch.id": "disp-1"},
        dataset="fabro",
        at=30.0,
    )
    # The receiver records BOTH per export request, so the realistic fixture
    # carries both: the attributable key and the unattributable count.
    sink.record_trace_request(
        request=RunTurnTraceRequest(
            ingested_spans=1,
            enriched_spans=1,
            dataset_batch_sizes={"fabro": 1},
            export_results={"fabro": True},
            run_turn_sink_missing=False,
            successful_run_turn_exports=1,
            at=30.0,
        )
    )

    append_run_turn_checks(
        outcomes=(
            _outcome(work_item_id="bd-ib-one"),
            _outcome(work_item_id="bd-ib-two"),
        ),
        journal=journal,
        journal_path=journal_path,
        sink=sink,
    )

    checks = {
        record["work_item_id"]: record
        for record in _records(path=journal_path)
        if record.get("stage") == "run-turn-telemetry-check"
    }
    assert checks["bd-ib-one"]["run_turn_exported"] is True
    assert checks["bd-ib-two"]["run_turn_exported"] is False
    assert checks["bd-ib-two"]["run_turn_receiver_observed"] is True


def test_append_run_turn_checks_journals_the_receiver_observation_separately(
    tmp_path: Path,
) -> None:
    """A receiver-level `run_turn` export is recorded, never counted as this one's.

    `successful_run_turn_exports` is a per-REQUEST count the receiver keeps;
    it says an export happened, not whose. Both fields are written so an
    operator reading an absence can tell "the receiver saw nothing at all"
    apart from "the receiver saw someone else's".
    """
    journal_path = tmp_path / "journal.jsonl"
    journal = JournalFile(path=journal_path)
    journal.append(
        record={
            "stage": "dispatch-id",
            "work_item_id": "bd-ib-demo",
            "dispatch_id": "disp-1",
            "started_at_epoch": 20.0,
        }
    )
    sink = RunTurnSink(path=tmp_path / "run-turn.json")
    sink.record_trace_request(
        request=RunTurnTraceRequest(
            ingested_spans=1,
            enriched_spans=1,
            dataset_batch_sizes={"fabro": 1},
            export_results={"fabro": True},
            run_turn_sink_missing=False,
            successful_run_turn_exports=1,
            at=30.0,
        )
    )

    append_run_turn_checks(
        outcomes=(_outcome(work_item_id="bd-ib-demo"),),
        journal=journal,
        journal_path=journal_path,
        sink=sink,
    )

    check = _records(path=journal_path)[-1]
    assert check["run_turn_exported"] is False
    assert check["run_turn_receiver_observed"] is True


def test_append_run_turn_checks_rejects_receiver_export_without_run_turn(
    tmp_path: Path,
) -> None:
    journal_path = tmp_path / "journal.jsonl"
    journal = JournalFile(path=journal_path)
    journal.append(
        record={
            "stage": "dispatch-id",
            "work_item_id": "bd-ib-demo",
            "dispatch_id": "disp-1",
            "started_at_epoch": 20.0,
        }
    )
    sink = RunTurnSink(path=tmp_path / "run-turn.json")
    sink.record_trace_request(
        request=RunTurnTraceRequest(
            ingested_spans=1,
            enriched_spans=1,
            dataset_batch_sizes={"fabro": 1},
            export_results={"fabro": True},
            run_turn_sink_missing=False,
            successful_run_turn_exports=0,
            at=30.0,
        )
    )

    append_run_turn_checks(
        outcomes=(_outcome(work_item_id="bd-ib-demo"),),
        journal=journal,
        journal_path=journal_path,
        sink=sink,
    )

    check = _records(path=journal_path)[-1]
    assert check["run_turn_exported"] is False
    assert check["run_turn_receiver_observed"] is False


def test_append_run_turn_checks_journals_absence_and_skips_failed(tmp_path: Path) -> None:
    journal_path = tmp_path / "journal.jsonl"
    journal = JournalFile(path=journal_path)
    journal.append(
        record={"stage": "dispatch-id", "work_item_id": "bd-ib-demo", "dispatch_id": "disp-1"}
    )

    append_run_turn_checks(
        outcomes=(
            _outcome(work_item_id="bd-ib-demo"),
            _outcome(work_item_id="bd-ib-failed", status="failed"),
        ),
        journal=journal,
        journal_path=journal_path,
        sink=RunTurnSink(path=tmp_path / "run-turn.json"),
    )

    checks = [
        record
        for record in _records(path=journal_path)
        if record.get("stage") == "run-turn-telemetry-check"
    ]
    assert [
        {key: check[key] for key in ("dispatch_id", "run_turn_exported", "stage", "work_item_id")}
        for check in checks
    ] == [
        {
            "dispatch_id": "disp-1",
            "run_turn_exported": False,
            "stage": "run-turn-telemetry-check",
            "work_item_id": "bd-ib-demo",
        }
    ]


def test_append_run_turn_checks_marks_hp_factory_unobservable_not_absent(
    tmp_path: Path,
) -> None:
    journal_path = tmp_path / "journal.jsonl"
    journal = JournalFile(path=journal_path)
    journal.append(
        record={
            "stage": "dispatch-id",
            "work_item_id": "bd-ib-demo",
            "dispatch_id": "disp-1",
            "dispatch_factory": "hp",
            "dispatch_factory_exports_run_turn_telemetry": False,
            "started_at_epoch": 20.0,
        }
    )

    append_run_turn_checks(
        outcomes=(_outcome(work_item_id="bd-ib-demo"),),
        journal=journal,
        journal_path=journal_path,
        sink=RunTurnSink(path=tmp_path / "run-turn.json"),
    )

    records = read_journal_records(journal_path=journal_path)
    check = records[-1]
    assert check["run_turn_observable"] is False
    assert check["run_turn_observation"] == "unobservable-remote-factory"
    assert check["run_turn_exported"] is False
    assert items_with_run_turn_absence(records=records) == ()


def test_append_run_turn_checks_marks_any_non_exporting_factory_unobservable(
    tmp_path: Path,
) -> None:
    journal_path = tmp_path / "journal.jsonl"
    journal = JournalFile(path=journal_path)
    journal.append(
        record={
            "stage": "dispatch-id",
            "work_item_id": "bd-ib-demo",
            "dispatch_id": "disp-1",
            "dispatch_factory": "hp-candidate",
            "dispatch_factory_exports_run_turn_telemetry": False,
            "started_at_epoch": 20.0,
        }
    )

    append_run_turn_checks(
        outcomes=(_outcome(work_item_id="bd-ib-demo"),),
        journal=journal,
        journal_path=journal_path,
        sink=RunTurnSink(path=tmp_path / "run-turn.json"),
    )

    records = read_journal_records(journal_path=journal_path)
    check = records[-1]
    assert check["run_turn_observable"] is False
    assert check["run_turn_observation"] == "unobservable-remote-factory"
    assert items_with_run_turn_absence(records=records) == ()


def test_append_run_turn_checks_observes_a_factory_declaring_run_turn_export(
    tmp_path: Path,
) -> None:
    journal_path = tmp_path / "journal.jsonl"
    journal = JournalFile(path=journal_path)
    journal.append(
        record={
            "stage": "dispatch-id",
            "work_item_id": "bd-ib-demo",
            "dispatch_id": "disp-1",
            "dispatch_factory": "hp",
            "dispatch_factory_exports_run_turn_telemetry": True,
            "started_at_epoch": 20.0,
        }
    )

    append_run_turn_checks(
        outcomes=(_outcome(work_item_id="bd-ib-demo"),),
        journal=journal,
        journal_path=journal_path,
        sink=RunTurnSink(path=tmp_path / "run-turn.json"),
    )

    check = _records(path=journal_path)[-1]
    assert check["run_turn_observable"] is True
    assert "run_turn_observation" not in check


def test_append_run_turn_checks_ignores_malformed_dispatch_id_records(tmp_path: Path) -> None:
    journal_path = tmp_path / "journal.jsonl"
    journal = JournalFile(path=journal_path)
    journal.append(record={"stage": "dispatch-id", "work_item_id": 7, "dispatch_id": "bad"})
    journal.append(record={"stage": "other", "work_item_id": "bd-ib-demo", "dispatch_id": "bad"})

    append_run_turn_checks(
        outcomes=(_outcome(work_item_id="bd-ib-demo"),),
        journal=journal,
        journal_path=journal_path,
        sink=RunTurnSink(path=tmp_path / "run-turn.json"),
    )

    check = _records(path=journal_path)[-1]
    assert check["dispatch_id"] == ""
    assert check["run_turn_exported"] is False


def test_run_turn_sink_stores_no_key_for_an_uncorrelated_run_turn_export(
    tmp_path: Path,
) -> None:
    """An export carrying no correlation id is ACCEPTED and attributed to nothing.

    Acceptance is the receiver's own fact and stays visible in the
    diagnostics; what it must not do is leave a key behind that some
    dispatch's check can match.
    """
    path = tmp_path / "run-turn.json"
    sink = RunTurnSink(path=path)
    assert (
        sink.record_export(
            span={"name": "run_turn"},
            resource_attrs={},
            dataset="fabro",
            at=10.0,
        )
        is True
    )
    assert sink.has_export(keys=("",)) is False
    assert json.loads(path.read_text(encoding="utf-8")) == {}


def test_run_turn_sink_writes_non_secret_diagnostics_for_record_attempts(tmp_path: Path) -> None:
    sink = RunTurnSink(path=tmp_path / "run-turn.json")
    assert (
        sink.record_export(
            span={"name": "agent.turn"},
            resource_attrs={"work.item.id": "bd-ib-demo"},
            dataset="fabro",
            at=10.0,
        )
        is False
    )
    assert (
        sink.record_export(
            span={"name": "run_turn"},
            resource_attrs={"work.item.id": "bd-ib-demo"},
            dataset="fabro",
            at=11.0,
        )
        is True
    )

    diagnostic = json.loads((tmp_path / "run-turn-diagnostics.json").read_text(encoding="utf-8"))
    assert diagnostic == {
        "accepted": 1,
        "last": {
            "at": 11.0,
            "dataset": "fabro",
            "reason": "accepted",
            "span_name": "run_turn",
        },
        "rejected": {"span-name": 1},
        "write_failures": 0,
    }


@pytest.mark.parametrize("raw", ["not-json", "[]", json.dumps({"key": True, "other": "text"})])
def test_run_turn_sink_reads_malformed_files_as_empty(tmp_path: Path, raw: str) -> None:
    path = tmp_path / "run-turn.json"
    _ = path.write_text(raw, encoding="utf-8")
    assert RunTurnSink(path=path).has_export(keys=("key", "other")) is False


def test_run_turn_sink_read_failure_is_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "run-turn.json"
    _ = path.write_text("{}", encoding="utf-8")

    def _raise_read_text(self: Path, encoding: str | None = None) -> str:
        _ = (self, encoding)
        raise OSError("unreadable")

    monkeypatch.setattr(Path, "read_text", _raise_read_text)
    assert RunTurnSink(path=path).has_export(keys=("key",)) is False


def test_run_turn_sink_scrubs_persisted_keys(tmp_path: Path) -> None:
    path = tmp_path / "run-turn.json"
    _ = path.write_text(
        json.dumps({"https://x-access-token:ghp_SECRET@github.com/o/r": 10.0}),
        encoding="utf-8",
    )
    assert RunTurnSink(path=path).has_export(keys=("[redacted-credential-shaped-value]",)) is True


def test_run_turn_sink_write_failure_is_fail_open(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "run-turn.json"

    def _raise_write_text(self: Path, text: str, encoding: str | None = None) -> int:
        _ = (self, text, encoding)
        raise OSError("disk full")

    monkeypatch.setattr(Path, "write_text", _raise_write_text)
    recorded = RunTurnSink(path=path).record_export(
        span={"name": "run_turn"},
        resource_attrs={"work.item.id": "bd-ib-demo"},
        dataset="fabro",
        at=10.0,
    )
    assert recorded is True
    assert path.exists() is False


def test_run_turn_sink_skips_malformed_span_attrs(tmp_path: Path) -> None:
    sink = RunTurnSink(path=tmp_path / "run-turn.json")
    recorded = sink.record_export(
        span={
            "name": "run_turn",
            "attributes": [
                "not-a-dict",
                {"key": 7, "value": {"stringValue": "ignored"}},
                {"key": "work.item.id", "value": "not-a-dict"},
                {"key": "work.item.id", "value": {"intValue": "7"}},
            ],
        },
        resource_attrs={"livespec.dispatch.id": "dispatch-1"},
        dataset="fabro",
        at=10.0,
    )
    assert recorded is True
    stored = json.loads((tmp_path / "run-turn.json").read_text(encoding="utf-8"))
    assert "ignored" not in stored
    assert "7" not in stored
    assert sink.has_export(keys=("dispatch-1",)) is True
