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

from _tier0_support import TIMEOUT_SECONDS, _assert_success, _inspect_record
from _tier1_support import _failure_block, _write_goal, _write_workflow
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


def test_acp_agent_launches_from_acp_config_json(*, tmp_path: Path, port: FabroPort) -> None:
    kind, message = _run_status(
        port=port, tmp_path=tmp_path, name="acp-config-launch", body=_ACP_CONFIG_WORKFLOW
    )
    assert kind == "succeeded", message


def test_acp_agent_launches_from_literal_acp_command(*, tmp_path: Path, port: FabroPort) -> None:
    kind, message = _run_status(
        port=port, tmp_path=tmp_path, name="acp-command-launch", body=_ACP_COMMAND_WORKFLOW
    )
    assert kind == "succeeded", message
