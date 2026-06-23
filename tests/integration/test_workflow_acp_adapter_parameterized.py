"""The implement workflow parameterizes its ACP adapter (work-item 6pl3in).

The three agent nodes (implement, fix, pr) launch their coding-agent adapter
via `{{ inputs.acp_adapter }}` rather than a hard-coded command, so the
Dispatcher can route a work-item to a Codex worker with
`fabro run --input acp_adapter=...`. The input defaults to the Claude adapter
in workflow.toml, so the default dispatch behavior is unchanged.
"""

from __future__ import annotations

import re
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_WORKFLOW_DIR = _REPO_ROOT / ".fabro" / "workflows" / "implement-work-item"
_WORKFLOW_DOT = _WORKFLOW_DIR / "workflow.fabro"
_WORKFLOW_TOML = _WORKFLOW_DIR / "workflow.toml"
_CLAUDE_ADAPTER = "npx -y @agentclientprotocol/claude-agent-acp"
_EXPECTED_ACP_LINES = 3


def test_all_acp_nodes_use_the_parameterized_adapter() -> None:
    dot = _WORKFLOW_DOT.read_text(encoding="utf-8")
    acp_lines = [line.strip() for line in dot.splitlines() if "acp.command=" in line]
    assert len(acp_lines) == _EXPECTED_ACP_LINES
    assert all(line == 'acp.command="{{ inputs.acp_adapter }}"' for line in acp_lines)


def test_no_node_hardcodes_the_claude_adapter_command() -> None:
    dot = _WORKFLOW_DOT.read_text(encoding="utf-8")
    assert f'acp.command="{_CLAUDE_ADAPTER}"' not in dot


def test_toml_declares_acp_adapter_defaulting_to_claude() -> None:
    toml = _WORKFLOW_TOML.read_text(encoding="utf-8")
    assert "[run.inputs]" in toml
    assert re.search(
        r'^\s*acp_adapter\s*=\s*"' + re.escape(_CLAUDE_ADAPTER) + r'"',
        toml,
        re.MULTILINE,
    )
