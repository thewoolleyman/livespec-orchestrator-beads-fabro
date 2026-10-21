"""The review prompt judges a captured record's currency by comparing TREES.

bd-ib-qnokup: the review prompt's currency section asked whether the latest
record was "posted BEFORE the tree you are reviewing" and told the reviewer to
compare the record's own TIMESTAMP against the branch's commit timestamps. The
engine commits a checkpoint after every node, and `proof_capture`'s own
checkpoint lands AFTER the record is posted, so the head under review is
routinely a commit or two above the sha the record names, seconds later, with
an IDENTICAL tree. Under a timestamp rule every one of those correct records is
stale. Measured 2026-10-20 on two runs: `01M5CE38SZJW` posted at 14:33:47Z for
head `ddb5523d` while the reviewed head `90b906e8` was committed at 14:33:52Z,
and `01M5CDH2FZSE` posted at 16:54:22Z for `67f31db` against a head committed
at 16:54:29Z. Both were rejected round after round as "proof predates the
reviewed head" until the review-fix firing budget ran out.

`SPECIFICATION/contracts.md` ratified the rule in v175, in its account of the
Definition-of-Done and Proof-of-Done stages: a record is CURRENT for a head
under review when the tree of the commit the record names equals the tree of
that head, a commit that changes no tree MUST NOT make a record stale, and no
rule MAY require a record to postdate such a commit. This module binds the
prompt to that rule.

WHY A PROMPT TEST AND NOT A CODE TEST. The currency judgement is made by the
`review` agent out of this prose and is rendered by no Python caller, exactly as
the proof-record disciplines beside this module record. Nothing host-side can
observe that a reviewer compared timestamps: the verdict is a well-formed
blocking finding either way, the run re-enters capture, and the defect surfaces
only as a run that spends its whole firing budget rejecting correct records.

THE PROMPT IS DERIVED FROM THE GRAPH's `review` node rather than named by path,
so this asserts about the file that node actually dispatches: a literal path
keeps passing after the node is re-pointed at a different prompt, which is an
instrument that cannot return the hit it exists to find. The sibling control
asserts the derivation named exactly one such node and that its prompt is on
disk.

THE NEEDLES ARE SCOPED TO THE CURRENCY SECTION, not to the whole prompt. The
prompt separately tells `proof_capture`'s own record to read the publish-branch
head from the forge and says `[BLOCKING]` a dozen times for a dozen unrelated
conditions, so a whole-file probe would be satisfied by prose that has nothing
to do with currency and could then read clean over a section still keyed on
timestamps.

WHITESPACE IS COLLAPSED BEFORE EVERY PROBE. Prompt prose is hard-wrapped, so a
needle straddling a line break fails while the prose says exactly the thing — a
probe that can only fail SILENTLY, which is the failure the tier's conventions
name first.

THE ROUTING CASE IS POSITIVE, NOT AN ABSENCE PROBE. v175 also ratified a
`recapture` routing label, and the graph that carried it was reverted in full
(PR 3416, released v0.229.3) because its added cycle pushed the credential
freshness requirement past a fresh credential's lifetime. So this re-land is
prompt-only and the shipped graph has NO `review -> recapture_route` edge: a
prompt emitting that label would select an edge that does not exist. Rather
than probe for the label's absence — a check that cannot return a hit — the
case ENUMERATES the routing labels the prompt offers and requires exactly the
two the graph has.
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
_REVIEW_NODE = "review"

# The currency section runs from its own `###` heading to the next heading of
# any level. Keyed on the CURRENCY word rather than on the whole heading text so
# a re-worded heading still resolves, while a section that says nothing about
# currency cannot.
_CURRENCY_SECTION = re.compile(
    r"^### [^\n]*\bCURRENT\b[^\n]*$.*?(?=^#{2,3} |\Z)",
    re.DOTALL | re.MULTILINE,
)

# The routing labels the prompt offers, read off its own JSON examples. The
# graph's `review` node has exactly two outbound verdict labels.
_ROUTING_LABEL = re.compile(r'"preferred_next_label":\s*"(?P<label>\w+)"')
_GRAPH_ROUTING_LABELS = {"approve", "fix"}

# The rule itself: what CURRENT means, and the command that decides it. The
# tree-equality definition and the `git diff --quiet` comparison are asserted
# together because either alone is satisfiable by prose the reviewer cannot act
# on — a definition with no command leaves the comparison to be improvised, and
# a command with no definition says nothing about what its exit status means.
_TREE_EQUALITY_RULE = (
    "the TREE of the commit the record names equals the TREE of that head",
    "git diff --quiet <the record's sha> <the head under review>",
    "Exit status 0 means the two commits carry the same tree",
)

# The prohibition, which is the half that was WRONG rather than merely missing.
# A reviewer told what CURRENT means still has the old habit available; the
# measured runs died with their reviewers comparing timestamps, so the section
# has to name every comparison it forbids.
_FORBIDDEN_COMPARISONS = (
    "Do NOT judge currency by timestamp, by sha equality, or by commit order",
    "never require the record to POSTDATE the head",
    "A commit that changes no tree MUST NOT make a record stale",
)

# The reason, which the section must carry IN THE RULE rather than leave to a
# reader. A reviewer cannot tell a tree-identical head from a genuinely newer
# one without knowing that the engine commits after every node.
_CHECKPOINT_REASON = (
    "The engine commits a CHECKPOINT after every node",
    "`proof_capture`'s own checkpoint lands AFTER the record is posted",
)

# The two states that ARE findings, so the rule narrows what currency means
# without retiring the blocking conditions the section already held.
_STILL_BLOCKING = (
    "If no captured record exists on the pull request at all",
    "`[BLOCKING]` finding, not an advisory one",
    "If the record declares NO head at all",
)

# And the routing a blocking finding here earns, stated in the section itself:
# this graph has one blocking route and the re-capture is owed through it.
_FIX_ROUTE = "re-enters `proof_capture` through the review-fix route"


def _review_prompt_files() -> tuple[str, ...]:
    """Prompt filenames of every node named `review` in the committed graph."""
    graph = _GRAPH.read_text(encoding="utf-8")
    names: list[str] = []
    for block in _NODE_BLOCK.finditer(graph):
        if block.group("name") != _REVIEW_NODE:
            continue
        attr = _PROMPT_ATTR.search(block.group("body"))
        assert attr is not None, f"node {_REVIEW_NODE} declares no prompt"
        names.append(attr.group("file"))
    return tuple(names)


_REVIEW_PROMPT_FILES = _review_prompt_files()


def _review_prompt_text() -> str:
    """The committed bytes of the prompt the graph's `review` node dispatches."""
    assert len(_REVIEW_PROMPT_FILES) == 1
    return (_PROMPTS_DIR / _REVIEW_PROMPT_FILES[0]).read_text(encoding="utf-8")


