"""Scenario 132 — the capture half: a draft pull request, then Proof of Done on it.

Binds the `SPECIFICATION/contracts.md` clauses ratified in v114 that this slice
realizes: the Definition-of-Done-and-Proof-of-Done stages clause, for the
`publish_draft` command node and the `proof_capture` ACP node, their positions and
their routing; the Proof-of-Done-record clause, for what the capture prompt must
publish; and the built-in-defaults, ACP-node-list and per-node-timeout tables that
every new node has to appear in before a repository can configure it.

WHY THE EDGE SHAPE IS ASSERTED AND NOT JUST THE NODES. Inserting `publish_draft`
between a green janitor and `review` CONSUMES the janitor's Green edge, and a node
whose every outgoing edge carries a condition is rejected outright by the pinned
engine (`all_conditional_edges`) — the defect that took the whole factory down
twice. So each inserted node names its exceptional routes by condition and leaves
the ordinary route as the unconditional fallthrough that conditional edges
outrank, exactly as `implement -> implementation_diff -> dead_implementer` and
`dod_gate -> implement` already do.

WHY THE SCRIPT BODY IS READ FOR ITS IDEMPOTENCE GUARD. `publish_draft` is a
COMMAND node, so there is no prompt to carry the "open one only when none exists"
duty and no agent to exercise judgement about it — the guard either is in the
script or the second janitor-green entry opens a second pull request. The guard
is therefore asserted on the committed script bytes, which is the only surface
that can carry it.

THE REGISTERED VARIANT IS READ TOO, for the reason `test_workflow_dod_gate_
scenario131` reads it: the same peer clause holds a registered variant to the
reserved workflow's ACP node names so the adapter and timeout layers resolve
against it without naming an absent node, while permitting the variant to leave a
node unreached by its edges. Parity is a relation between two payloads, so the
variant is compared against the BUNDLE rather than against a list restated here.
"""

from __future__ import annotations

import re
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._acp_node_adapters import (
    ACP_NODES,
    NODE_INPUT_CANDIDATES,
)
from livespec_orchestrator_beads_fabro.commands._acp_success_critical import (
    derive_success_critical,
)
from livespec_orchestrator_beads_fabro.commands._acp_workflow_graph import parse_workflow_graph
from livespec_orchestrator_beads_fabro.commands._node_timeouts import (
    DEFAULT_FABRO_TIMEOUT_SECONDS,
    default_node_timeouts,
    derive_fabro_timeout_seconds,
    node_timeouts_from_block,
)

_BUNDLE = Path(".claude-plugin/.fabro/workflows/implement-work-item")
_VARIANT = Path(".fabro/workflows/groom-work-item")
_PUBLISH = "publish_draft"
_CAPTURE = "proof_capture"
_CAPTURE_ADAPTER_INPUT = "proof_capture_adapter"
_ACP_BACKEND = 'backend="acp"'
# A DOT node declaration: a name at the start of a line followed by its attribute
# block. An edge line cannot match — the `^`-anchored name must be followed by the
# bracket with only whitespace between it, and an edge has its arrow and target
# there instead.
_NODE_DECLARATION = re.compile(r"(?m)^[ \t]*(?P<node>\w+)[ \t]*\[(?P<attrs>[^\]]*)\]")


def _dot(*, payload: Path) -> str:
    graph = payload / "workflow.fabro"
    assert graph.is_file(), graph
    return graph.read_text(encoding="utf-8")


def _toml(*, payload: Path) -> str:
    return (payload / "workflow.toml").read_text(encoding="utf-8")


def _node_body(*, text: str, node: str) -> str | None:
    """One node block's body, or `None` when the graph declares no such node."""
    match = re.search(rf"^\s*{node}\s*\[(?P<body>.*?)^\s*\]", text, re.DOTALL | re.MULTILINE)
    return None if match is None else match.group("body")


def _edges(*, text: str) -> list[str]:
    """Every edge line, comments stripped, so a commented example cannot match."""
    return [
        line.strip()
        for line in text.splitlines()
        if "->" in line and not line.strip().startswith("//")
    ]


def _edges_from(*, text: str, node: str) -> list[str]:
    return [edge for edge in _edges(text=text) if edge.startswith(f"{node} ->")]


def _prompt(*, name: str) -> str:
    """One prompt with every whitespace run collapsed to one space.

    The prompts are hard-wrapped, so a needle straddling a line break fails while
    the prose says exactly the thing — a probe that can only fail SILENTLY.
    Collapsing first is what makes these assertions able to return the other
    answer.
    """
    text = (_BUNDLE / "prompts" / name).read_text(encoding="utf-8")
    return re.sub(r"\s+", " ", text)


