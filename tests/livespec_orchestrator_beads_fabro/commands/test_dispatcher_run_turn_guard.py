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


def test_append_run_turn_checks_rejects_a_foreign_run_global_marker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An export attributed to NO dispatch satisfies no dispatch's check.

    The sink is host-global, so the marker a span carrying no correlation ids
    wrote is the marker EVERY concurrent dispatch on this host would read. It
    was accepted as a hit until the sink attributed by correlation id alone,
    which made one repository's unattributable export answer another
    repository's question.
    """
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    local_repo = tmp_path / "local-repo"
    foreign_repo = tmp_path / "foreign-repo"
    journal_path = local_repo / "tmp" / "journal.jsonl"
    journal = JournalFile(path=journal_path)
    journal.append(
        record={
            "stage": "dispatch-id",
            "work_item_id": "bd-ib-demo",
            "dispatch_id": "disp-1",
            "started_at_epoch": 20.0,
        }
    )
    foreign_sink = RunTurnSink(
        path=run_turn_sink_path(
            args=_args(journal=foreign_repo / "tmp" / "journal.jsonl"),
            repo=foreign_repo,
        )
    )
    _ = foreign_sink.record_export(
        span={"name": "run_turn"}, resource_attrs={}, dataset="fabro", at=30.0
    )

    append_run_turn_checks(
        outcomes=(_outcome(work_item_id="bd-ib-demo"),),
        journal=journal,
        journal_path=journal_path,
        repo=journal_path.parent,
        sink=RunTurnSink(
            path=run_turn_sink_path(args=_args(journal=journal_path), repo=local_repo)
        ),
    )

    check = _records(path=journal_path)[-1]
    assert check["run_turn_exported"] is False


def test_append_run_turn_checks_attribute_one_dispatchs_export_to_that_dispatch_alone(
    tmp_path: Path,
) -> None:
    """One export's correlation ids answer its own dispatch and no other.

    Both dispatches below are green, both started before the export, and the
    export carries exactly one of their id pairs — so a sink that attributed by
    any host-global signal would report BOTH as exported, and a sink that
    attributed by nothing would report NEITHER. Only per-dispatch attribution
    splits the pair, which is why the two assertions are each other's control.
    """
    journal_path = tmp_path / "journal.jsonl"
    journal = JournalFile(path=journal_path)
    for work_item_id, dispatch_id in (("bd-ib-mine", "disp-mine"), ("bd-ib-other", "disp-other")):
        journal.append(
            record={
                "stage": "dispatch-id",
                "work_item_id": work_item_id,
                "dispatch_id": dispatch_id,
                "started_at_epoch": 20.0,
            }
        )
    sink = RunTurnSink(path=tmp_path / "run-turn.json")
    _ = sink.record_export(
        span={"name": "run_turn"},
        resource_attrs={"work.item.id": "bd-ib-mine", "livespec.dispatch.id": "disp-mine"},
        dataset="fabro",
        at=30.0,
    )

    append_run_turn_checks(
        outcomes=(
            _outcome(work_item_id="bd-ib-mine"),
            _outcome(work_item_id="bd-ib-other"),
        ),
        journal=journal,
        journal_path=journal_path,
        repo=journal_path.parent,
        sink=sink,
    )

    checks = {
        record["work_item_id"]: record["run_turn_exported"]
        for record in _records(path=journal_path)
        if record.get("stage") == "run-turn-telemetry-check"
    }
    assert checks == {"bd-ib-mine": True, "bd-ib-other": False}


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
        repo=journal_path.parent,
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


def test_append_run_turn_checks_ignores_stale_global_run_turn_exports(tmp_path: Path) -> None:
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
    _ = sink.record_export(span={"name": "run_turn"}, resource_attrs={}, dataset="fabro", at=10.0)

    append_run_turn_checks(
        outcomes=(_outcome(work_item_id="bd-ib-old"),),
        journal=journal,
        journal_path=journal_path,
        repo=journal_path.parent,
        sink=sink,
    )

    check = _records(path=journal_path)[-1]
    assert check["work_item_id"] == "bd-ib-old"
    assert check["run_turn_exported"] is False


@pytest.mark.parametrize("successful_run_turn_exports", [1, 0], ids=["observed", "none"])
def test_append_run_turn_checks_rejects_the_receivers_aggregate_observation(
    tmp_path: Path, successful_run_turn_exports: int
) -> None:
    """The receiver's own request counters answer no dispatch's question.

    `record_trace_request` counts `run_turn` exports PER OTLP REQUEST, with no
    dispatch in the record at all, so a dispatch satisfied from it is satisfied
    by whatever run happened to export inside its window — including another
    repository's. Parametrized over both counter values because an aggregate
    read of ONE of them is what used to decide this record, and the point is
    that neither decides it now.
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
            successful_run_turn_exports=successful_run_turn_exports,
            at=30.0,
        )
    )

    append_run_turn_checks(
        outcomes=(_outcome(work_item_id="bd-ib-demo"),),
        journal=journal,
        journal_path=journal_path,
        repo=journal_path.parent,
        sink=sink,
    )

    check = _records(path=journal_path)[-1]
    assert check["run_turn_exported"] is False


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
        repo=journal_path.parent,
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


