"""The factory-addressed Dispatcher run reader."""

from __future__ import annotations

import argparse
import importlib
import json
from io import StringIO
from pathlib import Path
from typing import Any

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult

_REPO_ROOT = Path(__file__).resolve().parents[3]
_COMMANDS = (
    _REPO_ROOT / ".claude-plugin" / "scripts" / "livespec_orchestrator_beads_fabro" / "commands"
)
_PACKAGE = "livespec_orchestrator_beads_fabro.commands"
_MODULE = "_dispatcher_factory_inspect"
_SERVER = "https://gmktec.example.ts.net:32276"


class _Runner:
    """A Fabro runner that records which client and target a read reaches."""

    def __init__(self, *, results: list[CommandResult]) -> None:
        self.calls: list[dict[str, object]] = []
        self.results = results

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


def _repo(*, tmp_path: Path) -> Path:
    (tmp_path / ".livespec.jsonc").write_text(
        json.dumps(
            {
                "livespec-orchestrator-beads-fabro": {
                    "dispatcher": {
                        "factories": {"petri": {"bin": "/carrier/petri-fabro", "server": _SERVER}}
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    return tmp_path


def test_diagnostic_note_requires_a_fresh_invocation_log_before_export() -> None:
    """Sequential captures cannot mistake an earlier inspect for a dump."""
    diagnosis = (_REPO_ROOT / ".ai" / "fabro-dispatch-diagnosis.md").read_text(encoding="utf-8")

    assert "Start every export capture with a fresh invocation log" in diagnosis


def test_factory_inspect_reads_a_run_with_the_factory_client_and_server(tmp_path: Path) -> None:
    """A Petri run never falls through to the host PATH client or its server."""
    module = _module()
    repo = _repo(tmp_path=tmp_path)
    runner = _Runner(
        results=[CommandResult(exit_code=0, stdout='{"sandbox_type":"kubernetes"}\n', stderr="")]
    )
    stdout = StringIO()
    stderr = StringIO()

    status = module.run_factory_inspect_command(
        args=argparse.Namespace(
            factory="petri", run_id="01MFACTORY", output_dir=None, repo=str(repo)
        ),
        runner=runner,
        stdout=stdout,
        stderr=stderr,
    )

    assert status == 0
    assert stdout.getvalue() == '{"sandbox_type":"kubernetes"}\n'
    assert stderr.getvalue() == ""
    assert [call["argv"] for call in runner.calls] == [
        [
            "/carrier/petri-fabro",
            "inspect",
            "01MFACTORY",
            "--json",
            "--server",
            _SERVER,
        ]
    ]


def test_factory_inspect_exports_with_the_selected_factory_client(tmp_path: Path) -> None:
    """An export uses the same selected client and server as inspection."""
    module = _module()
    repo = _repo(tmp_path=tmp_path)
    export_dir = tmp_path / "export"
    parser = argparse.ArgumentParser()
    module.add_factory_inspect_arguments(parser=parser)
    args = parser.parse_args(
        ["--factory", "petri", "01MFACTORY", "-o", str(export_dir), "--repo", str(repo)]
    )
    dump_runner = _Runner(results=[CommandResult(exit_code=0, stdout="exported\n", stderr="")])
    dump_stdout = StringIO()

    assert (
        module.run_factory_inspect_command(
            args=args, runner=dump_runner, stdout=dump_stdout, stderr=StringIO()
        )
        == 0
    )
    assert dump_stdout.getvalue() == "exported\n"
    assert [call["argv"] for call in dump_runner.calls] == [
        ["/carrier/petri-fabro", "dump", "01MFACTORY", "--server", _SERVER, "-o", str(export_dir)]
    ]


def test_factory_inspect_refuses_missing_bin_and_unresolved_registry(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """A reader refuses rather than falling back to a PATH client or local server."""
    module = _module()
    no_bin = tmp_path / "no-bin"
    no_bin.mkdir()
    (no_bin / ".livespec.jsonc").write_text(
        json.dumps(
            {
                "livespec-orchestrator-beads-fabro": {
                    "dispatcher": {"factories": {"petri": {"server": _SERVER}}}
                }
            }
        ),
        encoding="utf-8",
    )
    refusal_runner = _Runner(results=[])
    refusal_stderr = StringIO()

    assert (
        module.run_factory_inspect_command(
            args=argparse.Namespace(
                factory="petri", run_id="01MFACTORY", output_dir=None, repo=str(no_bin)
            ),
            runner=refusal_runner,
            stdout=StringIO(),
            stderr=refusal_stderr,
        )
        == module.FACTORY_INSPECT_REFUSAL_EXIT
    )
    assert "dispatcher.factories.petri.bin" in refusal_stderr.getvalue()
    assert refusal_runner.calls == []

    unresolved = tmp_path / "unresolved"
    unresolved.mkdir()
    registry = unresolved / "factories.json"
    monkeypatch.setenv("LIVESPEC_FABRO_FACTORY_REGISTRY", str(registry))
    (unresolved / ".livespec.jsonc").write_text(
        json.dumps(
            {
                "livespec-orchestrator-beads-fabro": {
                    "dispatcher": {
                        "factories": {"petri": {"bin": "/carrier/petri-fabro", "registry": True}}
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    unresolved_runner = _Runner(results=[])
    unresolved_stderr = StringIO()

    assert (
        module.run_factory_inspect_command(
            args=argparse.Namespace(
                factory="petri", run_id="01MFACTORY", output_dir=None, repo=str(unresolved)
            ),
            runner=unresolved_runner,
            stdout=StringIO(),
            stderr=unresolved_stderr,
        )
        == module.FACTORY_INSPECT_REFUSAL_EXIT
    )
    assert "petri" in unresolved_stderr.getvalue()
    assert str(registry) in unresolved_stderr.getvalue()
    assert unresolved_runner.calls == []


def test_factory_inspect_requires_a_committed_bin_and_server(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """A registry address never lets the registry replace required committed settings."""
    module = _module()
    registry_backed = tmp_path / "registry-backed"
    registry_backed.mkdir()
    registry = registry_backed / "factories.json"
    registry.write_text(
        json.dumps({"petri": {"bin": "/registry/petri-fabro", "server": _SERVER}}),
        encoding="utf-8",
    )
    monkeypatch.setenv("LIVESPEC_FABRO_FACTORY_REGISTRY", str(registry))
    (registry_backed / ".livespec.jsonc").write_text(
        json.dumps(
            {
                "livespec-orchestrator-beads-fabro": {
                    "dispatcher": {"factories": {"petri": {"registry": True}}}
                }
            }
        ),
        encoding="utf-8",
    )
    registry_runner = _Runner(results=[CommandResult(exit_code=0, stdout="record\n", stderr="")])
    registry_stderr = StringIO()

    assert (
        module.run_factory_inspect_command(
            args=argparse.Namespace(
                factory="petri",
                run_id="01MFACTORY",
                output_dir=None,
                repo=str(registry_backed),
            ),
            runner=registry_runner,
            stdout=StringIO(),
            stderr=registry_stderr,
        )
        == module.FACTORY_INSPECT_REFUSAL_EXIT
    )
    assert "dispatcher.factories.petri.bin" in registry_stderr.getvalue()
    assert registry_runner.calls == []

    serverless = tmp_path / "serverless"
    serverless.mkdir()
    (serverless / ".livespec.jsonc").write_text(
        json.dumps(
            {
                "livespec-orchestrator-beads-fabro": {
                    "dispatcher": {"factories": {"petri": {"bin": "/carrier/petri-fabro"}}}
                }
            }
        ),
        encoding="utf-8",
    )
    serverless_runner = _Runner(results=[])
    serverless_stderr = StringIO()

    assert (
        module.run_factory_inspect_command(
            args=argparse.Namespace(
                factory="petri", run_id="01MFACTORY", output_dir=None, repo=str(serverless)
            ),
            runner=serverless_runner,
            stdout=StringIO(),
            stderr=serverless_stderr,
        )
        == module.FACTORY_INSPECT_REFUSAL_EXIT
    )
    assert "no resolved server address" in serverless_stderr.getvalue()
    assert serverless_runner.calls == []


def test_factory_inspect_relays_the_selected_clients_failure(tmp_path: Path) -> None:
    """The selected client error remains visible to the reader's caller."""
    module = _module()
    repo = _repo(tmp_path=tmp_path)
    failed_runner = _Runner(
        results=[CommandResult(exit_code=23, stdout="", stderr="unknown variant `kubernetes`\n")]
    )
    failed_stderr = StringIO()

    assert (
        module.run_factory_inspect_command(
            args=argparse.Namespace(
                factory="petri", run_id="01MFACTORY", output_dir=None, repo=str(repo)
            ),
            runner=failed_runner,
            stdout=StringIO(),
            stderr=failed_stderr,
        )
        == 23
    )
    assert failed_stderr.getvalue() == "unknown variant `kubernetes`\n"


def test_factory_inspect_gives_an_export_a_longer_timeout_than_an_inspect_read(
    tmp_path: Path,
) -> None:
    """A full run export is far slower than one inspect read, so it gets its own bound."""
    module = _module()
    repo = _repo(tmp_path=tmp_path)
    inspect_runner = _Runner(results=[CommandResult(exit_code=0, stdout="record\n", stderr="")])
    dump_runner = _Runner(results=[CommandResult(exit_code=0, stdout="exported\n", stderr="")])

    _ = module.run_factory_inspect_command(
        args=argparse.Namespace(
            factory="petri", run_id="01MFACTORY", output_dir=None, repo=str(repo)
        ),
        runner=inspect_runner,
        stdout=StringIO(),
        stderr=StringIO(),
    )
    _ = module.run_factory_inspect_command(
        args=argparse.Namespace(
            factory="petri",
            run_id="01MFACTORY",
            output_dir=tmp_path / "export",
            repo=str(repo),
        ),
        runner=dump_runner,
        stdout=StringIO(),
        stderr=StringIO(),
    )

    assert inspect_runner.calls[0]["timeout_seconds"] == 60.0
    assert dump_runner.calls[0]["timeout_seconds"] == 300.0
