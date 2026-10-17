"""The git-history anchoring rule the proof-capture Deterministic bullet carries.

bd-ib-ltjrn: a reproduction step that expects a commit inside a fixed-size
window counted from HEAD passes at capture and fails at replay. The engine
appends a checkpoint commit after every node and `proof_verify` always runs at
least two checkpoints after `proof_capture`, so the depth the capture measured
is not the depth the replay leg sees. Measured 2026-10-17 on two hp-candidate
canaries: `bd-ib-qg6qkz` (run 01M55WZ7DS6AV6Q2S2S87SKBK5, pull request 3185)
published a step reading `git log --max-count=2 --format='%H %s' HEAD` and
expecting implementing commit 265e65f4 among its lines -- depth 2 at capture, 4
at verify -- so `proof_verify` failed, the `fix` round found no legitimate
change and the run ended at `needs_human`; `bd-ib-djbwai` (run
01M55FJXTN15DR6DV85ZHBX00R, pull request 3176) expected `git log -1 --format=%s
HEAD` to print its own `publish_draft` checkpoint subject and review flagged it
BLOCKING.

WHY A PROMPT TEST AND NOT A CODE TEST. The reproduction steps are authored by
the `proof_capture` agent out of this prose and are rendered by no Python
caller, exactly as the proof-record disciplines beside this module record.
Nothing on the host can observe that a step anchored itself to a moving HEAD:
the capture passes, the record publishes, and the defect surfaces one stage
later as a `not_reproduced` verdict against an implementation that is correct.

THE PROMPT IS DERIVED FROM THE GRAPH's `proof_capture` node rather than named by
path, so this asserts about the file that node actually dispatches: a literal
path keeps passing after the node is re-pointed at a different prompt, which is
an instrument that cannot return the hit it exists to find. The sibling control
asserts the derivation named exactly one such node and that its prompt is on
disk.

THE NEEDLES ARE SCOPED TO THE DETERMINISTIC BULLET, not to the whole prompt.
The Definition of Done puts the rule in that bullet, and the prompt separately
tells the record to read the publish-branch head from the forge rather than
from the clone -- a whole-file probe would be satisfied by that unrelated
paragraph and could then read clean over a Deterministic bullet that says
nothing about anchoring.

PROMPT PROSE IS HARD-WRAPPED, so every needle is chosen to sit WITHIN one
physical line, for the reason the size-budget module beside this one records: a
needle straddling a line break fails silently while the prose says exactly the
thing.
"""

from __future__ import annotations

import re
from pathlib import Path

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
_PROOF_CAPTURE_NODE = "proof_capture"

# The bullet runs from its own `- **Deterministic.**` marker to the next
# top-level bullet or heading, whichever comes first. The lookahead ends it
# without a branch either way.
_DETERMINISTIC_BULLET = re.compile(
    r"^- \*\*Deterministic\.\*\*.*?(?=^- \*\*|^## |\Z)",
    re.DOTALL | re.MULTILINE,
)

# The rule itself, as the two physical lines that carry its positive and its
# negative half. Pinned POSITIVELY rather than by probing for the absence of a
# HEAD-window phrase: an absence probe could never return a hit and would read
# clean over a bullet that said nothing at all.
_ANCHORING_RULE = (
    "MUST name a fixed commit sha",
    "depth-independent predicate",
    "fixed-size window counted from HEAD",
)


def _proof_capture_prompt_files() -> tuple[str, ...]:
    """Prompt filenames of every node named `proof_capture` in the committed graph."""
    graph = _GRAPH.read_text(encoding="utf-8")
    names: list[str] = []
    for block in _NODE_BLOCK.finditer(graph):
        if block.group("name") != _PROOF_CAPTURE_NODE:
            continue
        attr = _PROMPT_ATTR.search(block.group("body"))
        assert attr is not None, f"node {_PROOF_CAPTURE_NODE} declares no prompt"
        names.append(attr.group("file"))
    return tuple(names)


_PROOF_CAPTURE_PROMPT_FILES = _proof_capture_prompt_files()


def _deterministic_bullet() -> str:
    """The one Deterministic bullet of the prompt the graph's node dispatches."""
    assert len(_PROOF_CAPTURE_PROMPT_FILES) == 1
    text = (_PROMPTS_DIR / _PROOF_CAPTURE_PROMPT_FILES[0]).read_text(encoding="utf-8")
    bullets = _DETERMINISTIC_BULLET.findall(text)
    assert (
        len(bullets) == 1
    ), f"the proof-capture prompt carries {len(bullets)} Deterministic bullets; expected one"
    return bullets[0]


def test_the_graph_scan_names_one_proof_capture_prompt_that_is_on_disk() -> None:
    """Control: the derivation can return a hit, and the file it names exists."""
    assert len(_PROOF_CAPTURE_PROMPT_FILES) == 1, (
        f"graph declares {len(_PROOF_CAPTURE_PROMPT_FILES)} `{_PROOF_CAPTURE_NODE}` nodes "
        f"with a prompt; expected one"
    )
    named = _PROMPTS_DIR / _PROOF_CAPTURE_PROMPT_FILES[0]
    assert named.is_file(), f"{named} is declared by the graph but absent on disk"


def test_the_deterministic_bullet_anchors_a_git_history_read_to_a_fixed_sha() -> None:
    """A history-reading step names a sha or a depth-independent predicate, never a window."""
    bullet = _deterministic_bullet()

    for phrase in _ANCHORING_RULE:
        assert phrase in bullet, (
            f"the Deterministic bullet omits {phrase!r}, so a reproduction step may "
            f"anchor a git-history read to a window counted from a HEAD that moves "
            f"between capture and replay"
        )
