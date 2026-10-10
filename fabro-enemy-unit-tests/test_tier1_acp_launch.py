"""Tier 1 Enemy Unit Test for launching an ACP agent node.

The factory's every real stage is an ACP agent node, so "the engine can launch
an ACP agent from a literal configuration and read its answer" is the single
behaviour the Petri migration must preserve above all others. This test launches
the no-network fake agent carried in this directory and reads the run's
terminal status as the oracle. Measured 2026-10-08: on 0.378.0-nightly.0 the
node needs `backend="acp"` and either the `acp.config` JSON form or a literal
`acp.command`; a templated `acp.command` kills the agent before the protocol
completes. The server must hold at least one provider secret (a placeholder is
enough) or `fabro.model.no_ready_provider` refuses the run at admission.

Excluded from `just check`:

    just fabro-enemy-tier1
"""

from __future__ import annotations

from pathlib import Path

from _fake_acp_agent import ENV_PROBE_MODE, ENV_PROBE_NAME, ENV_PROBE_VALUE
from _tier0_support import (
    TIMEOUT_SECONDS,
    _assert_success,
    _FabroTier0Config,
    _inspect_record,
)
from _tier1_support import _failure_block, _write_goal, _write_workflow
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import (
    SynchronousFabroLauncher,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_graph_adapters import (
    render_acp_commands,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import ShellCommandRunner
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import build_plan
from livespec_orchestrator_beads_fabro.commands._fabro_client import (
    materialized_workflow_config,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port import FabroPort

__all__: list[str] = []

_RUN_TIMEOUT_SECONDS = 300.0
# Relative to the repository root the sandbox clones; the agent must be on the
# observed commit.
_FAKE_AGENT = "fabro-enemy-unit-tests/_fake_acp_agent.py"

_ACP_CONFIG_WORKFLOW = f"""
digraph FabroEnemyAcpConfigLaunch {{
    start [shape=Mdiamond, label="Start"]
    agent [shape=box, label="Agent", backend="acp", goal_gate=true, acp.config="{{\\"command\\": \\"python3\\", \\"args\\": [\\"{_FAKE_AGENT}\\", \\"success\\", \\"/tmp/eut-acp-config-record.jsonl\\"], \\"env\\": {{}}}}", prompt="say hi"]
    exit [shape=Msquare, label="Exit"]
    start -> agent
    agent -> exit
}}
"""

_ACP_COMMAND_WORKFLOW = f"""
digraph FabroEnemyAcpCommandLaunch {{
    start [shape=Mdiamond, label="Start"]
    agent [shape=box, label="Agent", backend="acp", goal_gate=true, acp.command="EUT_PROBE=1 python3 {_FAKE_AGENT} success /tmp/eut-acp-command-record.jsonl", prompt="say hi"]
    exit [shape=Msquare, label="Exit"]
    start -> agent
    agent -> exit
}}
"""


# The template token written as two pieces rather than as the literal pair, so
# quoting this file's text into a ledger comment or a run goal cannot poison the
# rendering (the fleet convention of livespec-dev-tooling-9yb4).
_ADAPTER_INPUT = "probe_adapter"
_TOKEN = "{" + f"{{ inputs.{_ADAPTER_INPUT} }}" + "}"

# The quote-and-backslash-bearing adapter command, assembled from the agent's
# own three constants so there is exactly ONE declaration of the intended
# bytes. This is the UNESCAPED command -- what the dispatch record reports and
# what the agent must observe -- never the DOT form.
_ESCAPED_PROBE_COMMAND = (
    f"{ENV_PROBE_NAME}='{ENV_PROBE_VALUE}' "
    f"python3 {_FAKE_AGENT} {ENV_PROBE_MODE} /tmp/eut-acp-escaped-record.jsonl"
)

# This node declares the adapter by TEMPLATE REFERENCE rather than literally,
# because that is the one path through `render_acp_commands` that reaches the
# escape: a command already written literally in a graph is already graph bytes
# and passes through untouched.
_ESCAPED_COMMAND_TEMPLATE = f"""
digraph FabroEnemyAcpEscapedCommandLaunch {{
    start [shape=Mdiamond, label="Start"]
    agent [shape=box, label="Agent", backend="acp", goal_gate=true, acp.command="{_TOKEN}", prompt="say hi"]
    exit [shape=Msquare, label="Exit"]
    start -> agent
    agent -> exit
}}
"""


class _Journal:
    def append(self, *, record: dict[str, object]) -> None:
        _ = record


def _run_config(*, graph: Path) -> str:
    return f"""_version = 1

[workflow]
graph = "{graph}"

[run.inputs]
review_fix_visit_cap = 2
merge_on_review_cap_outcome = "succeeded"
merge_hold = false
"""


def _run_status(*, port: FabroPort, tmp_path: Path, name: str, body: str) -> tuple[str, str]:
    workflow = _write_workflow(tmp_path=tmp_path, name=name, body=body)
    goal = _write_goal(tmp_path=tmp_path, title=name)
    run = port.run(
        workflow_toml=workflow,
        goal_file=goal,
        inputs=(),
        timeout_seconds=_RUN_TIMEOUT_SECONDS,
    )
    assert run.run_id is not None, run.command.stderr or run.command.stdout
    inspect = port.inspect(run_id=run.run_id, timeout_seconds=TIMEOUT_SECONDS)
    _assert_success(command=inspect.command)
    record = _inspect_record(value=inspect.payload)
    status = record.get("status")
    kind = status.get("kind") if isinstance(status, dict) else status
    failure = _failure_block(value=record) or {}
    detail = failure.get("detail")
    message = detail.get("message") if isinstance(detail, dict) else failure.get("message")
    return (str(kind), str(message or ""))


def _dispatcher_run_status(
    *,
    config: _FabroTier0Config,
    port: FabroPort,
    tmp_path: Path,
    name: str,
    body: str,
) -> tuple[str, str]:
    """Launch one self-contained package through the Dispatcher's launcher."""
    version = f"fabro {config.expected_client_version}"
    package = tmp_path / f"{name}-package"
    package.mkdir()
    graph = package / "workflow.fabro"
    package_config = package / "workflow.toml"
    overlay = tmp_path / f"{name}-overlay.toml"
    _ = graph.write_text(body.strip() + "\n", encoding="utf-8")
    _ = package_config.write_text(_run_config(graph=Path("workflow.fabro")), encoding="utf-8")
    _ = overlay.write_text(_run_config(graph=graph), encoding="utf-8")
    plan = build_plan(
        repo=Path.cwd(),
        work_item_id=f"fabro-eut-{name}",
        workflow_toml=materialized_workflow_config(
            version=version,
            overlay=overlay,
            package_dir=package,
        ),
        goal_file=_write_goal(tmp_path=tmp_path, title=name),
        fabro_bin=config.fabro_bin,
        fabro_factory_name="fabro-eut",
        fabro_factory_server=config.server_url,
        fabro_version=version,
        janitor=None,
        janitor_checkout=tmp_path / f"{name}-janitor",
        review_fix_cap=2,
        fabro_timeout_seconds=_RUN_TIMEOUT_SECONDS,
    )
    launched = SynchronousFabroLauncher().launch(
        plan=plan,
        runner=ShellCommandRunner(),
        journal=_Journal(),
    )
    assert launched.run_id is not None, launched.command.stderr or launched.command.stdout
    inspect = port.inspect(run_id=launched.run_id, timeout_seconds=TIMEOUT_SECONDS)
    _assert_success(command=inspect.command)
    record = _inspect_record(value=inspect.payload)
    status = record.get("status")
    kind = status.get("kind") if isinstance(status, dict) else status
    failure = _failure_block(value=record) or {}
    detail = failure.get("detail")
    message = detail.get("message") if isinstance(detail, dict) else failure.get("message")
    return (str(kind), str(message or ""))


def test_acp_agent_launches_from_acp_config_json(*, tmp_path: Path, port: FabroPort) -> None:
    kind, message = _run_status(
        port=port, tmp_path=tmp_path, name="acp-config-launch", body=_ACP_CONFIG_WORKFLOW
    )
    assert kind == "succeeded", message


def test_dispatcher_launches_the_same_literal_acp_command_on_each_engine(
    *, config: _FabroTier0Config, tmp_path: Path, port: FabroPort
) -> None:
    kind, message = _dispatcher_run_status(
        config=config,
        port=port,
        tmp_path=tmp_path,
        name="acp-command-launch",
        body=_ACP_COMMAND_WORKFLOW,
    )
    assert kind == "succeeded", message


def test_an_escaped_acp_command_reaches_the_agent_unescaped(
    *, tmp_path: Path, port: FabroPort
) -> None:
    """A quote-and-backslash command survives DOT escaping end to end.

    `bd-ib-4gkfaa`. The graph is produced by the PRODUCTION renderer rather
    than hand-written, so this exercises the escape the Dispatcher actually
    emits; and the oracle is the run's terminal status, because the agent exits
    non-zero unless the environment assignment it observes equals the unescaped
    intent byte for byte. `fabro validate` cannot answer this -- it accepts the
    escaped graph on both engines regardless of what the engine then hands the
    agent -- which is why the proof lives here and runs once per engine.
    """
    rendered = render_acp_commands(
        graph_text=_ESCAPED_COMMAND_TEMPLATE,
        adapters={_ADAPTER_INPUT: _ESCAPED_PROBE_COMMAND},
    )
    assert not isinstance(rendered, str), rendered
    # The record reports the intent, while the attribute carries the escapes.
    assert rendered.node_commands == {"agent": _ESCAPED_PROBE_COMMAND}
    assert f'acp.command="{_ESCAPED_PROBE_COMMAND}"' not in rendered.text
    assert r"\"approval_policy\"" in rendered.text

    kind, message = _run_status(
        port=port,
        tmp_path=tmp_path,
        name="acp-escaped-command-launch",
        body=rendered.text,
    )
    assert kind == "succeeded", message
