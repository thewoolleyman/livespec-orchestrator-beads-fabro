"""How one resumed run enters at its unfinished stage, on the published head.

`SPECIFICATION/contracts.md` section "Resume from a published pull request
(`resume --item`)" requires the resumed run to run "the workflow the earlier run's
dispatch record names, with a sandbox that checks out the publish branch at the
published head, entered at the resumed-at stage", and to visit neither `dod_gate`
nor `implement` nor "any other node the earlier run completed". It then names the
latitude this module takes and bounds it: whether the engine is entered at the
node directly "or through a graph the Dispatcher derives from that workflow for
the one run is implementation surface", and "a derived graph is not a registered
variant, is never selectable by the variant precedence, and is never recorded as
the item's workflow."

TWO HALVES, AND THEY FAIL DIFFERENTLY. The graph rewrite decides WHICH STAGE runs;
the prepare step decides WHICH TREE it runs on. Either alone is worse than
neither: entering at `pr` on the default branch publishes nothing the records
describe, and checking out the published head while entering at `dod_gate` spends
a whole sandbox re-implementing work that is already on the branch.

WHY THE REWRITE MOVES THE `start` EDGE RATHER THAN DELETING NODES. Deleting
`dod_gate` and `implement` would satisfy "no visit" and break every edge pointing
at them — `implement -> needs_human`, `implementation_diff -> dead_implementer` —
so the graph would stop validating and the dispatch would die at run-create with
an error about a graph the operator never wrote. Moving the one edge leaves every
node declared and simply UNREACHABLE from `start`, which makes the clause's "no
such visit" a property of the graph rather than a hope about the engine.

WHY AN UNDECLARED NODE REFUSES HERE. The resumed-at stage can come from a factory
run record, which names whatever node THAT engine was executing — possibly a node
this workflow does not declare, if the earlier run ran a different variant.
Pointing `start` at an undeclared name yields a graph that fails validation at
run-create time, which reads as a Dispatcher fault; refusing here names the real
cause, before any run exists.

WHY THE CHECKOUT FETCHES THE BRANCH AND THEN TAKES THE HEAD FROM IT. A forge does
not reliably serve a bare sha (`uploadpack.allowReachableSHA1InWant` is off by
default), so the BRANCH is fetched and the head is checked out from what arrived —
which has the second virtue of proving the head is on that branch rather than
merely reachable somewhere in the repository. And the step fails the run when it
cannot land: a swallowed failure would run the resumed stage against whatever the
clone happens to carry, which is the default branch, and publish a record for a
tree nobody proved.
"""

from __future__ import annotations

import argparse
import re
import shlex
from dataclasses import dataclass

__all__: list[str] = [
    "RESUME_ENTRY_NODE_ARG",
    "RESUME_HEAD_ARG",
    "ResumeCheckout",
    "graph_entered_at",
    "resume_checkout_for",
    "resume_checkout_prepare_steps_block",
]

# The two `argparse.Namespace` attributes a resume carries into the ordinary
# dispatch path. Named constants rather than literals because they are read
# DEFENSIVELY at two seams that no other command sets them at, and a typo at
# either read is invisible: the attribute simply resolves absent, the dispatch
# proceeds as a plain one, and the resumed run re-implements from `start`.
RESUME_ENTRY_NODE_ARG = "resume_entry_node"
RESUME_HEAD_ARG = "resume_head"

# The unconditional `start` edge, as the committed graph spells it: a bare
# `start -> <target>` line carrying no attribute list. The CONDITIONAL form is
# deliberately not matched — `start` carries exactly one outgoing edge, and fabro
# rejects a node whose every outgoing edge is conditional, so a conditional
# `start` edge is a graph that could never have run.
_START_EDGE = re.compile(r"(?m)^(?P<indent>[ \t]*)start[ \t]*->[ \t]*(?P<target>\w+)[ \t]*$")

