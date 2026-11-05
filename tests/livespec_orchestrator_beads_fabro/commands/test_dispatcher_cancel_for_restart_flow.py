"""Behaviour of the preservation-before-restart cancellation coordinator."""

from __future__ import annotations

import importlib
import json
from argparse import Namespace
from collections.abc import Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from types import ModuleType

import pytest
from livespec_orchestrator_beads_fabro.commands._config import FactoryTarget
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import (
    JournalFile,
    ShellCommandRunner,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_preserved_tree_publish import (
    STEP_FILES_READ,
    PreservedTree,
    PublishFailure,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port import FabroPort, FabroTarget
from livespec_orchestrator_beads_fabro.commands._fabro_port_http import FabroHttpResult

_GOAL = "Work-item: bd-ib-adcaa6\nTitle: cancel-for-restart"
_BASE_RECORD: dict[str, object] = {
    "stage": "source-checkout-stage",
    "work_item_id": "bd-ib-adcaa6",
    "staged_at": "base",
}
_GREEN: object = {"stages": [{"node": "janitor", "status": "succeeded"}]}
_NOT_GREEN: object = {"node": "implement", "status": "succeeded"}
_MODULE_PATH = (
    Path(__file__).parents[3]
    / ".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/_dispatcher_cancel_for_restart.py"
)


def _subject() -> ModuleType:
    assert _MODULE_PATH.is_file()
    return importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_cancel_for_restart"
    )


@dataclass
class _Runner:
    """A `FabroRunner` whose `fabro ps` answer is fixed."""

    runs: list[dict[str, object]]
    exit_code: int = 0

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: Mapping[str, str | None] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        _ = (argv, cwd, timeout_seconds, env, stdin)
        return CommandResult(
            exit_code=self.exit_code, stdout=json.dumps({"runs": self.runs}), stderr=""
        )


@dataclass
class _Transport:
    """A `FabroHttpTransport` serving per-run state and recording every call."""

    states: dict[str, FabroHttpResult]
    calls: list[str]
    cancellation_succeeds: bool = True

    def send(
        self,
        *,
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes | None,
        timeout_seconds: float,
    ) -> FabroHttpResult:
        _ = (method, headers, body, timeout_seconds)
        run_id = url.split("/runs/")[1].split("/")[0]
        if url.endswith("/state"):
            self.calls.append(f"state:{run_id}")
            return self.states[run_id]
        self.calls.append(f"cancel:{run_id}")
        return _answer(payload={}, succeeded=self.cancellation_succeeds)


def _answer(*, payload: object, succeeded: bool = True) -> FabroHttpResult:
    return FabroHttpResult(
        status=200 if succeeded else 500,
        body=json.dumps(payload),
        error=None,
        payload=None,
        succeeded=succeeded,
    )


def _row(*, run_id: str = "run-1", goal: str = _GOAL) -> dict[str, object]:
    return {"run_id": run_id, "status": "running", "goal": goal}


def _port(
    *, tmp_path: Path, rows: list[dict[str, object]], transport: _Transport, ps_exit_code: int = 0
) -> FabroPort:
    return FabroPort(
        fabro_bin="fabro",
        target=FabroTarget(server_url="https://petri.example"),
        runner=_Runner(runs=rows, exit_code=ps_exit_code),
        cwd=tmp_path,
        http=transport,
    )


def _sweep(
    *,
    tmp_path: Path,
    rows: list[dict[str, object]],
    states: dict[str, FabroHttpResult],
    calls: list[str],
    records: tuple[dict[str, object], ...] = (_BASE_RECORD,),
    cancellation_succeeds: bool = True,
    ps_exit_code: int = 0,
) -> tuple[str, ...]:
    transport = _Transport(states=states, calls=calls, cancellation_succeeds=cancellation_succeeds)
    return _subject().cancel_for_restart(
        repo=tmp_path,
        factory="petri",
        port=_port(tmp_path=tmp_path, rows=rows, transport=transport, ps_exit_code=ps_exit_code),
        journal=JournalFile(path=tmp_path / "journal.jsonl"),
        records=records,
        runner=ShellCommandRunner(),
    )


def _preserved() -> PreservedTree:
    return PreservedTree(
        ref="refs/livespec/preserved-publish/bd-ib-adcaa6/commit",
        commit="commit",
        file_count=1,
        scope="committed",
        source="sandbox",
    )


def test_restart_sweep_is_an_immutable_bundle_of_the_shared_collaborators(
    tmp_path: Path,
) -> None:
    assert hasattr(_subject(), "RestartSweep")
    sweep = _subject().RestartSweep(
        repo=tmp_path,
        factory="petri",
        http=_port(
            tmp_path=tmp_path, rows=[], transport=_Transport(states={}, calls=[])
        ).server_api(),
        journal=JournalFile(path=tmp_path / "journal.jsonl"),
        records=(),
        runner=ShellCommandRunner(),
    )

    moved = replace(sweep, factory="hp")

    assert (sweep.factory, moved.factory) == ("petri", "hp")
    assert moved.records == sweep.records == ()


def test_green_janitor_is_published_before_it_is_cancelled(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[str] = []
    comments: list[str] = []

    def _publish(**kwargs: object) -> PreservedTree:
        calls.append("publish")
        assert kwargs["base_commit"] == "base"
        return _preserved()

    monkeypatch.setattr(_subject(), "publish_run_tree", _publish)
    monkeypatch.setattr(_subject(), "store_config", lambda **_: object())
    monkeypatch.setattr(
        _subject(), "append_work_item_comment", lambda **kwargs: comments.append(kwargs["body"])
    )
    result = _sweep(
        tmp_path=tmp_path,
        rows=[_row()],
        states={"run-1": _answer(payload=_GREEN)},
        calls=calls,
    )

    assert result == ("CANCELLED run-1 factory=petri",)
    assert calls == ["state:run-1", "publish", "cancel:run-1"]
    journal = (tmp_path / "journal.jsonl").read_text(encoding="utf-8")
    assert "refs/livespec/preserved-publish/bd-ib-adcaa6/commit" in journal
    assert "livespec-preserved-tree" in comments[0]
    assert "run id: run-1" in comments[0]
    assert "factory: petri" in comments[0]
    assert "commit id: commit" in comments[0]


@pytest.mark.parametrize(
    "payload",
    [
        _NOT_GREEN,
        "janitor succeeded",
        {"name": "janitor", "state": "failed"},
        {"node": 4, "status": "succeeded"},
        [],
    ],
)
def test_run_whose_janitor_has_not_succeeded_is_cancelled_without_a_preservation_attempt(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, payload: object
) -> None:
    calls: list[str] = []
    monkeypatch.setattr(_subject(), "publish_run_tree", lambda **_: pytest.fail("must not publish"))

    result = _sweep(
        tmp_path=tmp_path,
        rows=[_row()],
        states={"run-1": _answer(payload=payload)},
        calls=calls,
        records=(),
    )

    assert result == ("CANCELLED run-1 factory=petri",)
    assert calls == ["state:run-1", "cancel:run-1"]


@pytest.mark.parametrize(
    "payload",
    [
        {"node": "janitor", "state": "green"},
        {"name": "janitor", "status": "success"},
        {"stage": "janitor", "outcome": "succeeded"},
    ],
)
def test_every_observed_green_janitor_shape_is_published_first(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, payload: object
) -> None:
    calls: list[str] = []
    monkeypatch.setattr(_subject(), "publish_run_tree", lambda **_: _preserved())
    monkeypatch.setattr(_subject(), "store_config", lambda **_: object())
    monkeypatch.setattr(_subject(), "append_work_item_comment", lambda **_: None)

    result = _sweep(
        tmp_path=tmp_path,
        rows=[_row()],
        states={"run-1": _answer(payload=payload)},
        calls=calls,
    )

    assert result == ("CANCELLED run-1 factory=petri",)


def test_unreadable_green_tree_is_recorded_then_cancelled(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[str] = []
    comments: list[str] = []
    monkeypatch.setattr(
        _subject(),
        "publish_run_tree",
        lambda **_: PublishFailure(step=STEP_FILES_READ, detail="factory did not serve files"),
    )
    monkeypatch.setattr(_subject(), "store_config", lambda **_: object())
    monkeypatch.setattr(
        _subject(), "append_work_item_comment", lambda **kwargs: comments.append(kwargs["body"])
    )

    result = _sweep(
        tmp_path=tmp_path,
        rows=[_row()],
        states={"run-1": _answer(payload={"node": "janitor", "state": "green"})},
        calls=calls,
    )

    assert result == ("CANCELLED run-1 factory=petri",)
    assert "livespec-preserved-tree" in comments[0]
    assert "failed step: files-read" in comments[0]
    assert calls == ["state:run-1", "cancel:run-1"]
    assert "restart-preserved-tree-unpreserved" in (tmp_path / "journal.jsonl").read_text(
        encoding="utf-8"
    )


def test_forge_failure_keeps_green_run_alive(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[str] = []
    monkeypatch.setattr(
        _subject(),
        "publish_run_tree",
        lambda **_: PublishFailure(step="ref", detail="ref rejected"),
    )
    monkeypatch.setattr(_subject(), "store_config", lambda **_: object())
    monkeypatch.setattr(_subject(), "append_work_item_comment", lambda **_: None)

    result = _sweep(
        tmp_path=tmp_path,
        rows=[_row()],
        states={"run-1": _answer(payload={"stage": "janitor", "outcome": "success"})},
        calls=calls,
    )

    assert result == ("HELD run-1 factory=petri preservation-ref-missing",)
    assert calls == ["state:run-1"]


def test_state_unavailable_and_unattributed_green_runs_are_not_cancelled(tmp_path: Path) -> None:
    calls: list[str] = []
    result = _sweep(
        tmp_path=tmp_path,
        rows=[_row(run_id="unreadable"), _row(run_id="unattributed", goal="no work item here")],
        states={
            "unreadable": _answer(payload={}, succeeded=False),
            "unattributed": _answer(payload={"node": "janitor", "status": "succeeded"}),
        },
        calls=calls,
        records=(),
    )

    assert result == ("HELD unattributed factory=petri preservation-ref-missing",)
    assert calls == ["state:unreadable", "state:unattributed"]


def test_listing_failure_is_reported(tmp_path: Path) -> None:
    calls: list[str] = []

    assert _sweep(
        tmp_path=tmp_path, rows=[], states={}, calls=calls, records=(), ps_exit_code=1
    ) == ("ERROR factory=petri could not list active runs",)
    assert calls == []


def test_cancellation_failure_is_reported(tmp_path: Path) -> None:
    calls: list[str] = []

    assert _sweep(
        tmp_path=tmp_path,
        rows=[_row()],
        states={"run-1": _answer(payload=_NOT_GREEN)},
        calls=calls,
        records=(),
        cancellation_succeeds=False,
    ) == ("ERROR run-1 factory=petri cancellation-failed",)


def test_green_run_without_its_recorded_base_is_held(tmp_path: Path) -> None:
    calls: list[str] = []

    assert _sweep(
        tmp_path=tmp_path,
        rows=[_row()],
        states={"run-1": _answer(payload={"node": "janitor", "status": "succeeded"})},
        calls=calls,
        records=(),
    ) == ("HELD run-1 factory=petri preservation-ref-missing",)
    assert calls == ["state:run-1"]


def test_command_refuses_an_unaddressable_factory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        _subject(),
        "resolve_fabro_factory",
        lambda **_: FactoryTarget(name="petri", server=None, dev_token=None),
    )
    assert (
        _subject().run_cancel_for_restart_command(
            args=Namespace(repo=str(tmp_path), factory="petri", journal=None)
        )
        == 2
    )
    assert "has no server url" in capsys.readouterr().err


def test_command_wires_the_resolved_factory_and_reports_its_result(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        _subject(),
        "resolve_fabro_factory",
        lambda **_: FactoryTarget(
            name="petri", server="https://petri.example", dev_token=None, fabro_bin="fabro-petri"
        ),
    )
    monkeypatch.setattr(
        _subject(), "cancel_for_restart", lambda **_: ("CANCELLED run-1 factory=petri",)
    )
    assert (
        _subject().run_cancel_for_restart_command(
            args=Namespace(repo=str(tmp_path), factory="petri", journal=str(tmp_path / "journal"))
        )
        == 0
    )
    assert capsys.readouterr().out == "CANCELLED run-1 factory=petri\n"
