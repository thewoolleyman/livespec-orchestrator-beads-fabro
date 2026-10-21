"""The proof-capture Self-contained bullet scopes its duty by what the REPLAYER has.

bd-ib-qnokup: the bullet required a step's program text whenever a step ran "a
program rather than a bare command", and enumerated four shapes — a heredoc, a
scratch script, a `-c` one-liner, a patch. That enumeration is not a rule, and
it leaves the one question a capturing agent actually has unanswered: does a
helper the step invokes by PATH need copying in? The answer depends entirely on
whether the replayer will have it, which the enumeration never mentions.
Measured 2026-10-20: records whose steps ran untracked
`/tmp/proof-capture/*.py` programs the record never contained were rejected
round after round until the run died on its firing budget.

`SPECIFICATION/contracts.md` ratified the rule in v175, in its account of the
Definition-of-Done and Proof-of-Done stages: every program a reproduction step
executes that is neither tracked in the repository at the commit the record
names nor an installed tool invoked by its name MUST be written into the record
itself, inline or as an asset the record names through the proof asset store, so
that each step can be replayed from the record, that commit and the sandbox's
installed tools alone — and a step MAY invoke a tracked program by its path, and
an installed tool by its name, without copying either in. This module binds the
prompt to that rule.

WHY A PROMPT TEST AND NOT A CODE TEST. The reproduction steps are authored by
the `proof_capture` agent out of this prose and are rendered by no Python
caller, exactly as the proof-record disciplines beside this module record.
Nothing host-side can observe that a step invoked a program the record does not
carry: the capture passes, the record publishes, and the defect surfaces one
stage later as a `not_reproduced` verdict against an implementation that is
correct.

THE PROMPT IS DERIVED FROM THE GRAPH's `proof_capture` node rather than named by
path, so this asserts about the file that node actually dispatches: a literal
path keeps passing after the node is re-pointed at a different prompt, which is
an instrument that cannot return the hit it exists to find. The sibling control
asserts the derivation named exactly one such node and that its prompt is on
disk.

THE NEEDLES ARE SCOPED TO THE SELF-CONTAINED BULLET, not to the whole prompt.
The prompt's Step 5 separately requires the publishing step's body to carry the
`COMPLETE SOURCE of any program it runs`, so a whole-file probe would be
satisfied by that paragraph and could then read clean over a bullet that scoped
nothing — which is the state this item exists to end.

WHITESPACE IS COLLAPSED BEFORE EVERY PROBE. Prompt prose is hard-wrapped, so a
needle straddling a line break fails while the prose says exactly the thing — a
probe that can only fail SILENTLY, which is the failure the tier's conventions
name first.

THE UNCHANGED HALF IS ASSERTED TOO, in the bullet rather than the file. The
OUTPUT-IS-NOT-SOURCE clause predates this rule and is bound at whole-file level
by `tests/integration/test_proof_finding_work_order_scenario138.py`; a rewrite
of this bullet could drop it and still satisfy that module, because Step 5 says
it elsewhere. Keeping it here is what makes the narrowing a narrowing rather
than a replacement.
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

# The bullet runs from its own marker to the next TOP-LEVEL bullet or heading,
# whichever comes first. Its own sub-bullets are indented, so they cannot end it.
_SELF_CONTAINED_BULLET = re.compile(
    r"^- \*\*Self-contained in its PROGRAM TEXT\.\*\*.*?(?=^- \*\*|^## |\Z)",
    re.DOTALL | re.MULTILINE,
)

# The rule itself, stated as the two-sided test the replayer poses rather than
# as a list of program shapes. All three needles are required: the condition
# alone leaves the asset route unstated, the asset route alone does not say which
# programs owe it, and the replayability sentence is what lets an author decide a
# shape none of this prose anticipated.
_SCOPING_RULE = (
    "Every program a step executes that is NEITHER tracked in the repository at",
    "the commit this record names NOR an installed tool invoked by its name MUST",
    "be written into the record itself",
    "or into a proof asset the record names through the proof asset store",
    "The test is replayability from three things alone: this record, that commit,",
    "and the sandbox's installed tools",
)

# The two exemptions, which are the half the enumeration could not express. A
# rule with no exemption reads as "publish every program", and an author obeying
# it copies the repository's own tracked scripts into the record — which inflates
# every record against a size budget the prompt enforces one section later.
_EXEMPTIONS = (
    "A program the repository TRACKS at that commit may be invoked by its path",
    "an INSTALLED tool may be invoked by its name",
    "because the replayer has both",
)

# The scratch directory, named because it is the shape that actually failed and
# because its untrackedness is a property of the directory rather than of any
# program in it.
_SCRATCH_IS_UNTRACKED = 'anything under `"${TMPDIR:-/tmp}/proof-capture"` is untracked by'

# The clause the narrowing must not drop, and the measurement that earned it.
_OUTPUT_IS_NOT_SOURCE = (
    "Publishing only the invocation line and the program's OUTPUT does not satisfy",
    "UNREPLAYABLE",
    "graded `not_reproduced` however correct the implementation is",
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


def _self_contained_bullet() -> str:
    """The one Self-contained bullet of that prompt, whitespace-collapsed."""
    assert len(_PROOF_CAPTURE_PROMPT_FILES) == 1
    text = (_PROMPTS_DIR / _PROOF_CAPTURE_PROMPT_FILES[0]).read_text(encoding="utf-8")
    bullets = _SELF_CONTAINED_BULLET.findall(text)
    assert len(bullets) == 1, (
        f"the proof-capture prompt carries {len(bullets)} Self-contained bullets; expected "
        f"one. A step's program travels with the record only if this bullet says which "
        f"programs owe their source, so a prompt with none leaves the decision to an "
        f"author who cannot see the replay, and a prompt with two lets it pick the "
        f"cheaper reading"
    )
    return re.sub(r"\s+", " ", bullets[0])


def test_the_graph_scan_names_one_proof_capture_prompt_that_is_on_disk() -> None:
    """Control: the derivation can return a hit, and the file it names exists."""
    assert len(_PROOF_CAPTURE_PROMPT_FILES) == 1, (
        f"graph declares {len(_PROOF_CAPTURE_PROMPT_FILES)} `{_PROOF_CAPTURE_NODE}` nodes "
        f"with a prompt; expected one"
    )
    named = _PROMPTS_DIR / _PROOF_CAPTURE_PROMPT_FILES[0]
    assert named.is_file(), f"{named} is declared by the graph but absent on disk"


def test_the_self_contained_bullet_scopes_the_duty_by_what_the_replayer_has() -> None:
    """Untracked-at-that-commit and not-an-installed-tool is the whole condition."""
    bullet = _self_contained_bullet()

    for phrase in _SCOPING_RULE:
        assert phrase in bullet, (
            f"the Self-contained bullet omits {phrase!r}, so the duty is scoped by a list "
            f"of program shapes rather than by what the replayer will have, and a step "
            f"invoking an untracked helper by its path owes nothing"
        )


def test_the_self_contained_bullet_names_both_exemptions() -> None:
    """A tracked program by path and an installed tool by name need no copy."""
    bullet = _self_contained_bullet()

    for phrase in _EXEMPTIONS:
        assert phrase in bullet, (
            f"the Self-contained bullet omits {phrase!r}, so the rule reads as 'publish "
            f"every program' and an author obeying it copies the repository's own tracked "
            f"scripts into a record the prompt bounds by size two sections later"
        )


def test_the_self_contained_bullet_names_the_scratch_directory_as_untracked() -> None:
    """The measured failure shape is named where an author would recognise it."""
    bullet = _self_contained_bullet()

    assert _SCRATCH_IS_UNTRACKED in bullet, (
        f"the Self-contained bullet omits {_SCRATCH_IS_UNTRACKED!r}, so the one shape that "
        f"cost a run its firing budget — a program authored into the capture scratch "
        f"directory, which no commit can track — is left for an author to classify"
    )


def test_the_self_contained_bullet_keeps_the_output_is_not_source_clause() -> None:
    """Narrowing the duty does not retire the clause that made it enforceable."""
    bullet = _self_contained_bullet()

    for phrase in _OUTPUT_IS_NOT_SOURCE:
        assert phrase in bullet, (
            f"the Self-contained bullet omits {phrase!r}, so scoping which programs owe "
            f"their source has also dropped what an absent one costs, and a record "
            f"publishing an invocation line beside its output reads as compliant"
        )