# A node DECLARATION: a bare name at line start followed directly by its
# attribute bracket. The same shape `_dispatcher_graph_render` matches, and for
# the same reason — an edge line never matches, because the name must be followed
# by the bracket with nothing between.
_NODE_DECLARATION = r"(?m)^[ \t]*{name}[ \t]*\["

_NODE_NAME = re.compile(r"^\w+$")


@dataclass(frozen=True, kw_only=True)
class ResumeCheckout:
    """The publish branch and head one resumed run's sandbox is placed on.

    A pair rather than the head alone, because the fetch needs the BRANCH and the
    checkout needs the HEAD, and taking the head from a branch tip read at
    prepare time would defeat the whole point: the tip may have moved since the
    record was published, which is precisely the state the head-moved refusal
    exists to catch.
    """

    branch: str
    head: str


def graph_entered_at(*, graph_text: str, node: str) -> str | None:
    """The one run's derived graph, entered at `node`, or `None` when it cannot be.

    `None` for three conditions, each of which would otherwise produce a graph
    that fails at run-create time rather than a refusal an operator can read: a
    node this workflow does not declare, a node name that is not a bare
    identifier (so it could never be one), and a graph carrying no unconditional
    `start` edge to move.
    """
    if _NODE_NAME.match(node) is None:
        return None
    if re.search(_NODE_DECLARATION.format(name=re.escape(node)), graph_text) is None:
        return None
    edge = _START_EDGE.search(graph_text)
    if edge is None:
        return None
    replacement = f"{edge.group('indent')}start -> {node}"
    return graph_text[: edge.start()] + replacement + graph_text[edge.end() :]


def resume_checkout_prepare_steps_block(*, checkout: ResumeCheckout | None) -> str:
    """The prepare step that puts the sandbox clone on the published head.

    Rendered as the LAST appended prepare step, which is where the overlay places
    it: the committed steps provision the clone — unshallowing it, installing the
    toolchain and the hooks — and every one of those acts on `.git` or on
    untracked state that a checkout does not disturb, while a checkout performed
    BEFORE them would be unshallowed out from under.

    `""` for no resume, byte-for-byte what the overlay carried before this
    existed, so an ordinary dispatch is untouched by the resume path.
    """
    if checkout is None:
        return ""
    script = " && ".join(
        (
            "set -e",
            f"git fetch --no-tags origin {shlex.quote(f'refs/heads/{checkout.branch}')}",
            f"git checkout --detach {shlex.quote(checkout.head)}",
        )
    )
    return (
        "\n# --- Dispatcher-materialized resume checkout: the publish branch at the\n"
        "# --- head the anchoring Proof of Done record names ---\n"
        "[[run.prepare.steps]]\n"
        f"script = {_toml_basic_string(value=script)}\n"
    )


def resume_checkout_for(*, args: argparse.Namespace, branch: str) -> ResumeCheckout | None:
    """The checkout this dispatch is a resume ONTO, or `None` for a plain dispatch.

    The head is read off the invocation rather than from the branch tip, and the
    difference is the whole guarantee: a tip read here, at prepare time, may have
    moved since the anchoring record was published — which is exactly the state
    the head-moved refusal exists to catch, so resolving it here would quietly
    undo that refusal for every resume that got past it.

    Read DEFENSIVELY, because every dispatch entry point reaches the overlay
    through this seam and only the resume one sets these attributes.

    The BRANCH is a parameter rather than derived here from the work-item id,
    because the one function that derives it lives downstream of the engine and
    importing it would close a cycle through the overlay this module feeds. The
    caller already holds the item, so it is the party with nothing to resolve.
    """
    head = getattr(args, RESUME_HEAD_ARG, None)
    if not isinstance(head, str) or not head:
        return None
    return ResumeCheckout(branch=branch, head=head)


def _toml_basic_string(*, value: str) -> str:
    """One TOML basic string, escaping what a basic string cannot carry raw.

    Spelled here rather than borrowed from the overlay's own escaper because this
    module must not import the overlay: the overlay imports THIS one to render the
    block, and the reverse edge would close a cycle.
    """
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'