def _repo_declaring_factory(*, repo: Path, entry: str) -> Path:
    """A dispatch target whose `dispatcher.factories.hp` entry is `entry`.

    The entry is written as JSON text rather than built from the resolver's own
    constants so a rename of the declaration key fails these assertions instead
    of silently agreeing with them.
    """
    _ = repo.mkdir(parents=True, exist_ok=True)
    _ = (repo / ".livespec.jsonc").write_text(
        '{"livespec-orchestrator-beads-fabro": {"dispatcher": {"factories": '
        f'{{"hp": {entry}}}}}}}}}',
        encoding="utf-8",
    )
    return repo


def test_append_run_turn_checks_marks_an_unexporting_factory_unobservable_not_absent(
    tmp_path: Path,
) -> None:
    journal_path = tmp_path / "repo" / "journal.jsonl"
    repo = _repo_declaring_factory(
        repo=journal_path.parent, entry='{"server": "https://hp.example:32276"}'
    )
    journal = JournalFile(path=journal_path)
    journal.append(
        record={
            "stage": "dispatch-id",
            "work_item_id": "bd-ib-demo",
            "dispatch_id": "disp-1",
            "dispatch_factory": "hp",
            "started_at_epoch": 20.0,
        }
    )

    append_run_turn_checks(
        outcomes=(_outcome(work_item_id="bd-ib-demo"),),
        journal=journal,
        journal_path=journal_path,
        repo=repo,
        sink=RunTurnSink(path=tmp_path / "run-turn.json"),
    )

    records = read_journal_records(journal_path=journal_path)
    check = records[-1]
    assert check["run_turn_observable"] is False
    assert check["run_turn_observation"] == "unobservable-remote-factory"
    assert check["run_turn_exported"] is False
    assert items_with_run_turn_absence(records=records) == ()


def test_append_run_turn_checks_names_an_unreadable_configuration_as_its_own_cause(
    tmp_path: Path,
) -> None:
    """An unreadable configuration is not a remote factory, and the row must not say so.

    The sibling case above is this one's control: both journal
    `run_turn_observable` False for a dispatch to a factory named `hp`, and only
    the repository's `.livespec.jsonc` differs — parseable there, a stray comma
    here. A record that collapses the two asserts a factory remoteness nobody
    measured, and sends the operator to the factory rather than to the config
    that actually darkened the gauge for every factory in the repository.
    """
    journal_path = tmp_path / "repo" / "journal.jsonl"
    repo = journal_path.parent
    repo.mkdir(parents=True, exist_ok=True)
    _ = (repo / ".livespec.jsonc").write_text("{ not json", encoding="utf-8")
    journal = JournalFile(path=journal_path)
    journal.append(
        record={
            "stage": "dispatch-id",
            "work_item_id": "bd-ib-demo",
            "dispatch_id": "disp-1",
            "dispatch_factory": "hp",
            "started_at_epoch": 20.0,
        }
    )

    append_run_turn_checks(
        outcomes=(_outcome(work_item_id="bd-ib-demo"),),
        journal=journal,
        journal_path=journal_path,
        repo=repo,
        sink=RunTurnSink(path=tmp_path / "run-turn.json"),
    )

    records = read_journal_records(journal_path=journal_path)
    check = records[-1]
    assert check["run_turn_observable"] is False
    assert check["run_turn_observation"] == "unobservable-unreadable-configuration"
    assert check["run_turn_exported"] is False
    assert items_with_run_turn_absence(records=records) == ()


