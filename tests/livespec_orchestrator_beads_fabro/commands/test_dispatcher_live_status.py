"""The watchdog's factory-status reader is live-only and scoped to its port."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._fabro_port import FabroPort, FabroTarget


@dataclass(kw_only=True)
class _Runner:
    calls: list[list[str]] = field(default_factory=list)

    def run(self, *, argv: list[str], cwd: Path, timeout_seconds: float) -> CommandResult:
        _ = (cwd, timeout_seconds)
        self.calls.append(argv)
        return CommandResult(exit_code=0, stdout="[]", stderr="")


def test_the_watchdog_can_read_only_a_factorys_live_run_statuses(tmp_path: Path) -> None:
    """The live status route omits historical runs without changing full readers."""
    runner = _Runner()
    port = FabroPort(
        fabro_bin="fabro",
        target=FabroTarget(server_url="https://factory.example.test"),
        runner=runner,
        cwd=tmp_path,
    )

    assert "live_ps" in FabroPort.__dict__
    _ = port.live_ps(timeout_seconds=1.0)
    _ = port.ps(timeout_seconds=1.0)

    assert runner.calls == [
        ["fabro", "ps", "--json", "--server", "https://factory.example.test"],
        ["fabro", "ps", "-a", "--json", "--server", "https://factory.example.test"],
    ]