def _acp_node_names(*, payload: Path) -> set[str]:
    """Every node in one payload's graph the adapter layer has to address."""
    return {
        match.group("node")
        for match in _NODE_DECLARATION.finditer(_dot(payload=payload))
        if _ACP_BACKEND in match.group("attrs")
    }


def test_publish_draft_is_a_command_node_that_pushes_the_publish_branch() -> None:
    """The node is a `script` position, not an agent turn, and it pushes the branch.

    The contract calls `publish_draft` a COMMAND node, which is what makes the
    publish deterministic: a draft that must exist before any capture cannot be
    contingent on a model choosing to create it.

    The branch is named from the run ENVIRONMENT rather than from a workflow
    input, because `CONTRACT_INPUT_NAMES` is a closed set that carries no
    publish-branch name and a script node cannot read the rendered goal the way
    the `pr` prompt does.
    """
    body = _node_body(text=_dot(payload=_BUNDLE), node=_PUBLISH)

    assert body is not None, "the reserved workflow declares no publish_draft node"
    assert _ACP_BACKEND not in body
    assert "shape=parallelogram" in body
    assert "script=" in body
    assert "LIVESPEC_PUBLISH_BRANCH" in body
    assert "git push" in body


def test_publish_draft_opens_a_draft_only_when_no_pull_request_exists() -> None:
    """Idempotence across janitor re-entries, read off the committed script bytes.

    Every accepted fix round re-enters the janitor, so a green janitor is reached
    more than once per run and this node runs again each time. The guard — ask the
    forge for an open pull request on the publish branch, and create one only when
    there is none — is the whole of that idempotence, and a COMMAND node has no
    prompt to carry it anywhere else.

    `--draft` is asserted on the creation call specifically: a pull request opened
    ready would be merged by the repository's automation before any proof was
    captured on it, which is the one outcome the draft exists to prevent.
    """
    body = _node_body(text=_dot(payload=_BUNDLE), node=_PUBLISH)

    assert body is not None
    assert "gh pr list" in body
    assert "--head" in body
    create = body[body.index("gh pr create") :]
    assert "--draft" in create.split(";")[0]


def test_publish_draft_fails_closed_to_needs_human_and_falls_through_to_capture() -> None:
    """An unreachable origin parks the item; the ordinary route is UNCONDITIONAL.

    The contract requires this node to fail closed to `needs_human` when origin
    cannot be reached — a capture posted onto no pull request is not a proof — and
    the fallthrough has to be unconditional or the engine rejects the whole graph
    before any node runs.
    """
    edges = _edges_from(text=_dot(payload=_BUNDLE), node=_PUBLISH)

    assert edges, "publish_draft declares no outgoing edges"
    assert [edge for edge in edges if "condition=" not in edge] == [f"{_PUBLISH} -> {_CAPTURE}"]
    blocked = [edge for edge in edges if edge.startswith(f"{_PUBLISH} -> needs_human")]
    assert len(blocked) == 1
    assert 'condition="outcome=failed"' in blocked[0]


def test_a_green_janitor_reaches_review_only_through_publish_draft_and_capture() -> None:
    """The two nodes sit BETWEEN a green janitor and `review`, not beside it.

    Asserted as the absence of the old direct edge as well as the presence of the
    new one: leaving `janitor -> review` in place would let every run reach the
    reviewer with no draft and no captured record while both new nodes still
    existed, and the graph would look correct.
    """
    text = _dot(payload=_BUNDLE)
    janitor = _edges_from(text=text, node="janitor")

    green = [edge for edge in janitor if "Green" in edge]
    assert len(green) == 1
    assert green[0].startswith(f"janitor -> {_PUBLISH}")
    assert not any(edge.startswith("janitor -> review") for edge in janitor)
    assert [edge for edge in _edges(text=text) if edge.startswith(f"{_CAPTURE} -> review")]


def test_proof_capture_is_an_acp_node_on_its_own_adapter_input() -> None:
    """`proof_capture` is an ACP node whose adapter rides its own input."""
    body = _node_body(text=_dot(payload=_BUNDLE), node=_CAPTURE)

    assert body is not None, "the reserved workflow declares no proof_capture node"
    assert _ACP_BACKEND in body
    assert 'acp.command="{{ inputs.' + _CAPTURE_ADAPTER_INPUT + ' }}"' in body
    assert 'prompt="@prompts/proof-capture.md"' in body
    assert (_BUNDLE / "prompts" / "proof-capture.md").is_file()


def test_proof_capture_is_entered_only_from_publish_draft() -> None:
    """Nothing but `publish_draft` reaches the capture node.

    The contract says "entered only from `publish_draft`", and the reason is the
    pull request: a capture entered from anywhere else could run before any draft
    existed and would have nowhere to post its record.
    """
    edges = _edges(text=_dot(payload=_BUNDLE))

    assert [edge for edge in edges if edge.endswith(f"-> {_CAPTURE}")] == [
        f"{_PUBLISH} -> {_CAPTURE}"
    ]


