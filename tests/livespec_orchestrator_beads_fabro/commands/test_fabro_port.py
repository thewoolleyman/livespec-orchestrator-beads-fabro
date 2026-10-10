"""Tests for the thin Fabro CLI port."""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult

_MODULE_PATH = Path(
    ".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/_fabro_port.py"
)
_MODULE_NAME = "livespec_orchestrator_beads_fabro.commands._fabro_port"


@dataclass(kw_only=True)
class _Call:
    argv: list[str]
    cwd: Path
    timeout_seconds: float
    env: dict[str, str] | None


@dataclass(kw_only=True)
class _Runner:
    results: list[CommandResult]
    calls: list[_Call]

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        _ = stdin
        self.calls.append(_Call(argv=argv, cwd=cwd, timeout_seconds=timeout_seconds, env=env))
        return self.results.pop(0)


def _port_module() -> Any:
    assert _MODULE_PATH.is_file()
    return importlib.import_module(_MODULE_NAME)


def test_fabro_port_is_the_only_public_fabro_cli_and_response_surface() -> None:
    """Legacy dispatcher modules must not keep duplicate Fabro readers."""
    argv_module = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_fabro_argv"
    )
    run_status_module = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_run_status"
    )
    # The stale-run sweep that used to carry its own Fabro reader is GONE,
    # subsumed by the reconciler, so the guard is now that no module of that
    # name survives to grow one back.
    sweep_path = _MODULE_PATH.with_name("_dispatcher_stale_run_sweep.py")
    reconciler_module = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_runs"
    )

    assert not any(name.startswith("fabro_") for name in argv_module.__all__)
    assert "parse_run_id" not in run_status_module.__all__
    assert "parse_run_status" not in run_status_module.__all__
    assert not sweep_path.exists()
    assert not any(name.startswith("fabro_") for name in reconciler_module.__all__)


def test_fabro_port_run_builds_livespec_run_argv_and_parses_run_id(tmp_path: Path) -> None:
    module = _port_module()
    login_value = "fixture-login-value"
    runner = _Runner(
        results=[CommandResult(exit_code=0, stdout="\x1b[2mRun: 01ABC\x1b[0m\n", stderr="")],
        calls=[],
    )
    port = module.FabroPort(
        fabro_bin="/opt/fabro-254",
        target=module.FabroTarget(
            server_url="http://127.0.0.1:32276",
            dev_token=login_value,
        ),
        runner=runner,
        cwd=tmp_path,
    )

    result = port.run(
        workflow_toml=tmp_path / "workflow.toml",
        goal_file=tmp_path / "goal.md",
        inputs=("acp_adapter=codex-acp", "review_fix_visit_cap=2"),
        timeout_seconds=42.0,
    )

    assert result.run_id == "01ABC"
    assert runner.calls == [
        _Call(
            argv=[
                "/opt/fabro-254",
                "run",
                str(tmp_path / "workflow.toml"),
                "--goal-file",
                str(tmp_path / "goal.md"),
                "--input",
                "acp_adapter=codex-acp",
                "--input",
                "review_fix_visit_cap=2",
                "--no-upgrade-check",
                "--server",
                "http://127.0.0.1:32276",
            ],
            cwd=tmp_path,
            timeout_seconds=42.0,
            env={"FABRO_SERVER": "http://127.0.0.1:32276"},
        )
    ]