def test_append_run_turn_checks_observes_a_factory_declaring_the_dispatcher_receiver(
    tmp_path: Path,
) -> None:
    """A factory OTHER than the one the name test knew is read from its own entry.

    The sibling case above is this one's control: both dispatch to a factory
    named `hp` with a server, and only the declaration differs, so a guard that
    still keyed on the name — or one that read every factory as observable —
    fails exactly one of the pair.
    """
    journal_path = tmp_path / "repo" / "journal.jsonl"
    repo = _repo_declaring_factory(
        repo=journal_path.parent,
        entry='{"server": "https://hp.example:32276", '
        '"run_turn_telemetry_export": "dispatcher_receiver"}',
    )
    journal = JournalFile(path=journal_path)
    journal.append(
        record={
            "stage": "dispatch-id",
            "work_item_id": "bd-ib-demo",
            "dispatch_id": "disp-1",
            "dispatch_factory": "hp",
            "started_at_epoch": 20.0,
        }
    )
    sink = RunTurnSink(path=tmp_path / "run-turn.json")
    _ = sink.record_export(
        span={"name": "run_turn"},
        resource_attrs={"work.item.id": "bd-ib-demo", "livespec.dispatch.id": "disp-1"},
        dataset="fabro",
        at=30.0,
    )

    append_run_turn_checks(
        outcomes=(_outcome(work_item_id="bd-ib-demo"),),
        journal=journal,
        journal_path=journal_path,
        repo=repo,
        sink=sink,
    )

    check = _records(path=journal_path)[-1]
    assert check["run_turn_observable"] is True
    assert check["run_turn_exported"] is True


def test_append_run_turn_checks_ignores_malformed_dispatch_id_records(tmp_path: Path) -> None:
    journal_path = tmp_path / "journal.jsonl"
    journal = JournalFile(path=journal_path)
    journal.append(record={"stage": "dispatch-id", "work_item_id": 7, "dispatch_id": "bad"})
    journal.append(record={"stage": "other", "work_item_id": "bd-ib-demo", "dispatch_id": "bad"})

    append_run_turn_checks(
        outcomes=(_outcome(work_item_id="bd-ib-demo"),),
        journal=journal,
        journal_path=journal_path,
        repo=journal_path.parent,
        sink=RunTurnSink(path=tmp_path / "run-turn.json"),
    )

    check = _records(path=journal_path)[-1]
    assert check["dispatch_id"] == ""
    assert check["run_turn_exported"] is False


def test_run_turn_sink_accepts_an_uncorrelated_export_without_attributing_it(
    tmp_path: Path,
) -> None:
    """An uncorrelated export is still ACCEPTED; it is simply attributed to nobody.

    The two halves are separate claims and the pairing is the point: the return
    value says the receiver observed a Fabro `run_turn` export, which the
    diagnostics beside it then count, while `has_export` says no dispatch can
    claim it. Collapsing either into the other would lose the signal or
    manufacture a hit.
    """
    sink = RunTurnSink(path=tmp_path / "run-turn.json")
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
    assert sink.has_export(keys=("bd-ib-demo", "disp-1")) is False


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
