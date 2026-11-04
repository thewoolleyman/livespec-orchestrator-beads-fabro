"""One dispatch pass asks a factory about one run at most once.

Binds the third assertion of work-item bd-ib-6bbcda's Definition of Done: within
one dispatch pass the Dispatcher issues at most one `fabro inspect` for each
distinct pair of factory and run id. The pre-launch readers (the ACP hold
evidence, the availability confirmation, the selection replay, the grace arm)
each open their OWN port onto the same factory, so the unit that must agree is
the factory and the run, never one port object.

THE CONTROLS ARE AS LOAD-BEARING AS THE CASE. A memo keyed on the run id alone
would answer a second factory with the first one's reading, and a memo that
outlived the pass would answer a polling watcher with a stale state for the whole
life of a run; both return a plausible well-formed result and neither announces
itself, so each has its own case.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_pass_snapshot import (
    pass_snapshot,
    release_pass_snapshot,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port import FabroPort
from livespec_orchestrator_beads_fabro.commands._fabro_port_types import FabroTarget

_HP = "https://hp.example:32276"
_GMKTEC = "https://gmktec.example:32276"
_RUNNING = '{"status": {"kind": "running"}}'


@dataclass(kw_only=True)
class _Runner:
    """Answers every call with the next canned result and remembers what was asked."""

    exit_codes: list[int] = field(default_factory=list)
    argvs: list[list[str]] = field(default_factory=list)

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
        exit_code = self.exit_codes.pop(0) if self.exit_codes else 0
        return CommandResult(exit_code=exit_code, stdout=_RUNNING, stderr="")

    def inspections(self) -> list[list[str]]:
        return [argv for argv in self.argvs if "inspect" in argv]


def _port(*, runner: _Runner, server: str, tmp_path: Path) -> FabroPort:
    return FabroPort(
        fabro_bin="fabro",
        target=FabroTarget(server_url=server),
        runner=runner,
        cwd=tmp_path,
    )


def test_two_ports_onto_one_factory_inspect_one_run_once(tmp_path: Path) -> None:
    runner = _Runner()
    with pass_snapshot():
        first = _port(runner=runner, server=_HP, tmp_path=tmp_path)
        second = _port(runner=runner, server=_HP, tmp_path=tmp_path)
        a = first.inspect(run_id="run-1", timeout_seconds=60.0)
        b = second.inspect(run_id="run-1", timeout_seconds=60.0)
        c = first.inspect(run_id="run-1", timeout_seconds=60.0)
    assert len(runner.inspections()) == 1
    assert a == b == c


def test_a_different_run_or_a_different_factory_is_its_own_inspection(tmp_path: Path) -> None:
    runner = _Runner()
    with pass_snapshot():
        hp = _port(runner=runner, server=_HP, tmp_path=tmp_path)
        gmktec = _port(runner=runner, server=_GMKTEC, tmp_path=tmp_path)
        _ = hp.inspect(run_id="run-1", timeout_seconds=60.0)
        _ = hp.inspect(run_id="run-2", timeout_seconds=60.0)
        _ = gmktec.inspect(run_id="run-1", timeout_seconds=60.0)
        _ = gmktec.inspect(run_id="run-1", timeout_seconds=60.0)
    assert len(runner.inspections()) == 3


def test_outside_a_pass_every_inspection_asks_the_factory(tmp_path: Path) -> None:
    runner = _Runner()
    port = _port(runner=runner, server=_HP, tmp_path=tmp_path)
    for _ in range(3):
        _ = port.inspect(run_id="run-1", timeout_seconds=60.0)
    assert len(runner.inspections()) == 3


def test_a_released_pass_asks_the_factory_again(tmp_path: Path) -> None:
    runner = _Runner()
    port = _port(runner=runner, server=_HP, tmp_path=tmp_path)
    with pass_snapshot():
        _ = port.inspect(run_id="run-1", timeout_seconds=60.0)
        release_pass_snapshot()
        _ = port.inspect(run_id="run-1", timeout_seconds=60.0)
        _ = port.inspect(run_id="run-1", timeout_seconds=60.0)
    assert len(runner.inspections()) == 3


def test_an_inspection_that_failed_is_not_asked_again_in_the_pass(tmp_path: Path) -> None:
    runner = _Runner(exit_codes=[1, 0])
    port = _port(runner=runner, server=_HP, tmp_path=tmp_path)
    with pass_snapshot():
        first = port.inspect(run_id="run-1", timeout_seconds=60.0)
        second = port.inspect(run_id="run-1", timeout_seconds=60.0)
    assert first.command.exit_code == 1
    assert second.command.exit_code == 1
    assert len(runner.inspections()) == 1


def test_removing_a_run_forgets_what_the_pass_read_of_it(tmp_path: Path) -> None:
    runner = _Runner()
    port = _port(runner=runner, server=_HP, tmp_path=tmp_path)
    with pass_snapshot():
        _ = port.inspect(run_id="run-1", timeout_seconds=60.0)
        _ = port.rm(run_id="run-1", timeout_seconds=60.0)
        _ = port.inspect(run_id="run-1", timeout_seconds=60.0)
        _ = port.inspect(run_id="run-1", timeout_seconds=60.0)
    assert len(runner.inspections()) == 2