def test_petri_fabro_run_receives_the_self_contained_workflow_package(
    tmp_path: Path,
) -> None:
    """The Petri client collects the package directory, not its config file."""
    module = _port_module()
    assert "fabro_version" in module.FabroPort.__dataclass_fields__

    package = tmp_path / "fabro-workflow-bd-ib-na2ddt"
    package.mkdir()
    graph = package / "workflow.fabro"
    workflow_toml = package / "workflow.toml"
    _ = graph.write_text("digraph Launch { start -> exit }\n", encoding="utf-8")
    resolved_config = '_version = 1\n\n[run]\ndispatch_id = "dispatch-1"\n'
    _ = workflow_toml.write_text(resolved_config, encoding="utf-8")
    runner = _Runner(
        results=[CommandResult(exit_code=0, stdout="Run: 01PETRI\n", stderr="")],
        calls=[],
    )
    port = module.FabroPort(
        fabro_bin="/opt/fabro-378",
        target=module.FabroTarget(server_url="http://127.0.0.1:32278"),
        runner=runner,
        cwd=tmp_path,
        fabro_version="fabro 0.378.0-nightly.0 (fixture)",
    )

    result = port.run(
        workflow_toml=workflow_toml,
        goal_file=tmp_path / "goal.md",
        inputs=(),
        timeout_seconds=42.0,
    )

    assert result.run_id == "01PETRI"
    assert graph.is_file()
    assert workflow_toml.read_text(encoding="utf-8") == resolved_config
    assert runner.calls[0].argv[2] == str(package)


def test_pinned_fabro_run_keeps_the_run_config_overlay_file(tmp_path: Path) -> None:
    """The pinned 0.254 client keeps the file-shaped launch contract exactly."""
    module = _port_module()
    overlay = tmp_path / "fabro-run-config-bd-ib-na2ddt.toml"
    _ = overlay.write_text('_version = 1\n\n[run]\ngoal = "fixture"\n', encoding="utf-8")
    runner = _Runner(
        results=[CommandResult(exit_code=0, stdout="Run: 01PINNED\n", stderr="")],
        calls=[],
    )
    port = module.FabroPort(
        fabro_bin="/opt/fabro-254",
        target=module.FabroTarget(server_url="http://127.0.0.1:32276"),
        runner=runner,
        cwd=tmp_path,
        fabro_version="fabro 0.254.0 (fixture)",
    )

    result = port.run(
        workflow_toml=overlay,
        goal_file=tmp_path / "goal.md",
        inputs=(),
        timeout_seconds=42.0,
    )

    assert result.run_id == "01PINNED"
    assert runner.calls[0].argv[2] == str(overlay)


def test_fabro_port_auth_login_uses_dev_token_and_server_as_subcommand_flags(
    tmp_path: Path,
) -> None:
    module = _port_module()
    login_value = "fixture-login-value"
    runner = _Runner(results=[CommandResult(exit_code=0, stdout="", stderr="")], calls=[])
    port = module.FabroPort(
        fabro_bin="fabro-candidate",
        target=module.FabroTarget(server_url="http://factory", dev_token=login_value),
        runner=runner,
        cwd=tmp_path,
    )

    result = port.auth_login(timeout_seconds=5.0)

    assert result.command.exit_code == 0
    assert runner.calls == [
        _Call(
            argv=[
                "fabro-candidate",
                "auth",
                "login",
                "--dev-token",
                login_value,
                "--server",
                "http://factory",
            ],
            cwd=tmp_path,
            timeout_seconds=5.0,
            env=None,
        )
    ]


def test_fabro_port_json_operations_parse_payloads_and_run_summaries(tmp_path: Path) -> None:
    module = _port_module()
    runner = _Runner(
        results=[
            CommandResult(exit_code=0, stdout='{"status": {"kind": "blocked"}}', stderr=""),
            CommandResult(exit_code=0, stdout='{"events": [{"timestamp": 12}]}', stderr=""),
            CommandResult(
                exit_code=0,
                stdout=(
                    '{"runs": [{"run_id": "01RUN", "status": {"kind": "running"}, '
                    '"goal": "Work-item: bd-ib-okr5ru", "total_usd_micros": 1250}]}'
                ),
                stderr="",
            ),
            CommandResult(exit_code=0, stdout='{"valid": true}', stderr=""),
        ],
        calls=[],
    )
    port = module.FabroPort(
        fabro_bin="fabro",
        target=module.FabroTarget(server_url="http://factory"),
        runner=runner,
        cwd=tmp_path,
    )

    inspect = port.inspect(run_id="01RUN", timeout_seconds=1.0)
    events = port.events(run_id="01RUN", timeout_seconds=2.0)
    ps = port.ps(timeout_seconds=3.0)
    validate = port.validate(workflow_toml=tmp_path / "workflow.toml", timeout_seconds=4.0)

    assert inspect.status_kind == "blocked"
    assert events.payload == {"events": [{"timestamp": 12}]}
    assert ps.runs == (
        module.FabroRunSummary(
            run_id="01RUN",
            status_kind="running",
            goal="Work-item: bd-ib-okr5ru",
            total_usd_micros=1250,
        ),
    )
    assert getattr(ps.runs[0], "work_item_id", None) == "bd-ib-okr5ru"
    assert validate.payload == {"valid": True}
    assert [call.argv for call in runner.calls] == [
        ["fabro", "inspect", "01RUN", "--json", "--server", "http://factory"],
        ["fabro", "events", "01RUN", "--json", "--server", "http://factory"],
        ["fabro", "ps", "-a", "--json", "--server", "http://factory"],
        ["fabro", "validate", str(tmp_path / "workflow.toml"), "--json"],
    ]


