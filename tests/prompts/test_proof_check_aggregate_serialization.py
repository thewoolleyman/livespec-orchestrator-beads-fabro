"""Proof-stage prompts must keep repository check aggregates serial.

The capture stage authors and runs the proof steps from its prompt. A detached
tool-call rule alone does not prevent a foreground shell command from putting a
full repository check aggregate behind ``&``; the sandbox then throttles every
concurrent aggregate. This prompt contract pins the capture-stage direction
that prevents that in-pod contention.
"""

from __future__ import annotations

import re
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_WORKFLOW_DIR = _REPO_ROOT / ".claude-plugin" / ".fabro" / "workflows" / "implement-work-item"
_GRAPH = _WORKFLOW_DIR / "workflow.fabro"
_PROMPTS_DIR = _WORKFLOW_DIR / "prompts"

_NODE_BLOCK = re.compile(
    r"^[ \t]*(?P<name>\w+)[ \t]*\[$(?P<body>.*?)^[ \t]*\]$",
    re.DOTALL | re.MULTILINE,
)
_PROMPT_ATTR = re.compile(r'prompt="@prompts/(?P<file>[\w.-]+\.md)"')
_PROOF_NODE_PREFIX = "proof_"

_CAPTURE_NEEDLES = (
    "Run at most ONE repository check aggregate at a time in this sandbox.",
    "A trailing `&` inside one tool call breaks this rule.",
    "Parallel tool calls that start check aggregates also break this rule.",
)


def _proof_stage_prompts() -> dict[str, Path]:
    """Derive proof-stage prompt paths from the committed workflow graph."""
    prompts: dict[str, Path] = {}
    for block in _NODE_BLOCK.finditer(_GRAPH.read_text(encoding="utf-8")):
        name = block.group("name")
        body = block.group("body")
        if not name.startswith(_PROOF_NODE_PREFIX) or 'backend="acp"' not in body:
            continue
        attribute = _PROMPT_ATTR.search(body)
        assert attribute is not None, f"proof ACP node {name} declares no prompt"
        prompts[name] = _PROMPTS_DIR / attribute.group("file")
    return prompts


def test_the_graph_derives_the_two_proof_stage_prompts() -> None:
    """Control: this contract reaches both active proof-stage prompts."""
    prompts = _proof_stage_prompts()

    assert set(prompts) == {"proof_capture", "proof_verify"}
    assert all(path.is_file() for path in prompts.values())


def test_the_capture_prompt_serializes_repository_check_aggregates() -> None:
    """One foreground call and several parallel calls are equally unsafe."""
    text = _proof_stage_prompts()["proof_capture"].read_text(encoding="utf-8")

    for needle in _CAPTURE_NEEDLES:
        assert needle in text, f"proof-capture.md omits {needle!r}"
