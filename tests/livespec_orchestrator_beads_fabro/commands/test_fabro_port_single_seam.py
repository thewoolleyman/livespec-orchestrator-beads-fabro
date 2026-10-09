"""The Fabro facade is the SINGLE seam between the Dispatcher and the engine.

The Enemy Unit Test suite exercises the engine through `FabroPort`, so a green
pinned-versus-candidate comparison is evidence about the Dispatcher only to the
extent the Dispatcher itself reaches Fabro through that same facade. Three call
sites reached past it, and each one did so because the facade carried no verb
for what it needed: both preserve-by-reference modules built their own
`fabro dump` argv, and the ACP capability reader sent its own `/system/info`
request through the transport function directly.

So this test asserts BOTH halves, because either alone is satisfiable without
the other. The verb must LIVE on the facade -- asserted against the argv and
the url the facade itself produces -- and every caller must GO THROUGH it.

The second half is asserted by REPLACING the facade method and watching which
callers stop reaching the engine, never by reading their imports. A caller that
kept the import and re-inlined the argv beside it would satisfy an
import-shaped assertion exactly as a routed one does, and that caller is
precisely the regression this test and `dev-tooling/checks/fabro_port_seam.py`
exist to make impossible.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult

_PACKAGE = "livespec_orchestrator_beads_fabro.commands"
_COMMANDS_DIR = Path(".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands")
_FABRO_BIN = "/home/factory/.fabro/bin/fabro"
_SERVER = "https://hp-xubuntu.perch-rudd.ts.net:32276"
_RUN_ID = "01M0RUN"
_CAPABILITY_BODY = '{"capabilities": []}'


def _module(*, name: str) -> ModuleType:
    assert (_COMMANDS_DIR / f"{name}.py").is_file()
    return importlib.import_module(f"{_PACKAGE}.{name}")


@dataclass(kw_only=True)
class _Runner:
    """Records each argv the facade hands the subprocess seam, exporting nothing."""

    calls: list[list[str]] = field(default_factory=list)

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        _ = (cwd, timeout_seconds, env, stdin)
        self.calls.append(argv)
        return CommandResult(exit_code=0, stdout="", stderr="")


@dataclass(kw_only=True)
class _Transport:
    """Records each exchange the facade sends, answering with an empty capability list."""

    urls: list[str] = field(default_factory=list)

    def send(
        self,
        *,
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes | None,
        timeout_seconds: float,
    ) -> Any:
        _ = (headers, body, timeout_seconds)
        self.urls.append(f"{method} {url}")
        http = _module(name="_fabro_port_http")
        return http.FabroHttpResult(
            status=200,
            body=_CAPABILITY_BODY,
            error=None,
            payload=None,
            succeeded=True,
        )


def _recording_dump(*, routed: list[str]) -> Any:
    def dump(self, *, run_id: str, output_dir: Path, timeout_seconds: float) -> Any:
        _ = (self, run_id, output_dir, timeout_seconds)
        routed.append("dump")
        types = _module(name="_fabro_port_types")
        return types.FabroCommandResult(command=CommandResult(exit_code=0, stdout="", stderr=""))

    return dump


def _recording_system_info(*, routed: list[str]) -> Any:
    def system_info(self, *, timeout_seconds: float) -> Any:
        _ = (self, timeout_seconds)
        routed.append("system_info")
        http = _module(name="_fabro_port_http")
        return http.FabroHttpResult(
            status=200,
            body=_CAPABILITY_BODY,
            error=None,
            payload=None,
            succeeded=True,
        )

    return system_info


def _undigested_pointer_body() -> str:
    """A pointer with no recorded digest, so the reader needs no re-exported bytes."""
    body = _module(name="_dispatcher_preserve_reference_body")
    text, _ = body.dump_failed_body(
        run_id=_RUN_ID,
        server_url=_SERVER,
        command=CommandResult(exit_code=2, stdout="", stderr="run storage not found"),
        fabro_bin=_FABRO_BIN,
    )
    return text


def test_dump_and_system_info_live_on_the_facade_and_every_caller_routes_through_them(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    port_module = _module(name="_fabro_port")
    http_module = _module(name="_fabro_port_http")

    # Asserted before any attribute access, so a facade still missing the verb
    # fails HERE on a genuine assertion rather than on an AttributeError that
    # would prove only unimportability.
    assert "dump" in vars(port_module.FabroPort)
    assert "system_info" in vars(http_module.FabroHttpPort)

    export_dir = tmp_path / "export"
    runner = _Runner()
    _ = port_module.FabroPort(
        fabro_bin=_FABRO_BIN,
        target=port_module.FabroTarget(server_url=_SERVER),
        runner=runner,
        cwd=tmp_path,
    ).dump(run_id=_RUN_ID, output_dir=export_dir, timeout_seconds=1.0)
    assert runner.calls == [
        [_FABRO_BIN, "dump", _RUN_ID, "--server", _SERVER, "-o", str(export_dir)]
    ]

    transport = _Transport()
    _ = http_module.FabroHttpPort(
        target=port_module.FabroTarget(server_url=_SERVER),
        transport=transport,
    ).system_info(timeout_seconds=1.0)
    assert transport.urls == [f"GET {_SERVER}{http_module.SYSTEM_INFO_PATH}"]

    routed: list[str] = []
    monkeypatch.setattr(port_module.FabroPort, "dump", _recording_dump(routed=routed))
    monkeypatch.setattr(
        http_module.FabroHttpPort, "system_info", _recording_system_info(routed=routed)
    )

    preserve = _module(name="_dispatcher_preserve_reference")
    _ = preserve.pointer_record_for_run(
        fabro_bin=_FABRO_BIN,
        repo=tmp_path,
        item_id="bd-ib-seam",
        run_id=_RUN_ID,
        server_url=_SERVER,
        command_runner=_Runner(),
    )
    checker = _module(name="_dispatcher_preserve_reference_check")
    pointer = checker.parse_preserved_pointer(body=_undigested_pointer_body())
    assert pointer is not None
    _ = checker.check_preserved_pointer(
        pointer=pointer,
        repo=tmp_path,
        fabro_bin=_FABRO_BIN,
        runner=_Runner(),
    )
    capabilities = _module(name="_acp_factory_capabilities")
    config = _module(name="_config")
    _ = capabilities.factory_capability_reader(
        factory=config.FactoryTarget(name="hp", server=_SERVER, dev_token=None),
        transport=_Transport(),
    )()

    assert routed == ["dump", "dump", "system_info"]
