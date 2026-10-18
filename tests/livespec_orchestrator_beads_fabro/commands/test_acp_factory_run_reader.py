"""Production reads of factory-native ACP run evidence."""

from __future__ import annotations

import importlib
import json
import subprocess
from pathlib import Path
from typing import Any, cast

import pytest

_PACKAGE = "livespec_orchestrator_beads_fabro.commands"
_MODULE = "_acp_factory_run_reader"


def _reader_module() -> Any:
    """Import the reader after proving the new module is present."""
    commands = (
        Path(__file__).resolve().parents[3]
        / ".claude-plugin"
        / "scripts"
        / ("livespec_orchestrator_beads_fabro")
        / "commands"
    )
    assert (commands / f"{_MODULE}.py").is_file()
    return importlib.import_module(f"{_PACKAGE}.{_MODULE}")


def _repo(*, tmp_path: Path) -> Path:
    """A repository with one declared remote factory."""
    _ = (tmp_path / ".livespec.jsonc").write_text(
        json.dumps(
            {
                "livespec-orchestrator-beads-fabro": {
                    "dispatcher": {
                        "factories": {"hp": {"server": "https://hp.example.ts.net:32276"}}
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    return tmp_path


def test_reader_queries_the_declared_remote_factory_for_listing_and_inspection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Both reads name the declared server, never Fabro's local default."""
    module = _reader_module()
    calls: list[list[str]] = []

    def fake_run(*args: object, **_kwargs: object) -> object:
        raw_argv = args[0]
        assert isinstance(raw_argv, list)
        argv = cast("list[str]", raw_argv)
        calls.append(argv)
        payload: object
        if argv[1] == "ps":
            payload = [
                {
                    "run_id": "run-1",
                    "status": {"kind": "failed"},
                    "start_time": "2026-10-18T12:00:00Z",
                }
            ]
        else:
            payload = [{"checkpoint": {"node_outcomes": cast("dict[str, object]", {})}}]
        return type("Completed", (), {"returncode": 0, "stdout": json.dumps(payload)})()

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    reader = module.FactoryRunReader(repo=_repo(tmp_path=tmp_path))

    rows = reader.list_runs(factory="hp")
    payload = reader.inspect_payload(factory="hp", run_id="run-1")

    assert [row.run_id for row in rows or ()] == ["run-1"]
    assert payload == [{"checkpoint": {"node_outcomes": {}}}]
    assert calls == [
        ["fabro", "ps", "-a", "--json", "--server", "https://hp.example.ts.net:32276"],
        [
            "fabro",
            "inspect",
            "--json",
            "--server",
            "https://hp.example.ts.net:32276",
            "run-1",
        ],
    ]


def test_reader_returns_none_for_failed_timed_out_or_unparseable_factory_reads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An unreadable factory is never misreported as an empty factory."""
    module = _reader_module()
    reader = module.FactoryRunReader(repo=_repo(tmp_path=tmp_path))

    def failed_run(*_args: object, **_kwargs: object) -> object:
        return type("Completed", (), {"returncode": 1, "stdout": "[]"})()

    monkeypatch.setattr(module.subprocess, "run", failed_run)
    assert reader.list_runs(factory="hp") is None

    def timed_out_run(*_args: object, **_kwargs: object) -> object:
        raise subprocess.TimeoutExpired(cmd="fabro", timeout=60)

    monkeypatch.setattr(module.subprocess, "run", timed_out_run)
    assert reader.inspect_payload(factory="hp", run_id="run-1") is None

    def invalid_json_run(*_args: object, **_kwargs: object) -> object:
        return type("Completed", (), {"returncode": 0, "stdout": "not json"})()

    monkeypatch.setattr(module.subprocess, "run", invalid_json_run)
    assert reader.list_runs(factory="hp") is None

    def unexpected_payload_run(*_args: object, **_kwargs: object) -> object:
        return type("Completed", (), {"returncode": 0, "stdout": "[]"})()

    monkeypatch.setattr(module.subprocess, "run", unexpected_payload_run)
    assert reader.inspect_payload(factory="hp", run_id="run-1") is None
