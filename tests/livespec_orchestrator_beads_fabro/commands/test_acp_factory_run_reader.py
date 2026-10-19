"""The production factory-record reader used by ACP admission."""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult

_REPO_ROOT = Path(__file__).resolve().parents[3]
_COMMANDS = (
    _REPO_ROOT / ".claude-plugin" / "scripts" / "livespec_orchestrator_beads_fabro" / "commands"
)
_PACKAGE = "livespec_orchestrator_beads_fabro.commands"
_MODULE = "_acp_factory_run_reader"
_SERVER = "https://hp.example.ts.net:32276"


class _Runner:
    """Scripted Fabro-port runner that retains the argv each read reached."""

    def __init__(self, *, results: list[CommandResult]) -> None:
        self.results = results
        self.calls: list[dict[str, object]] = []

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        self.calls.append(
            {
                "argv": argv,
                "cwd": cwd,
                "timeout_seconds": timeout_seconds,
                "env": env,
                "stdin": stdin,
            }
        )
        return self.results.pop(0)


def _module() -> Any:
    path = _COMMANDS / f"{_MODULE}.py"
    assert path.is_file(), f"{_MODULE}.py is not implemented yet"
    return importlib.import_module(f"{_PACKAGE}.{_MODULE}")


def _repo(*, tmp_path: Path, server: str | None = _SERVER) -> Path:
    entry: dict[str, object] = {"bin": "/factory/fabro"}
    if server is not None:
        entry["server"] = server
    (tmp_path / ".livespec.jsonc").write_text(
        json.dumps(
            {"livespec-orchestrator-beads-fabro": {"dispatcher": {"factories": {"hp": entry}}}}
        ),
        encoding="utf-8",
    )
    return tmp_path


def _result(*, exit_code: int = 0, stdout: str = "") -> CommandResult:
    return CommandResult(exit_code=exit_code, stdout=stdout, stderr="")


def test_factory_reader_uses_the_port_for_server_qualified_reads_and_rejects_unreadable_output(
    tmp_path: Path,
) -> None:
    """Both reads use their declared factory, never a host-default Fabro server."""
    module = _module()
    runner = _Runner(
        results=[
            _result(
                stdout=json.dumps(
                    [
                        {
                            "run_id": "01MFACTORY",
                            "status": {"kind": "failed"},
                            "labels": {"livespec.repository": "another-repository"},
                        }
                    ]
                )
            ),
            _result(stdout=json.dumps([{"run_id": "01MFACTORY", "status": {"kind": "failed"}}])),
            _result(exit_code=124),
            _result(stdout="not json"),
            _result(stdout=json.dumps({"wrong": "ps shape"})),
            _result(stdout=json.dumps(["wrong inspect shape"])),
        ]
    )
    reader = module.FactoryRunReader(repo=_repo(tmp_path=tmp_path), runner=runner)

    runs = reader.list_runs(factory="hp")

    assert runs is not None
    assert [run.run_id for run in runs] == ["01MFACTORY"]
    assert reader.inspect_payload(factory="hp", run_id="01MFACTORY") == [
        {"run_id": "01MFACTORY", "status": {"kind": "failed"}}
    ]
    assert reader.list_runs(factory="hp") is None
    assert reader.list_runs(factory="hp") is None
    assert reader.list_runs(factory="hp") is None
    assert reader.inspect_payload(factory="hp", run_id="01MFACTORY") is None
    assert [call["argv"] for call in runner.calls] == [
        ["/factory/fabro", "ps", "-a", "--json", "--server", _SERVER],
        ["/factory/fabro", "inspect", "01MFACTORY", "--json", "--server", _SERVER],
        ["/factory/fabro", "ps", "-a", "--json", "--server", _SERVER],
        ["/factory/fabro", "ps", "-a", "--json", "--server", _SERVER],
        ["/factory/fabro", "ps", "-a", "--json", "--server", _SERVER],
        ["/factory/fabro", "inspect", "01MFACTORY", "--json", "--server", _SERVER],
    ]


def test_factory_reader_reads_the_scheduler_ceiling_from_its_declared_factory(
    tmp_path: Path,
) -> None:
    """The ceiling overflow selection compares a run count against, or `None`.

    `None` is asserted for BOTH ways the read can answer nothing — a non-zero
    exit and a payload naming no ceiling — because the two reach the caller
    identically and the clause turns either into "this candidate has no free
    slot". A reader that returned a number for one of them would report a
    saturated factory as having room.
    """
    module = _module()
    runner = _Runner(
        results=[
            _result(stdout=json.dumps({"server": {"scheduler": {"max_concurrent_runs": 10}}})),
            _result(exit_code=124),
            _result(stdout=json.dumps({"server": {"listen": "127.0.0.1:32276"}})),
        ]
    )
    reader = module.FactoryRunReader(repo=_repo(tmp_path=tmp_path), runner=runner)

    assert reader.scheduler_max_concurrent_runs(factory="hp") == 10
    assert reader.scheduler_max_concurrent_runs(factory="hp") is None
    assert reader.scheduler_max_concurrent_runs(factory="hp") is None
    assert [call["argv"] for call in runner.calls] == [
        ["/factory/fabro", "settings", "--json", "--server", _SERVER],
        ["/factory/fabro", "settings", "--json", "--server", _SERVER],
        ["/factory/fabro", "settings", "--json", "--server", _SERVER],
    ]


def test_factory_reader_refuses_a_factory_without_a_declared_server(tmp_path: Path) -> None:
    """A missing target cannot fall through to Fabro's local default server."""
    module = _module()
    runner = _Runner(results=[])
    reader = module.FactoryRunReader(repo=_repo(tmp_path=tmp_path, server=None), runner=runner)

    assert reader.list_runs(factory="hp") is None
    assert reader.inspect_payload(factory="hp", run_id="01MFACTORY") is None
    assert reader.scheduler_max_concurrent_runs(factory="hp") is None
    assert runner.calls == []