def test_proof_capture_routes_a_defect_to_fix_and_a_failure_to_needs_human() -> None:
    """A capture needing a code change is an implementation defect, not a park.

    The contract splits the two outcomes deliberately: `preferred_label=fix` routes
    to `fix` because the tree is wrong and the loop can still converge, while a
    failed outcome routes to `needs_human` exactly as every other ACP node's does.
    `review` is the unconditional fallthrough, which is also what keeps
    `all_conditional_edges` from firing on this node.
    """
    edges = _edges_from(text=_dot(payload=_BUNDLE), node=_CAPTURE)

    assert [edge for edge in edges if "condition=" not in edge] == [f"{_CAPTURE} -> review"]
    blocked = [edge for edge in edges if edge.startswith(f"{_CAPTURE} -> needs_human")]
    assert len(blocked) == 1
    assert 'condition="outcome=failed"' in blocked[0]
    defect = [edge for edge in edges if edge.startswith(f"{_CAPTURE} -> fix")]
    assert len(defect) == 1
    assert "preferred_label=fix" in defect[0]


def test_both_new_nodes_carry_a_worst_case_visit_budget() -> None:
    """Lengthening either node's configured timeout lengthens the derived ceiling.

    The `fabro run` subprocess ceiling is derived from the graph's worst-case path,
    so a node absent from that derivation is budgeted at ZERO — the run would be
    killed by the Dispatcher's own subprocess timeout before the node it never
    accounted for could finish. Asserting through the derivation rather than
    against the visit table is what makes this a behaviour test.

    Both nodes are reached once per green janitor, so each carries the review
    node's own visit budget rather than the janitor's: a run whose reviewer asks
    for three fix rounds passes through this pair four times.
    """
    raised = 14400
    for node in (_PUBLISH, _CAPTURE):
        longer = node_timeouts_from_block(block={"node_timeouts": {node: raised}})
        assert not isinstance(longer, str), longer
        assert default_node_timeouts().seconds_for(node=node) == 1800
        assert derive_fabro_timeout_seconds(
            timeouts=longer
        ) == DEFAULT_FABRO_TIMEOUT_SECONDS + 4 * (raised - 1800)


def _declared(*, toml: str, name: str) -> str | None:
    """One `[run.inputs]` string value, in either TOML string spelling.

    A structured adapter default is a JSON object, so it carries double quotes
    of its own and is declared as a TOML LITERAL string. A basic-string-only
    pattern returns `None` for it, and the caller then reports "the workflow
    declares no such input" about an input that is right there.
    """
    match = re.search(
        rf"""^\s*{name}\s*=\s*(?:"(?P<basic>.+)"|'(?P<literal>.+)')""", toml, re.MULTILINE
    )
    if match is None:
        return None
    basic = match.group("basic")
    return match.group("literal") if basic is None else basic


def test_the_bundle_declares_the_capture_adapter_at_the_implementer_default() -> None:
    """The built-in default is the implementer entry, compared line to line.

    The contracts file's built-in-defaults table groups `proof_capture` WITH
    `implement` / `fix` / `review_fix`, so the two lines are compared to each other
    rather than to a model name restated here — a default pinned by copying a
    literal drifts silently the moment the implementer pin moves.
    """
    toml = _toml(payload=_BUNDLE)
    capture = _declared(toml=toml, name=_CAPTURE_ADAPTER_INPUT)
    implement = _declared(toml=toml, name="implement_adapter")

    assert implement is not None
    assert capture is not None, "the reserved workflow declares no proof_capture_adapter input"
    assert capture == implement
    # The control that makes the two assertions above mean anything: the reader
    # CAN return None, so "is not None" is evidence the input is declared rather
    # than evidence the helper never reports an absence.
    assert _declared(toml=toml, name="no_such_adapter") is None


def test_proof_capture_is_a_registered_acp_node_with_its_own_input_candidate() -> None:
    """The adapter layer addresses the capture node, and only through its own input.

    The shared `acp_adapter` is deliberately NOT a candidate. A repository that
    moved the implementer tier must not silently move the capture node with it:
    the capture is what the reviewer and the replay are graded against, so its
    pin is a separate decision.
    """
    assert _CAPTURE in ACP_NODES
    assert NODE_INPUT_CANDIDATES[_CAPTURE] == (_CAPTURE_ADAPTER_INPUT,)


