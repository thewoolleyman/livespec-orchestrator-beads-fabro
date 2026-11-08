"""Scenario 199's grade-once-through-the-commit-hook rule in the dispatched fix prompt.

The source-prompt test establishes the rule in the committed prose.  This test
crosses the materialization and input-binding seam: a fix turn follows the
prompt copied into its per-dispatch payload, so the rule must survive there and
no numbered instruction may direct a run of the bound full check suite.
"""

from __future__ import annotations

import re
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands import dispatcher
from livespec_orchestrator_beads_fabro.commands._dispatcher_integration_projection import (
    workflow_declared_inputs,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_payload import (
    WorkflowPayload,
    materialize_workflow_payload,
)
from livespec_orchestrator_beads_fabro.commands._node_timeouts import default_node_timeouts

_PLUGIN_ROOT = Path(dispatcher.__file__).resolve().parents[3]
_WORKFLOW_DIR = _PLUGIN_ROOT / ".fabro" / "workflows" / "implement-work-item"
_WORKFLOW = _WORKFLOW_DIR / "workflow.toml"
_CHECK_SUITE = "./fixture-gates --every-target"
_OPEN = "{" + "{"
_CLOSE = "}" + "}"
_CHECK_SUITE_TOKEN = f"{_OPEN} inputs.sandbox_check_suite {_CLOSE}"

_NODE_BLOCK = re.compile(
    r"^[ \t]*(?P<name>\w+)[ \t]*\[$(?P<body>.*?)^[ \t]*\]$",
    re.DOTALL | re.MULTILINE,
)
_PROMPT_ATTR = re.compile(r'prompt="@prompts/(?P<file>[\w.-]+\.md)"')
_LIST_ITEM = re.compile(r"^\s*\d+\.\s")

_RULE_SENTENCES = (
    "This turn directs no run of the full check suite beyond what its commit hook runs.",
    "Do NOT start a full run of the check suite while `HEAD` and the working tree",
    "failing tests that target's own output names",
    "A command whose tool call returned WITHOUT an exit status is STILL RUNNING",
    "Do NOT start a full run of the check suite while another full run you started is still live.",
    "commit that tree through the commit hook to a passing result before the turn ends.",
)


def _fix_prompt_file() -> str:
    """Return the prompt filename the committed graph dispatches for `fix`."""
    graph = (_WORKFLOW_DIR / "workflow.fabro").read_text(encoding="utf-8")
    names: list[str] = []
    for block in _NODE_BLOCK.finditer(graph):
        if block.group("name") != "fix":
            continue
        attribute = _PROMPT_ATTR.search(block.group("body"))
        assert attribute is not None, "the fix node declares no prompt"
        names.append(attribute.group("file"))
    assert len(names) == 1, f"graph declares {len(names)} fix prompts; expected one"
    return names[0]


def _dispatched_fix_prompt(*, payload_dir: Path) -> str:
    """Materialize and bind the exact fix prompt a dispatched run receives."""
    declared = workflow_declared_inputs(committed_text=_WORKFLOW.read_text(encoding="utf-8"))
    payload = materialize_workflow_payload(
        committed=_WORKFLOW,
        payload_dir=payload_dir,
        timeouts=default_node_timeouts(),
        adapters={name: value for name, value in declared.items() if name.endswith("_adapter")},
    )
    assert isinstance(payload, WorkflowPayload)
    prompt = payload.graph.parent / "prompts" / _fix_prompt_file()
    assert prompt.is_file()
    assert prompt != _WORKFLOW_DIR / "prompts" / _fix_prompt_file()
    return prompt.read_text(encoding="utf-8").replace(_CHECK_SUITE_TOKEN, _CHECK_SUITE)


def _fix_steps(*, prompt: str) -> tuple[str, ...]:
    """Return each numbered instruction of the rendered fix prompt."""
    return tuple(line for line in prompt.splitlines() if _LIST_ITEM.match(line) is not None)


def _suite_directives(*, prompt: str) -> tuple[str, ...]:
    """Return each numbered fix instruction that directs the full suite."""
    directives: list[list[str]] = []
    current: list[str] | None = None
    for line in prompt.splitlines():
        if _LIST_ITEM.match(line) is not None:
            current = [line]
            directives.append(current)
        elif current is not None and line:
            current.append(line)
        elif not line:
            current = None
    rendered = tuple("\n".join(item) for item in directives)
    return tuple(item for item in rendered if _CHECK_SUITE in item)


def test_dispatched_fix_prompt_directs_no_suite_run_beyond_the_commit_hook(
    tmp_path: Path,
) -> None:
    """The rendered prompt carries the rule and no numbered step directs the bound suite."""
    prompt = _dispatched_fix_prompt(payload_dir=tmp_path / "payload")

    assert len(_fix_steps(prompt=prompt)) >= 6, "the numbered-step scan found too few steps"
    assert _suite_directives(prompt=prompt) == ()
    for sentence in _RULE_SENTENCES:
        assert sentence in prompt, f"the dispatched fix prompt omits {sentence!r}"
    assert _CHECK_SUITE in prompt, "the rendered section no longer names the bound check suite"
