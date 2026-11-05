"""Behaviour of the preservation-before-restart cancellation coordinator."""

from __future__ import annotations

from argparse import Namespace
from dataclasses import dataclass
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands import _dispatcher_cancel_for_restart as subject
from livespec_orchestrator_beads_fabro.commands._config import FactoryTarget
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_preserved_tree_publish import (
    STEP_FILES_READ,
    PreservedTree,
    PublishFailure,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port_records import FabroRunSummary


@dataclass
class _Result:
    succeeded: bool
    payload: object | None = None


class _Http:
    def __init__(
        self, *, states: dict[str, _Result], calls: list[str], cancellation_succeeds: bool = True
    ) -> None:
        self._states = states
        self._calls = calls
        self._cancellation_succeeds = cancellation_succeeds

    def run_state(self, *, run_id: str, timeout_seconds: float) -> _Result:
        _ = timeout_seconds
        self._calls.append(f"state:{run_id}")
        return self._states[run_id]

    def cancel(self, *, run_id: str, timeout_seconds: float) -> _Result:
        _ = timeout_seconds
        self._calls.append(f"cancel:{run_id}")
        return _Result(succeeded=self._cancellation_succeeds)


class _Port:
    def __init__(
        self, *, runs: tuple[FabroRunSummary, ...], http: _Http, listing_succeeds: bool = True
    ) -> None:
        self._runs = runs
        self._http = http
        self._listing_succeeds = listing_succeeds

    def live_ps(self, *, timeout_seconds: float) -> object:
        _ = timeout_seconds
        return type(
            "Listed",
            (),
            {
                "command": CommandResult(
                    exit_code=0 if self._listing_succeeds else 1, stdout="", stderr=""
                ),
                "runs": self._runs,
            },
        )()

    def server_api(self) -> _Http:
        return self._http


def _run(*, run_id: str = "run-1", item: str | None = "bd-ib-adcaa6") -> FabroRunSummary:
    return FabroRunSummary(
        run_id=run_id,
        status_kind="running",
        goal=None,
        work_item_id=item,
        total_usd_micros=None,
    )


def _journal(*, tmp_path: Path) -> JournalFile:
    return JournalFile(path=tmp_path / "journal.jsonl")


def test_green_janitor_is_published_before_it_is_cancelled(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[str] = []
    http = _Http(
        states={
            "run-1": _Result(
                succeeded=True, payload={"stages": [{"node": "janitor", "status": "succeeded"}]}
            )
        },
        calls=calls,
    )

    def _publish(**kwargs: object) -> PreservedTree:
        calls.append("publish")
        assert kwargs["base_commit"] == "base"
        return PreservedTree(
            ref="refs/livespec/preserved-publish/bd-ib-adcaa6/commit",
            commit="commit",
            file_count=1,
            scope="committed",
            source="sandbox",
        )

    monkeypatch.setattr(subject, "publish_run_tree", _publish)
    result = subject.cancel_for_restart(
        repo=tmp_path,
        factory="petri",
        port=_Port(runs=(_run(),), http=http),  # type: ignore[arg-type]
        journal=_journal(tmp_path=tmp_path),
        records=(
            {"stage": "source-checkout-stage", "work_item_id": "bd-ib-adcaa6", "staged_at": "base"},
        ),
        runner=object(),  # type: ignore[arg-type]
    )

    assert result == ("CANCELLED run-1 factory=petri",)
    assert calls == ["state:run-1", "publish", "cancel:run-1"]


def test_non_green_run_is_cancelled_without_a_preservation_attempt(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[str] = []
    http = _Http(
        states={
            "run-1": _Result(succeeded=True, payload={"node": "implement", "status": "succeeded"})
        },
        calls=calls,
    )
    monkeypatch.setattr(subject, "publish_run_tree", lambda **_: pytest.fail("must not publish"))

    result = subject.cancel_for_restart(
        repo=tmp_path,
        factory="petri",
        port=_Port(runs=(_run(),), http=http),  # type: ignore[arg-type]
        journal=_journal(tmp_path=tmp_path),
        records=(),
        runner=object(),  # type: ignore[arg-type]
    )

    assert result == ("CANCELLED run-1 factory=petri",)
    assert calls == ["state:run-1", "cancel:run-1"]


def test_unreadable_green_tree_is_recorded_then_cancelled(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[str] = []
    comments: list[str] = []
    http = _Http(
        states={"run-1": _Result(succeeded=True, payload={"node": "janitor", "state": "green"})},
        calls=calls,
    )
    monkeypatch.setattr(
        subject,
        "publish_run_tree",
        lambda **_: PublishFailure(step=STEP_FILES_READ, detail="factory did not serve files"),
    )
    monkeypatch.setattr(subject, "store_config", lambda **_: object())
    monkeypatch.setattr(
        subject, "append_work_item_comment", lambda **kwargs: comments.append(kwargs["body"])
    )

    result = subject.cancel_for_restart(
        repo=tmp_path,
        factory="petri",
        port=_Port(runs=(_run(),), http=http),  # type: ignore[arg-type]
        journal=_journal(tmp_path=tmp_path),
        records=(
            {"stage": "source-checkout-stage", "work_item_id": "bd-ib-adcaa6", "staged_at": "base"},
        ),
        runner=object(),  # type: ignore[arg-type]
    )

    assert result == ("CANCELLED run-1 factory=petri",)
    assert "livespec-preserved-tree" in comments[0]
    assert "failed step: files-read" in comments[0]
    assert calls == ["state:run-1", "cancel:run-1"]


def test_forge_failure_keeps_green_run_alive(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[str] = []
    http = _Http(
        states={
            "run-1": _Result(succeeded=True, payload={"stage": "janitor", "outcome": "success"})
        },
        calls=calls,
    )
    monkeypatch.setattr(
        subject, "publish_run_tree", lambda **_: PublishFailure(step="ref", detail="ref rejected")
    )
    monkeypatch.setattr(subject, "store_config", lambda **_: object())
    monkeypatch.setattr(subject, "append_work_item_comment", lambda **_: None)

    result = subject.cancel_for_restart(
        repo=tmp_path,
        factory="petri",
        port=_Port(runs=(_run(),), http=http),  # type: ignore[arg-type]
        journal=_journal(tmp_path=tmp_path),
        records=(
            {"stage": "source-checkout-stage", "work_item_id": "bd-ib-adcaa6", "staged_at": "base"},
        ),
        runner=object(),  # type: ignore[arg-type]
    )

    assert result == ("HELD run-1 factory=petri preservation-ref-missing",)
    assert calls == ["state:run-1"]


def test_state_unavailable_and_unattributed_green_runs_are_not_cancelled(tmp_path: Path) -> None:
    calls: list[str] = []
    http = _Http(
        states={
            "unreadable": _Result(succeeded=False),
            "unattributed": _Result(
                succeeded=True, payload={"node": "janitor", "status": "succeeded"}
            ),
        },
        calls=calls,
    )
    result = subject.cancel_for_restart(
        repo=tmp_path,
        factory="petri",
        port=_Port(
            runs=(_run(run_id="unreadable"), _run(run_id="unattributed", item=None)), http=http
        ),  # type: ignore[arg-type]
        journal=_journal(tmp_path=tmp_path),
        records=(),
        runner=object(),  # type: ignore[arg-type]
    )

    assert result == ("HELD unattributed factory=petri preservation-ref-missing",)
    assert calls == ["state:unreadable", "state:unattributed"]


def test_listing_and_cancellation_failures_are_reported(tmp_path: Path) -> None:
    calls: list[str] = []
    http = _Http(
        states={
            "run-1": _Result(succeeded=True, payload={"node": "implement", "status": "succeeded"})
        },
        calls=calls,
        cancellation_succeeds=False,
    )
    assert subject.cancel_for_restart(
        repo=tmp_path,
        factory="petri",
        port=_Port(runs=(), http=http, listing_succeeds=False),  # type: ignore[arg-type]
        journal=_journal(tmp_path=tmp_path),
        records=(),
        runner=object(),  # type: ignore[arg-type]
    ) == ("ERROR factory=petri could not list active runs",)
    assert subject.cancel_for_restart(
        repo=tmp_path,
        factory="petri",
        port=_Port(runs=(_run(),), http=http),  # type: ignore[arg-type]
        journal=_journal(tmp_path=tmp_path),
        records=(),
        runner=object(),  # type: ignore[arg-type]
    ) == ("ERROR run-1 factory=petri cancellation-failed",)


def test_green_run_without_its_recorded_base_is_held(tmp_path: Path) -> None:
    calls: list[str] = []
    http = _Http(
        states={
            "run-1": _Result(succeeded=True, payload={"node": "janitor", "status": "succeeded"})
        },
        calls=calls,
    )
    assert subject.cancel_for_restart(
        repo=tmp_path,
        factory="petri",
        port=_Port(runs=(_run(),), http=http),  # type: ignore[arg-type]
        journal=_journal(tmp_path=tmp_path),
        records=(),
        runner=object(),  # type: ignore[arg-type]
    ) == ("HELD run-1 factory=petri preservation-ref-missing",)
    assert calls == ["state:run-1"]


def test_command_refuses_an_unaddressable_factory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        subject,
        "resolve_fabro_factory",
        lambda **_: FactoryTarget(name="petri", server=None, dev_token=None),
    )
    assert (
        subject.run_cancel_for_restart_command(
            args=Namespace(repo=str(tmp_path), factory="petri", journal=None)
        )
        == 2
    )
    assert "has no server url" in capsys.readouterr().err


def test_command_wires_the_resolved_factory_and_reports_its_result(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        subject,
        "resolve_fabro_factory",
        lambda **_: FactoryTarget(
            name="petri", server="https://petri.example", dev_token=None, fabro_bin="fabro-petri"
        ),
    )
    monkeypatch.setattr(
        subject, "cancel_for_restart", lambda **_: ("CANCELLED run-1 factory=petri",)
    )
    assert (
        subject.run_cancel_for_restart_command(
            args=Namespace(repo=str(tmp_path), factory="petri", journal=str(tmp_path / "journal"))
        )
        == 0
    )
    assert capsys.readouterr().out == "CANCELLED run-1 factory=petri\n"


def test_green_janitor_reader_rejects_scalar_and_non_green_records() -> None:
    assert not subject._janitor_succeeded(payload="janitor succeeded")  # noqa: SLF001
    assert not subject._janitor_succeeded(payload={"name": "janitor", "state": "failed"})  # noqa: SLF001
    assert not subject._janitor_succeeded(payload={"node": 4, "status": "succeeded"})  # noqa: SLF001
    assert tuple(subject._mappings(value=[])) == ()  # noqa: SLF001
    subject._record_unpreserved(  # noqa: SLF001
        repo=Path(),
        factory="petri",
        run=subject.RestartRun(run_id="run", work_item_id=None, janitor_succeeded=True),
        journal=JournalFile(path=Path("/tmp/unreachable")),
        failure=PublishFailure(step="ref", detail="ignored"),
    )
