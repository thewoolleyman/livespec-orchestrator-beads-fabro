"""Scenario 199's hook-green exemption in the dispatched fix prompt.

The source-prompt test establishes the once-per-tree rule in the committed
prose.  This test crosses the materialization and input-binding seam: a fix
turn follows the prompt copied into its per-dispatch payload, so the exemption
must survive there and constrain each directive that names the full suite.
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

_HOOK_GREEN_GUARD = (
    "If a commit's pre-commit hook already passed the full suite on its exact "
    "committed tree, do NOT start it yourself."
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


def test_dispatched_fix_prompt_forbids_a_second_self_started_suite_on_hook_green_tree(
    tmp_path: Path,
) -> None:
    """A hook-green commit satisfies Scenario 199 before the prompt is rendered."""
    prompt = _dispatched_fix_prompt(payload_dir=tmp_path / "payload")
    directives = _suite_directives(prompt=prompt)

    assert (
        len(directives) == 2
    ), f"found {len(directives)} dispatched suite directives; expected the repair and fix steps"
    for directive in directives:
        assert _HOOK_GREEN_GUARD in directive, (
            "a dispatched suite directive does not forbid a self-started duplicate on a "
            f"hook-green tree: {directive}"
        )
        assert "yourself until it is green" not in directive, (
            "a dispatched suite directive still directs an unconditional self-started run: "
            f"{directive}"
        )
