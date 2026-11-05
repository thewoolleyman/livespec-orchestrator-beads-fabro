"""Scenario 306: a planned restart preserves janitor-green committed work."""

from __future__ import annotations

import json
from argparse import Namespace
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands import _dispatcher_cancel_for_restart as subject
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_cancel_for_restart_command as command,
)
from livespec_orchestrator_beads_fabro.commands._config import FactoryTarget
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._fabro_port_http import FabroHttpResult
from livespec_orchestrator_beads_fabro.commands._fabro_port_records import FabroRunSummary

_ITEM = "bd-ib-adcaa6"
_RUN = "01JANITOR"
_BASE = "a" * 40
_COMMIT = "c" * 40


@dataclass(kw_only=True)
class _Command:
    exit_code: int = 0


@dataclass(kw_only=True)
class _Listing:
    runs: tuple[FabroRunSummary, ...]
    command: _Command = field(default_factory=_Command)


@dataclass(kw_only=True)
class _Inspect:
    payload: object


@dataclass(kw_only=True)
class _Api:
    files: FabroHttpResult
    calls: list[str]

    def run_files(self, *, run_id: str, timeout_seconds: float) -> FabroHttpResult:
        _ = (run_id, timeout_seconds)
        return self.files

    def cancel(self, *, run_id: str, timeout_seconds: float) -> FabroHttpResult:
        _ = timeout_seconds
        self.calls.append(run_id)
        return self.files


@dataclass(kw_only=True)
class _Port:
    listing: _Listing
    inspect_payload: object
    api: _Api

    def live_ps(self, *, timeout_seconds: float) -> _Listing:
        _ = timeout_seconds
        return self.listing

    def inspect(self, *, run_id: str, timeout_seconds: float) -> _Inspect:
        _ = (run_id, timeout_seconds)
        return _Inspect(payload=self.inspect_payload)

    def server_api(self) -> _Api:
        return self.api


@dataclass(kw_only=True)
class _Runner:
    argvs: list[list[str]] = field(default_factory=list[list[str]])

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: Mapping[str, str | None] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        _ = (cwd, timeout_seconds, env, stdin)
        self.argvs.append(argv)
        endpoint = next((word for word in argv if word.startswith("/repos/")), "")
        names = {
            f"/repos/{{owner}}/{{repo}}/git/commits/{_BASE}": "b" * 40,
            "/repos/{owner}/{repo}/git/blobs": "d" * 40,
            "/repos/{owner}/{repo}/git/trees": "e" * 40,
            "/repos/{owner}/{repo}/git/commits": _COMMIT,
        }
        return CommandResult(exit_code=0, stdout=names.get(endpoint, "{}") + "\n", stderr="")


def _run() -> FabroRunSummary:
    return FabroRunSummary(
        run_id=_RUN, status_kind="running", goal=None, total_usd_micros=None, work_item_id=_ITEM
    )


def _payload(*, janitor: str, published: str | None = None) -> dict[str, object]:
    stages: dict[str, object] = {"janitor@1": {"state": janitor}}
    if published is not None:
        stages["publish_draft@1"] = {"state": published}
    return {"stages": stages}


def _files(*, succeeded: bool = True) -> FabroHttpResult:
    return FabroHttpResult(
        status=200 if succeeded else 503,
        body=json.dumps({"files": [{"path": "a.py", "content": "x\\n"}]})
        if succeeded
        else "refused",
        error=None,
        payload={"files": [{"path": "a.py", "content": "x\\n"}]} if succeeded else None,
        succeeded=succeeded,
    )


def _cancel(
    *, tmp_path: Path, janitor: str, files_succeed: bool = True
) -> tuple[_Runner, _Api, list[str]]:
    api = _Api(files=_files(succeeded=files_succeed), calls=[])
    runner = _Runner()
    comments: list[str] = []

    def comment_writer(*, item: str, body: str) -> None:
        comments.append(f"{item}:{body}")

    result = subject.cancel_runs(
        port=_Port(
            listing=_Listing(runs=(_run(),)), inspect_payload=_payload(janitor=janitor), api=api
        ),
        runner=runner,
        repo=tmp_path,
        factory="petri",
        records=({"stage": "source-checkout-stage", "work_item_id": _ITEM, "staged_at": _BASE},),
        comment_writer=comment_writer,
    )
    assert result == 0
    return runner, api, comments


def _discard_comment(*, item: str, body: str) -> None:
    _ = (item, body)


def test_green_run_is_published_before_its_restart_cancel(tmp_path: Path) -> None:
    runner, api, comments = _cancel(tmp_path=tmp_path, janitor="succeeded")
    ref_call = next(
        index for index, argv in enumerate(runner.argvs) if any("/git/refs" in arg for arg in argv)
    )
    assert ref_call >= 0
    assert api.calls == [_RUN]
    assert f"refs/livespec/preserved-publish/{_ITEM}/{_COMMIT}" in comments[0]
    assert _RUN in comments[0]
    assert all("push" not in argv for argv in runner.argvs)


