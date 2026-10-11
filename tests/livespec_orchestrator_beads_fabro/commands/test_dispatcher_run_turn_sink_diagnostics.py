"""Edge coverage for `RunTurnSink` export-attempt diagnostics."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_run_turn_diagnostics import (
    RunTurnTraceRequest,
    record_run_turn_receiver_diagnostic,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_run_turn_sink import RunTurnSink


def test_run_turn_sink_diagnostics_reject_wrong_dataset_and_malformed_name(
    tmp_path: Path,
) -> None:
    sink = RunTurnSink(path=tmp_path / "run-turn.json")
    assert (
        sink.record_export(span={"name": "run_turn"}, resource_attrs={}, dataset="other", at=1.0)
        is False
    )
    assert sink.record_export(span={"name": 7}, resource_attrs={}, dataset="fabro", at=2.0) is False

    diagnostic = json.loads((tmp_path / "run-turn-diagnostics.json").read_text(encoding="utf-8"))
    assert diagnostic == {
        "accepted": 0,
        "last": {
            "at": 2.0,
            "dataset": "fabro",
            "reason": "span-name",
            "span_name": "",
        },
        "rejected": {"dataset": 1, "span-name": 1},
        "write_failures": 0,
    }


def test_run_turn_sink_diagnostics_reads_malformed_file_as_empty(tmp_path: Path) -> None:
    diagnostic_path = tmp_path / "run-turn-diagnostics.json"
    _ = diagnostic_path.write_text("not-json", encoding="utf-8")

    assert (
        RunTurnSink(path=tmp_path / "run-turn.json").record_export(
            span={"name": "run_turn"},
            resource_attrs={},
            dataset="fabro",
            at=3.0,
        )
        is True
    )

    diagnostic = json.loads(diagnostic_path.read_text(encoding="utf-8"))
    assert diagnostic["accepted"] == 1
    assert diagnostic["rejected"] == {}


def test_run_turn_sink_diagnostics_normalizes_bad_counter_shapes(tmp_path: Path) -> None:
    diagnostic_path = tmp_path / "run-turn-diagnostics.json"
    _ = diagnostic_path.write_text(
        json.dumps({"accepted": True, "rejected": [], "write_failures": "bad"}),
        encoding="utf-8",
    )

    assert (
        RunTurnSink(path=tmp_path / "run-turn.json").record_export(
            span={"name": "agent.turn"},
            resource_attrs={},
            dataset="fabro",
            at=4.0,
        )
        is False
    )

    diagnostic = json.loads(diagnostic_path.read_text(encoding="utf-8"))
    assert diagnostic["accepted"] == 0
    assert diagnostic["rejected"] == {"span-name": 1}
    assert diagnostic["write_failures"] == 0


def test_run_turn_receiver_diagnostics_write_without_sink_and_accumulate(
    tmp_path: Path,
) -> None:
    """Two requests against one diagnostics file ACCUMULATE rather than replace.

    The second call is what reads a stored `receiver` block back, so recording
    one request proves only that a first write lands — a diagnostic that reset
    its counters on every request would satisfy that and lose every count but
    the newest.
    """
    diagnostic_path = tmp_path / "run-turn-diagnostics.json"
    for at in (6.0, 7.0):
        record_run_turn_receiver_diagnostic(
            sink=None,
            diagnostics_path=diagnostic_path,
            request=RunTurnTraceRequest(
                ingested_spans=1,
                enriched_spans=1,
                dataset_batch_sizes={"fabro": 1},
                export_results={"fabro": True},
                run_turn_sink_missing=False,
                successful_run_turn_exports=1,
                at=at,
            ),
        )

    diagnostic = json.loads(diagnostic_path.read_text(encoding="utf-8"))
    assert diagnostic["receiver"]["requests"] == 2
    assert diagnostic["receiver"]["run_turn_sink_missing"] == 2
    assert diagnostic["receiver"]["last"]["run_turn_sink_missing"] is True
    assert diagnostic["receiver"]["last_successful_run_turn_export_at"] == 7.0


def test_run_turn_sink_diagnostics_read_failure_starts_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "run-turn.json"
    diagnostic_path = tmp_path / "run-turn-diagnostics.json"
    _ = path.write_text("{}", encoding="utf-8")
    _ = diagnostic_path.write_text("{}", encoding="utf-8")

    def _raise_for_diagnostic(self: Path, encoding: str | None = None) -> str:
        _ = encoding
        if self.name == "run-turn-diagnostics.json":
            raise OSError("unreadable")
        return "{}"

    monkeypatch.setattr(Path, "read_text", _raise_for_diagnostic)
    assert (
        RunTurnSink(path=path).record_export(
            span={"name": "run_turn"},
            resource_attrs={},
            dataset="fabro",
            at=5.0,
        )
        is True
    )

    with diagnostic_path.open(encoding="utf-8") as handle:
        diagnostic = json.load(handle)
    assert diagnostic["accepted"] == 1
