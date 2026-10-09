"""The credential-bearing Fabro call stays inside the engine facade.

The dispatch sink owns the unlinked input file, journaling, and refusal policy;
`FabroPort` owns the lower-level fact that the factory is reached with
`fabro secret set`. The value therefore travels through standard input and
never appears in argv or an inherited environment.
"""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._fabro_port import FabroPort, FabroTarget

_FABRO_BIN = "/opt/fabro-candidate/bin/fabro"
_SERVER = "https://candidate.example.invalid:32278"
_SECRET_NAME = "LIVESPEC_DISPATCH_GITHUB_TOKEN"
_VALUE = "facade-boundary-placeholder-0123456789"


@dataclass(kw_only=True)
class _RecordingRunner:
    """Record the complete child-process surface and consume its stdin."""

    argvs: list[list[str]] = field(default_factory=list)
    envs: list[dict[str, str] | None] = field(default_factory=list)
    stdin_texts: list[str] = field(default_factory=list)

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        _ = cwd, timeout_seconds
        self.argvs.append(list(argv))
        self.envs.append(env)
        self.stdin_texts.append("" if stdin is None else os.read(stdin, 4096).decode("utf-8"))
        return CommandResult(exit_code=0, stdout="stored", stderr="")


def test_secret_store_is_a_fabro_port_call_with_no_value_bearing_surface() -> None:
    """The facade owns the invocation and stdin is its sole value channel."""
    runner = _RecordingRunner()

    for server_url in (_SERVER, None):
        port = FabroPort(
            fabro_bin=_FABRO_BIN,
            target=FabroTarget(server_url=server_url),
            runner=runner,
            cwd=Path("/workspace/repo"),
        )
        with tempfile.TemporaryFile() as handle:
            _ = handle.write(_VALUE.encode("utf-8"))
            _ = handle.seek(0)
            result = port.secret_set(
                secret_name=_SECRET_NAME,
                stdin=handle.fileno(),
                timeout_seconds=120.0,
            )
        assert result.exit_code == 0

    assert runner.stdin_texts == [_VALUE, _VALUE]
    assert runner.envs == [None, None]
    assert runner.argvs == [
        [
            _FABRO_BIN,
            "secret",
            "set",
            _SECRET_NAME,
            "--value-stdin",
            "--server",
            _SERVER,
        ],
        [_FABRO_BIN, "secret", "set", _SECRET_NAME, "--value-stdin"],
    ]
    assert all(_VALUE not in " ".join(argv) for argv in runner.argvs)