def _collapsed(*, text: str) -> str:
    """`text` with every whitespace run collapsed to one space."""
    return re.sub(r"\s+", " ", text)


def _currency_section() -> str:
    """The one currency section of that prompt, whitespace-collapsed."""
    sections = _CURRENCY_SECTION.findall(_review_prompt_text())
    assert len(sections) == 1, (
        f"the review prompt carries {len(sections)} record-currency sections; expected one. "
        f"A record's currency is judged out of this prose alone, so a prompt with none "
        f"leaves a reviewer to improvise the comparison and a prompt with two lets it "
        f"choose the stale-by-timestamp reading that cost two runs their firing budget"
    )
    return _collapsed(text=sections[0])


def test_the_graph_scan_names_one_review_prompt_that_is_on_disk() -> None:
    """Control: the derivation can return a hit, and the file it names exists."""
    assert len(_REVIEW_PROMPT_FILES) == 1, (
        f"graph declares {len(_REVIEW_PROMPT_FILES)} `{_REVIEW_NODE}` nodes with a prompt; "
        f"expected one"
    )
    named = _PROMPTS_DIR / _REVIEW_PROMPT_FILES[0]
    assert named.is_file(), f"{named} is declared by the graph but absent on disk"


def test_the_currency_section_defines_current_as_tree_equality() -> None:
    """CURRENT means equal TREES, decided by a named `git diff --quiet` comparison."""
    section = _currency_section()

    for phrase in _TREE_EQUALITY_RULE:
        assert phrase in section, (
            f"the record-currency section omits {phrase!r}, so a reviewer has no "
            f"tree-equality test to apply and judges currency by whatever the section "
            f"does offer"
        )


def test_the_currency_section_forbids_timestamp_sha_and_order_comparisons() -> None:
    """No timestamp, no sha equality, no commit order, and no postdating demand."""
    section = _currency_section()

    for phrase in _FORBIDDEN_COMPARISONS:
        assert phrase in section, (
            f"the record-currency section omits {phrase!r}, so the comparison that "
            f"rejected two correct records round after round is still available to a "
            f"reviewer the tree-equality rule was meant to replace"
        )


def test_the_currency_section_gives_the_checkpoint_reason_in_the_rule() -> None:
    """The rule says why a tree-identical head is normal: the engine's checkpoints."""
    section = _currency_section()

    for phrase in _CHECKPOINT_REASON:
        assert phrase in section, (
            f"the record-currency section omits {phrase!r}, so the rule arrives as a "
            f"bare prohibition and a reviewer seeing a head above the record's sha "
            f"cannot tell the ordinary checkpoint case from a genuinely moved tree"
        )


def test_the_currency_section_keeps_an_absent_record_and_an_absent_head_blocking() -> None:
    """Narrowing currency retires neither blocking condition the section held."""
    section = _currency_section()

    for phrase in _STILL_BLOCKING:
        assert phrase in section, (
            f"the record-currency section omits {phrase!r}, so narrowing what makes a "
            f"record stale has also retired a state in which nothing anchors the proof "
            f"at all"
        )


def test_the_currency_section_routes_its_finding_through_this_graphs_fix_label() -> None:
    """A blocking finding here is owed through the review-fix route this graph has."""
    section = _currency_section()

    assert _FIX_ROUTE in section, (
        f"the record-currency section omits {_FIX_ROUTE!r}, so a reviewer holding a "
        f"stale-record finding is not told which route re-earns the capture, and the "
        f"re-capture this graph does offer reads as unavailable"
    )


def test_the_review_prompt_offers_exactly_the_routing_labels_the_graph_has() -> None:
    """The prompt's verdict labels are `approve` and `fix` — the graph's own two."""
    offered = set(_ROUTING_LABEL.findall(_review_prompt_text()))

    assert offered == _GRAPH_ROUTING_LABELS, (
        f"the review prompt offers routing labels {sorted(offered)} while the graph's "
        f"`{_REVIEW_NODE}` node has {sorted(_GRAPH_ROUTING_LABELS)}. A label the graph "
        f"does not carry selects no edge, and a label the prompt never offers is a "
        f"route no verdict can reach"
    )
