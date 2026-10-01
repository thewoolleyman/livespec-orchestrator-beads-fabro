"""Turn-end discipline every ACP node prompt of the implement workflow must carry.

bd-ib-5qlr: an ACP turn does not COMPLETE while the agent session still has work
outstanding, so a stage that leaves a backgrounded tool call running holds the
prompt open until the node ceiling fires — and already-finished green work is
then recorded as a timed-out stage. Measured instances cost 28, 75 and 89 minutes
of factory wall-clock, plus four runs lost in one night to a single backgrounded
command. The prompt-side mitigation is one instruction, in ONE wording, on every
ACP node prompt.

The prompt list is DERIVED from the committed graph rather than spelled here: a
hand-written list is blind to an ACP node added later, and would report a clean
pass for a prompt nothing ever checked. The sibling control asserts the derivation
reached every prompt file on disk, so a scan that silently matched nothing — or
matched a subset — fails instead of certifying what it never read.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_WORKFLOW_DIR = _REPO_ROOT / ".claude-plugin" / ".fabro" / "workflows" / "implement-work-item"
_PROMPTS_DIR = _WORKFLOW_DIR / "prompts"
_GRAPH = _WORKFLOW_DIR / "workflow.fabro"

# A graph node block is `<name> [` on its own line through a closing `]` on its
# own line. Edge declarations carry their attributes inline on ONE line, so this
# shape cannot match an edge.
_NODE_BLOCK = re.compile(
    r"^[ \t]*(?P<name>\w+)[ \t]*\[$(?P<body>.*?)^[ \t]*\]$",
    re.DOTALL | re.MULTILINE,
)
_PROMPT_ATTR = re.compile(r'prompt="@prompts/(?P<file>[\w.-]+\.md)"')

_TURN_END_HEADING = "## Ending the turn — leave nothing running in the background"
# One regex rather than a find-the-next-heading walk: the lookahead ends the
# section at the next H2 or at end of file without a branch either way.
_TURN_END_SECTION = re.compile(
    rf"^{re.escape(_TURN_END_HEADING)}\n.*?(?=\n## |\Z)",
    re.DOTALL | re.MULTILINE,
)

# Needles chosen to sit WITHIN one physical line of the hard-wrapped block: a
# needle straddling a line break fails while the prose says exactly the thing,
# which is a probe that can only fail silently.
_REQUIRED_PHRASES = (
    "NEVER background a tool call.",
    "`run_in_background`",
    "Run a long command in the FOREGROUND",
    "STOP it",
    "before your final message",
    "Your final message must be the LAST thing the turn does.",
)


def _acp_prompt_files() -> tuple[str, ...]:
    """Prompt filenames of every `backend="acp"` node in the committed graph."""
    graph = _GRAPH.read_text(encoding="utf-8")
    names: list[str] = []
    for block in _NODE_BLOCK.finditer(graph):
        body = block.group("body")
        if 'backend="acp"' not in body:
            continue
        attr = _PROMPT_ATTR.search(body)
        assert attr is not None, f"acp node {block.group('name')} declares no prompt"
        names.append(attr.group("file"))
    return tuple(names)


_ACP_PROMPT_FILES = _acp_prompt_files()


def _prompt_text(*, name: str) -> str:
    return (_PROMPTS_DIR / name).read_text(encoding="utf-8")


def test_the_graph_scan_reaches_every_prompt_file_in_the_bundle() -> None:
    """Control: the derivation can return a hit for each prompt, and finds them all."""
    on_disk = sorted(path.name for path in _PROMPTS_DIR.glob("*.md"))

    assert on_disk, f"no prompt files found under {_PROMPTS_DIR}"
    assert sorted(_ACP_PROMPT_FILES) == on_disk
    assert len(set(_ACP_PROMPT_FILES)) == len(_ACP_PROMPT_FILES)


@pytest.mark.parametrize("prompt_name", _ACP_PROMPT_FILES)
def test_every_acp_node_prompt_forbids_leaving_work_running_at_turn_end(
    prompt_name: str,
) -> None:
    sections = _TURN_END_SECTION.findall(_prompt_text(name=prompt_name))

    assert len(sections) == 1, (
        f"{prompt_name} carries {len(sections)} turn-end sections headed "
        f"{_TURN_END_HEADING!r}; expected exactly one"
    )
    for phrase in _REQUIRED_PHRASES:
        assert phrase in sections[0], f"{prompt_name}'s turn-end section omits {phrase!r}"


def test_the_turn_end_instruction_is_one_wording_across_every_acp_prompt() -> None:
    """One wording, not seven: a per-prompt paraphrase drifts and cannot be audited."""
    per_prompt = {
        name: _TURN_END_SECTION.findall(_prompt_text(name=name)) for name in _ACP_PROMPT_FILES
    }
    without = sorted(name for name, found in per_prompt.items() if len(found) != 1)

    assert not without, f"prompts without exactly one turn-end section: {without}"
    distinct = {found[0] for found in per_prompt.values()}
    assert len(distinct) == 1, (
        f"{len(distinct)} distinct turn-end wordings across "
        f"{len(per_prompt)} prompts; expected one"
    )