def test_not_yet_green_run_is_cancelled_without_publication(tmp_path: Path) -> None:
    runner, api, comments = _cancel(tmp_path=tmp_path, janitor="running")
    assert runner.argvs == []
    assert api.calls == [_RUN]
    assert comments == []


def test_unreadable_green_tree_is_recorded_but_still_cancelled(tmp_path: Path) -> None:
    runner, api, comments = _cancel(tmp_path=tmp_path, janitor="succeeded", files_succeed=False)
    assert runner.argvs == []
    assert api.calls == [_RUN]
    assert "tree was NOT preserved" in comments[0]
    assert "failed step: files-read" in comments[0]


def test_unreadable_live_inventory_refuses_before_any_cancel(tmp_path: Path) -> None:
    api = _Api(files=_files(), calls=[])
    port = _Port(
        listing=_Listing(runs=(), command=_Command(exit_code=1)), inspect_payload={}, api=api
    )
    assert (
        subject.cancel_runs(
            port=port,
            runner=_Runner(),
            repo=tmp_path,
            factory="petri",
            records=(),
            comment_writer=_discard_comment,
        )
        == 1
    )
    assert api.calls == []


def test_published_or_unattributed_live_runs_are_cancelled_without_preservation(
    tmp_path: Path,
) -> None:
    api = _Api(files=_files(), calls=[])
    published = _Port(
        listing=_Listing(runs=(_run(),)),
        inspect_payload=_payload(janitor="succeeded", published="succeeded"),
        api=api,
    )
    assert (
        subject.cancel_runs(
            port=published,
            runner=_Runner(),
            repo=tmp_path,
            factory="petri",
            records=(),
            comment_writer=_discard_comment,
        )
        == 0
    )
    assert api.calls == [_RUN]


def test_missing_base_is_recorded_and_does_not_hold_the_cancel(tmp_path: Path) -> None:
    api = _Api(files=_files(), calls=[])
    comments: list[str] = []

    def comment_writer(*, item: str, body: str) -> None:
        comments.append(f"{item}:{body}")

    assert (
        subject.cancel_runs(
            port=_Port(
                listing=_Listing(runs=(_run(),)),
                inspect_payload=_payload(janitor="succeeded"),
                api=api,
            ),
            runner=_Runner(),
            repo=tmp_path,
            factory="petri",
            records=(),
            comment_writer=comment_writer,
        )
        == 0
    )
    assert api.calls == [_RUN]
    assert "failed step: tree" in comments[0]


def test_command_binds_the_selected_factory_and_uses_its_journal(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    received: dict[str, object] = {}

    def fake_cancel_runs(**kwargs: object) -> int:
        received.update(kwargs)
        return 0

    class _LivePort:
        def __init__(self, **kwargs: object) -> None:
            received["port_init"] = kwargs

    def fake_journal(*, path: Path) -> object:
        _ = path
        return object()

    def fake_records(*, journal: object) -> tuple[object, ...]:
        _ = journal
        return ()

    monkeypatch.setattr(subject, "ShellCommandRunner", lambda: "runner")
    monkeypatch.setattr(subject, "FabroPort", _LivePort)
    monkeypatch.setattr(subject, "JournalFile", fake_journal)
    monkeypatch.setattr(subject, "journal_records", fake_records)
    monkeypatch.setattr(subject, "cancel_runs", fake_cancel_runs)
    assert (
        subject.cancel_for_restart(
            repo=tmp_path,
            factory="petri",
            target=FactoryTarget(name="petri", server="https://petri.example", dev_token=None),
            fabro_bin="fabro",
        )
        == 0
    )
    assert received["factory"] == "petri"
    assert received["records"] == ()
    assert received["port_init"] == {
        "fabro_bin": "fabro",
        "target": subject.FabroTarget(server_url="https://petri.example", dev_token=None),
        "runner": "runner",
        "cwd": tmp_path,
    }


def test_cli_command_resolves_the_named_factory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    received: dict[str, object] = {}
    target = FactoryTarget(name="petri", server="https://petri.example", dev_token=None)

    def resolve_factory(*, cwd: Path, factory: str) -> FactoryTarget:
        received["factory_resolution"] = (cwd, factory)
        return target

    def resolve_binary(*, cwd: Path) -> str:
        received["binary_resolution"] = cwd
        return "fabro"

    def cancel(*, repo: Path, factory: str, target: FactoryTarget, fabro_bin: str) -> int:
        received.update(
            {
                "repo": repo,
                "cancel_factory": factory,
                "target": target,
                "fabro_bin": fabro_bin,
            }
        )
        return 0

    monkeypatch.setattr(command, "resolve_fabro_factory", resolve_factory)
    monkeypatch.setattr(command, "resolve_fabro_bin", resolve_binary)
    monkeypatch.setattr(command, "cancel_for_restart", cancel)
    assert (
        command.run_cancel_for_restart_command(args=Namespace(repo=str(tmp_path), factory="petri"))
        == 0
    )
    assert received["repo"] == tmp_path
    assert received["target"] == target
    assert received["cancel_factory"] == "petri"
    assert received["fabro_bin"] == "fabro"
    assert received["factory_resolution"] == (tmp_path, "petri")
    assert received["binary_resolution"] == tmp_path
