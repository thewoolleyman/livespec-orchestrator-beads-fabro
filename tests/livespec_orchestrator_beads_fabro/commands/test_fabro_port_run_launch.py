"""Tests for the `fabro run` launch assembly — argv, environment, labels.

The engine copies three run labels onto its server run span, the worker
run span and every `run_turn` span, and it parents the server run span on
the caller's `TRACEPARENT`. This module covers the argv and the
environment the Dispatcher hands it, and that the production launcher
actually passes a dispatch's own correlation rather than leaving the
labels to a default.
"""

from __future__ import annotations

import importlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

from livespec_orchestrator_beads_fabro.commands._dispatcher_correlation import (
    DispatchCorrelation,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dispatch_span import (
    dispatch_request_line,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_io_fabro_launcher import (
    WatchedFabroLauncher,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import build_plan
from livespec_orchestrator_beads_fabro.commands._fabro_port import FabroPort, FabroTarget

_MODULE_PATH = Path(
    ".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/_fabro_port_run_launch.py"
)
_MODULE_NAME = "livespec_orchestrator_beads_fabro.commands._fabro_port_run_launch"

_WORK_ITEM_ID = "bd-ib-5jvgfr"
_DISPATCH_ID = "01M4N4V6SEEKVVP88ST0CASGCP"
_FACTORY = "hp"


@dataclass(kw_only=True)
class _Runner:
    """Records every argv and environment the launch hands the CLI."""

    argvs: list[list[str]] = field(default_factory=list)
    envs: list[dict[str, str] | None] = field(default_factory=list)
    stdout: str = "Run: 01LAUNCHED\n"

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        _ = (cwd, timeout_seconds, stdin)
        self.argvs.append(argv)
        self.envs.append(env)
        return CommandResult(exit_code=0, stdout=self.stdout, stderr="")


def _launch_module() -> Any:
    assert _MODULE_PATH.is_file()
    return importlib.import_module(_MODULE_NAME)


def _run_argv(*, runner: _Runner) -> list[str]:
    return next(argv for argv in runner.argvs if argv[1] == "run")


def _run_env(*, runner: _Runner) -> dict[str, str] | None:
    return next(
        env for argv, env in zip(runner.argvs, runner.envs, strict=True) if argv[1] == "run"
    )


def _emitted_span(*, correlation: DispatchCorrelation) -> dict[str, Any]:
    """The dispatch span the Dispatcher emits for the SAME dispatch."""
    payload = json.loads(dispatch_request_line(correlation=correlation, now_ns=0))
    spans = payload["resourceSpans"][0]["scopeSpans"][0]["spans"]
    return cast("dict[str, Any]", spans[0])


def _label_values(*, argv: list[str]) -> dict[str, str]:
    """The `KEY=VALUE` operands of every `--label` pair in `argv`."""
    pairs = [argv[index + 1] for index, token in enumerate(argv) if token == "--label"]
    return dict(pair.split("=", 1) for pair in pairs)


def test_fabro_run_argv_carries_the_three_correlation_labels(tmp_path: Path) -> None:
    """One `--label KEY=VALUE` per correlation value, with this dispatch's values."""
    _ = _launch_module()
    runner = _Runner()
    port = FabroPort(
        fabro_bin="/opt/fabro",
        target=FabroTarget(server_url="http://127.0.0.1:32276"),
        runner=runner,
        cwd=tmp_path,
    )

    result = port.run(
        workflow_toml=tmp_path / "workflow.toml",
        goal_file=tmp_path / "goal.md",
        inputs=("acp_adapter=codex-acp",),
        timeout_seconds=42.0,
        correlation=DispatchCorrelation(
            work_item_id=_WORK_ITEM_ID,
            dispatch_id=_DISPATCH_ID,
            factory=_FACTORY,
        ),
    )

    assert result.run_id == "01LAUNCHED"
    argv = _run_argv(runner=runner)
    # Asserted as pairs rather than by substring: the engine reads `--label`
    # and its operand as two argv tokens, so a value spliced onto the flag
    # would satisfy a substring probe and be rejected by the engine.
    assert _label_values(argv=argv) == {
        "work.item.id": _WORK_ITEM_ID,
        "livespec.dispatch.id": _DISPATCH_ID,
        "livespec.dispatch.factory": _FACTORY,
    }
    # A hyphenated work-item id is exactly the shape every id in this tenant
    # has, so it must survive verbatim into the label rather than be
    # normalized, split or dropped.
    assert "--label" in argv
    assert argv[argv.index("--label") + 1] == f"work.item.id={_WORK_ITEM_ID}"
    # The pre-existing argv contract is untouched: labels ride beside the
    # goal file, the inputs and the server flag, never in place of them.
    assert argv[:5] == [
        "/opt/fabro",
        "run",
        str(tmp_path / "workflow.toml"),
        "--goal-file",
        str(tmp_path / "goal.md"),
    ]
    assert argv[-2:] == ["--server", "http://127.0.0.1:32276"]
    assert "--input" in argv
    assert "--no-upgrade-check" in argv


def test_the_watched_launcher_passes_its_own_dispatch_correlation(tmp_path: Path) -> None:
    """The production launcher labels a run with the dispatch it was minted for."""
    _ = _launch_module()
    runner = _Runner()
    plan = build_plan(
        repo=tmp_path,
        work_item_id=_WORK_ITEM_ID,
        workflow_toml=tmp_path / "workflow.toml",
        goal_file=tmp_path / "goal.md",
        fabro_bin="fabro",
        fabro_factory_name=_FACTORY,
        janitor=None,
        janitor_checkout=tmp_path / "janitor",
    )

    result = WatchedFabroLauncher(
        sleep=lambda _seconds: None,
        clock=lambda: 0.0,
        dispatch_id=_DISPATCH_ID,
    ).launch(
        plan=plan,
        runner=runner,
        journal=object(),  # type: ignore[arg-type]
    )

    assert result.command.exit_code == 0
    assert _label_values(argv=_run_argv(runner=runner)) == {
        "work.item.id": _WORK_ITEM_ID,
        "livespec.dispatch.id": _DISPATCH_ID,
        "livespec.dispatch.factory": _FACTORY,
    }


def test_the_fabro_run_environment_carries_this_dispatchs_own_traceparent(
    tmp_path: Path,
) -> None:
    """`TRACEPARENT` names the dispatch span, read off the span itself."""
    _ = _launch_module()
    runner = _Runner()
    correlation = DispatchCorrelation(
        work_item_id=_WORK_ITEM_ID,
        dispatch_id=_DISPATCH_ID,
        factory=_FACTORY,
    )
    port = FabroPort(
        fabro_bin="/opt/fabro",
        target=FabroTarget(server_url="http://127.0.0.1:32276"),
        runner=runner,
        cwd=tmp_path,
    )

    _ = port.run(
        workflow_toml=tmp_path / "workflow.toml",
        goal_file=tmp_path / "goal.md",
        inputs=(),
        timeout_seconds=42.0,
        correlation=correlation,
    )

    # The ids are read off the EMITTED SPAN rather than re-derived here: the
    # claim is that the environment and the span name one identity, and a
    # test that derived both from the same helper would hold even if the
    # emitter had rendered some other pair into the span it wrote.
    span = _emitted_span(correlation=correlation)
    env = _run_env(runner=runner)
    assert env is not None
    assert env.get("TRACEPARENT") == f"00-{span['traceId']}-{span['spanId']}-01"
    # The factory binding the launch already relied on is untouched.
    assert env["FABRO_SERVER"] == "http://127.0.0.1:32276"


def test_a_targetless_launch_still_carries_the_traceparent(tmp_path: Path) -> None:
    """With no factory to bind, the environment is the traceparent alone.

    The arms are independent: a launch with no server URL used to pass NO
    environment at all, so the traceparent had to stop riding on there
    being a `FABRO_SERVER` to ride beside.
    """
    _ = _launch_module()
    runner = _Runner()
    correlation = DispatchCorrelation(
        work_item_id=_WORK_ITEM_ID,
        dispatch_id=_DISPATCH_ID,
        factory=_FACTORY,
    )
    port = FabroPort(
        fabro_bin="fabro",
        target=FabroTarget(),
        runner=runner,
        cwd=tmp_path,
    )

    _ = port.run(
        workflow_toml=tmp_path / "workflow.toml",
        goal_file=tmp_path / "goal.md",
        inputs=(),
        timeout_seconds=1.0,
        correlation=correlation,
    )

    span = _emitted_span(correlation=correlation)
    assert _run_env(runner=runner) == {"TRACEPARENT": f"00-{span['traceId']}-{span['spanId']}-01"}
    assert "--server" not in _run_argv(runner=runner)