def test_fabro_port_preflight_builds_livespec_run_configuration_argv(tmp_path: Path) -> None:
    module = _port_module()
    runner = _Runner(
        results=[CommandResult(exit_code=0, stdout='{"ok": true}', stderr="")],
        calls=[],
    )
    port = module.FabroPort(
        fabro_bin="fabro",
        target=module.FabroTarget(server_url="http://factory"),
        runner=runner,
        cwd=tmp_path,
    )

    result = port.preflight(
        workflow_toml=tmp_path / "workflow.toml",
        goal_file=tmp_path / "goal.md",
        inputs=("acp_adapter=codex-acp",),
        timeout_seconds=4.0,
    )

    assert result.payload == {"ok": True}
    assert runner.calls == [
        _Call(
            argv=[
                "fabro",
                "preflight",
                str(tmp_path / "workflow.toml"),
                "--goal-file",
                str(tmp_path / "goal.md"),
                "--input",
                "acp_adapter=codex-acp",
                "--no-upgrade-check",
                "--json",
                "--server",
                "http://factory",
            ],
            cwd=tmp_path,
            timeout_seconds=4.0,
            env={"FABRO_SERVER": "http://factory"},
        )
    ]


def test_fabro_port_rm_and_version_stay_on_the_declared_surface(tmp_path: Path) -> None:
    module = _port_module()
    runner = _Runner(
        results=[
            CommandResult(exit_code=0, stdout="", stderr=""),
            CommandResult(exit_code=0, stdout="fabro 0.254.0 (8de6611)\n", stderr=""),
        ],
        calls=[],
    )
    port = module.FabroPort(
        fabro_bin="fabro",
        target=module.FabroTarget(),
        runner=runner,
        cwd=tmp_path,
    )

    rm = port.rm(run_id="01RUN", timeout_seconds=6.0)
    version = port.version(timeout_seconds=7.0)

    assert rm.command.exit_code == 0
    assert version.text == "fabro 0.254.0 (8de6611)\n"
    assert [call.argv for call in runner.calls] == [
        ["fabro", "rm", "-f", "01RUN"],
        ["fabro", "version"],
    ]


def test_fabro_port_can_probe_top_level_server_parse_rejection(tmp_path: Path) -> None:
    module = _port_module()
    runner = _Runner(
        results=[CommandResult(exit_code=2, stdout="", stderr="unexpected argument '--server'")],
        calls=[],
    )
    port = module.FabroPort(
        fabro_bin="fabro",
        target=module.FabroTarget(server_url="http://factory"),
        runner=runner,
        cwd=tmp_path,
    )

    result = port.top_level_server_parse_probe(
        subcommand=("ps", "-a", "--json"),
        timeout_seconds=8.0,
    )

    assert result.command.exit_code == 2
    assert runner.calls == [
        _Call(
            argv=["fabro", "--server", "http://factory", "ps", "-a", "--json"],
            cwd=tmp_path,
            timeout_seconds=8.0,
            env=None,
        )
    ]
