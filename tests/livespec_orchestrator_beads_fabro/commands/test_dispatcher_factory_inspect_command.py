"""The factory-addressed run reader exposed by ``dispatcher inspect``."""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import ClassVar

import pytest
from livespec_orchestrator_beads_fabro.commands._config import FactoryTarget

_COMMAND_MODULE = "livespec_orchestrator_beads_fabro.commands._dispatcher_factory_inspect_command"
_COMMAND_PATH = Path(
    ".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/"
    "_dispatcher_factory_inspect_command.py"
)


@dataclass(frozen=True, kw_only=True)
class _PortCall:
    """The target and run one fake reader was asked to inspect."""

    fabro_bin: str
    server_url: str | None
    run_id: str


class _Port:
    """A FabroPort replacement that records the command-facing contract."""

    calls: ClassVar[list[_PortCall]] = []
    exports: ClassVar[list[tuple[str, Path]]] = []

    def __init__(self, *, fabro_bin: str, target: object, runner: object, cwd: Path) -> None:
        _ = (runner, cwd)
        self._fabro_bin = fabro_bin
        self._server_url = getattr(target, "server_url", None)

    def inspect(self, *, run_id: str, timeout_seconds: float) -> SimpleNamespace:
        _ = timeout_seconds
        self.calls.append(
            _PortCall(
                fabro_bin=self._fabro_bin,
                server_url=self._server_url,
                run_id=run_id,
            )
        )
        return SimpleNamespace(
            command=SimpleNamespace(exit_code=0, stdout='{"run_id": "01PETRI"}\n', stderr="")
        )

    def dump(self, *, output_dir: Path, run_id: str, timeout_seconds: float) -> SimpleNamespace:
        _ = timeout_seconds
        self.exports.append((run_id, output_dir))
        return SimpleNamespace(command=SimpleNamespace(exit_code=0, stdout="", stderr=""))


def test_inspect_reads_a_named_run_through_its_factory_client_and_server(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The factory's client and registry-resolved address are one reader target."""
    assert _COMMAND_PATH.is_file()
    command = importlib.import_module(_COMMAND_MODULE)
    dispatcher = importlib.import_module("livespec_orchestrator_beads_fabro.commands.dispatcher")
    target = FactoryTarget(
        name="petri",
        server="https://gmktec.example",
        dev_token=None,
        fabro_bin="/opt/fabro-petri",
    )

    def _resolve(*, cwd: Path, factory: str | None = None) -> FactoryTarget:
        assert cwd == Path.cwd()
        assert factory == "petri"
        return target

    _Port.calls = []
    monkeypatch.setattr(command, "resolve_fabro_factory", _resolve)
    monkeypatch.setattr(command, "FabroPort", _Port)

    exit_code = dispatcher.main(argv=["inspect", "--factory", "petri", "01PETRI"])

    assert exit_code == 0
    assert capsys.readouterr().out == '{"run_id": "01PETRI"}\n'
    assert _Port.calls == [
        _PortCall(
            fabro_bin="/opt/fabro-petri",
            server_url="https://gmktec.example",
            run_id="01PETRI",
        )
    ]


def test_inspect_exports_a_named_run_through_its_factory_client_and_server(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The output flag delegates to the same factory-targeted reader."""
    command = importlib.import_module(_COMMAND_MODULE)
    dispatcher = importlib.import_module("livespec_orchestrator_beads_fabro.commands.dispatcher")
    target = FactoryTarget(
        name="petri",
        server="https://gmktec.example",
        dev_token=None,
        fabro_bin="/opt/fabro-petri",
    )
    output_dir = Path("exported-run")

    def _resolve(*, cwd: Path, factory: str | None = None) -> FactoryTarget:
        assert cwd == Path.cwd()
        assert factory == "petri"
        return target

    _Port.exports = []
    monkeypatch.setattr(command, "resolve_fabro_factory", _resolve)
    monkeypatch.setattr(command, "FabroPort", _Port)

    exit_code = dispatcher.main(
        argv=["inspect", "--factory", "petri", "01PETRI", "-o", str(output_dir)]
    )

    assert exit_code == 0
    assert _Port.exports == [("01PETRI", output_dir)]