def test_the_capture_node_dominates_every_green_path_so_it_is_success_critical() -> None:
    """The fallback-priority clause names the capture node admission-required.

    Derived from the committed graph rather than asserted as a literal set: the
    capture node is success-critical BECAUSE it sits on the only route from a green
    janitor to publication, and reading that off the dominator derivation is also
    what proves the widened graph is a shape that derivation still understands
    rather than one it refuses.

    `publish_draft` is deliberately NOT expected in this set, and the exclusion is
    asserted rather than merely omitted. The set is the ACP nodes dominating the
    green terminal, because what it gates is per-node ADAPTER FALLBACK — and a
    `script` node has no adapter and so no chain to fall back along. It dominates
    every green path just as hard; it simply is not the kind of thing this
    enumeration admits. Its own budget is covered by the timeout case above.
    """
    critical = derive_success_critical(graph=parse_workflow_graph(text=_dot(payload=_BUNDLE)))

    assert not isinstance(critical, str), critical
    assert _CAPTURE in critical.nodes
    assert _PUBLISH not in critical.nodes


def test_the_registered_variant_declares_the_capture_node_and_leaves_it_unreached() -> None:
    """Peer parity for the names the adapter and timeout layers address.

    A groom-kind variant MAY leave the capture node unreached by its edges, but it
    MUST still DECLARE it, so a repository configuring
    `dispatcher.acp_nodes.proof_capture` or `dispatcher.node_timeouts.proof_capture`
    is not refused for naming a node the variant's own payload lacks. REACHING it
    would try to prove a Definition of Done the groom run has only just written.
    """
    assert _acp_node_names(payload=_VARIANT) == _acp_node_names(payload=_BUNDLE)
    assert re.search(
        rf'^\s*{_CAPTURE_ADAPTER_INPUT}\s*=\s*"', _toml(payload=_VARIANT), re.MULTILINE
    )
    assert not any(_CAPTURE in edge for edge in _edges(text=_dot(payload=_VARIANT)))


def test_the_capture_prompt_authors_and_executes_steps_per_factory_captured_assertion() -> None:
    """Author the steps, then run them VERBATIM — the two halves the contract names.

    Each needle is chosen so it cannot be present unless the prompt carries that
    duty rather than merely mentioning the vocabulary: the execution leg names the
    verbatim requirement that makes the steps replayable by a different adapter,
    and the credential leg names the by-name rule that keeps a value off the
    record.
    """
    prompt = _prompt(name="proof-capture.md")

    assert "factory_captured" in prompt
    assert "Definition of Done order" in prompt
    assert "execute them verbatim" in prompt
    assert "environment-variable name" in prompt
    assert "never a value" in prompt


def test_the_capture_prompt_publishes_the_ratified_record_format() -> None:
    """The first line, the per-assertion body, and the one-new-comment rule.

    The header is asserted as the literal prefix the contract fixes, because every
    downstream reader — the reviewer, the replay, the post-merge pointer and the
    stale-pointer hygiene fact — finds a record by that line and nothing else.
    """
    prompt = _prompt(name="proof-capture.md")

    assert "Proof of Done — captured — run" in prompt
    assert "one NEW comment" in prompt
    assert "MUST NOT be edited after posting" in prompt
    assert "numbered reproduction steps" in prompt
    assert "fenced code block" in prompt
    assert "pending human attestation" in prompt


def test_the_capture_prompt_names_the_asset_naming_form_and_the_store() -> None:
    """Images ride the store seam under the flat name, never the repository tree.

    The ordinal is load-bearing rather than decorative: a `verify` asset is
    compared to the `capture` asset of the SAME ordinal, so a step that does not
    name the ordinal it produces makes the replay uncomparable.
    """
    prompt = _prompt(name="proof-capture.md")

    assert "__capture__" in prompt
    assert "proof-assets" in prompt
    assert "ordinal" in prompt
    assert "MUST NOT be committed" in prompt


def test_the_capture_prompt_leaves_the_tree_unchanged() -> None:
    """A capture that needs a code change is a defect report, not an edit.

    The node is the one surface that could quietly make the tree disagree with
    what the janitor passed and the reviewer is about to read, so the prohibition
    and its routing are both asserted.
    """
    prompt = _prompt(name="proof-capture.md")

    assert "MUST NOT modify the tree" in prompt
    assert '{"preferred_next_label": "fix"}' in prompt


def test_the_pr_prompt_marks_the_existing_draft_ready_instead_of_creating_one() -> None:
    """`pr` no longer creates the pull request; it readies the one already open.

    Asserted in BOTH directions on purpose. The presence of `gh pr ready` alone
    would pass for a prompt that readied a pull request it had just created, which
    is exactly the double-publication this change removes — so the creation verb
    has to be gone from the publishing steps as well.
    """
    prompt = _prompt(name="pr.md")

    assert "gh pr ready" in prompt
    assert "gh pr create" not in prompt
    assert "--auto" in prompt
    assert "publish_draft" in prompt
