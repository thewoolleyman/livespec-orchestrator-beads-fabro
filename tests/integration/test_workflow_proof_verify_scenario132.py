"""Scenario 132 — the replay half: review, then an independent `proof_verify`.

Binds the `SPECIFICATION/contracts.md` clauses ratified in v114 that this slice
realizes: the `proof_verify` paragraph of the Definition-of-Done-and-Proof-of-Done
stages clause, for the node, its adapter input, its position between `review` and
`pr` and its whole routing table; the Proof-of-Done-record clause, for what the
replay prompt must publish and under which asset name; and the reviewer mandate
that makes the captured record part of the review rather than a step after it.

WHY THE ROUTING TABLE IS ASSERTED EDGE BY EDGE. `proof_verify` is the last gate
before publication, and three of its four routes are about NOT publishing — so
an edge that is merely missing is indistinguishable, from the graph's shape
alone, from a run that shipped an unreplayed proof. The `pr` edge is asserted to
be CONDITIONAL rather than the fallthrough for the same reason: the contract
forbids any route from this node to `pr` on a verdict other than `verified`, and
an unconditional fallthrough to `pr` would satisfy "there is an edge to pr"
while violating exactly that.

WHY THE VISIT BOUND IS READ OFF THE EDGE AND NOT OFF A `max_visits`. The pinned
engine ABORTS a run at entry to a node that has reached `max_visits`
(`VisitLimitExceeded`) rather than emitting a failed outcome, so no edge could
route the exhaustion onward. The bound therefore has to be the edge guard on the
node's own visit count — the same shape the janitor fix loop uses — and the
absence of a `max_visits` on this node is asserted as part of it.

THE REGISTERED VARIANT IS READ TOO, for the reason the capture and gate modules
read it: the peer clause holds a registered variant to the reserved workflow's
ACP node names so the adapter and timeout layers resolve against it without
naming an absent node, while permitting the variant to leave a node unreached by
its edges. Parity is a relation between two payloads, so the variant is compared
against the BUNDLE rather than against a list restated here.
"""

from __future__ import annotations

import re
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._acp_node_adapters import (
    ACP_NODES,
    NODE_INPUT_CANDIDATES,
)
from livespec_orchestrator_beads_fabro.commands._node_timeouts import (
    DEFAULT_FABRO_TIMEOUT_SECONDS,
    default_node_timeouts,
    derive_fabro_timeout_seconds,
    node_timeouts_from_block,
)

_BUNDLE = Path(".claude-plugin/.fabro/workflows/implement-work-item")
_VARIANT = Path(".fabro/workflows/groom-work-item")
_VERIFY = "proof_verify"
_VERIFY_ADAPTER_INPUT = "proof_verify_adapter"
_VERIFY_PROMPT = "proof-verify.md"
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


def _verify_edges_to(*, target: str) -> list[str]:
    """Every committed `proof_verify -> <target>` edge line."""
    edges = _edges_from(text=_dot(payload=_BUNDLE), node=_VERIFY)
    return [edge for edge in edges if edge.startswith(f"{_VERIFY} -> {target}")]


def _input_value(*, toml: str, name: str) -> str | None:
    """One `[run.inputs]` string value, or `None` when the payload declares none."""
    match = re.search(rf'^\s*{name}\s*=\s*"(?P<value>.+)"', toml, re.MULTILINE)
    return None if match is None else match.group("value")


def _acp_node_names(*, payload: Path) -> set[str]:
    """Every node in one payload's graph the adapter layer has to address."""
    return {
        match.group("node")
        for match in _NODE_DECLARATION.finditer(_dot(payload=payload))
        if _ACP_BACKEND in match.group("attrs")
    }


def _prompt(*, name: str) -> str:
    """One prompt with every whitespace run collapsed to one space.

    The prompts are hard-wrapped, so a needle straddling a line break fails
    while the prose says exactly the thing — a probe that can only fail
    SILENTLY. Collapsing first is what makes these assertions able to return
    the other answer.
    """
    text = (_BUNDLE / "prompts" / name).read_text(encoding="utf-8")
    return re.sub(r"\s+", " ", text)


def test_proof_verify_is_an_acp_node_on_its_own_adapter_input() -> None:
    """An ACP node whose adapter rides its own input, carrying no `max_visits`.

    The absent `max_visits` is asserted rather than merely unmentioned, and it is
    the sharper half. The pinned engine ABORTS a run at entry to a node that has
    reached `max_visits` (`VisitLimitExceeded`) instead of emitting a failed
    outcome, so a `max_visits=3` here would hard-abort on the very visit the
    contract requires to route its third non-reproduction to `non_converged` —
    the graceful bound has to live on the edge guard, and a backstop that
    pre-empts it is not a backstop.
    """
    body = _node_body(text=_dot(payload=_BUNDLE), node=_VERIFY)

    assert body is not None, "the reserved workflow declares no proof_verify node"
    assert _ACP_BACKEND in body
    assert 'acp.command="{{ inputs.' + _VERIFY_ADAPTER_INPUT + ' }}"' in body
    assert f'prompt="@prompts/{_VERIFY_PROMPT}"' in body
    assert 'timeout="1800s"' in body
    assert "max_visits" not in body


def test_the_bundle_declares_the_verify_adapter_off_the_implementer_tier() -> None:
    """The built-in default is the REVIEW entry, compared line to line.

    The contracts file's built-in-defaults table groups `proof_verify` with
    `dod_gate` on the entry the workflow declares for its review input, so the
    two lines are compared to each other rather than to a model name restated
    here — a default pinned by copying a literal drifts silently the moment the
    review pin moves.

    The DISTINCTNESS from the implementer entry is asserted in its own right,
    because that is what the contract actually requires of this node: an adapter
    distinct from the implementer's. A repository that pins a cheap implementer
    has said nothing about how carefully its own proof should be replayed, and a
    replay sharing the implementer's tier is not an independent second leg.
    """
    toml = _toml(payload=_BUNDLE)
    verify = _input_value(toml=toml, name=_VERIFY_ADAPTER_INPUT)
    review = _input_value(toml=toml, name="review_adapter")
    implement = _input_value(toml=toml, name="implement_adapter")

    assert review is not None
    assert implement is not None
    assert verify is not None, "the reserved workflow declares no proof_verify_adapter input"
    assert verify == review
    assert verify != implement


def test_proof_verify_is_a_registered_acp_node_with_its_own_input_candidate() -> None:
    """The adapter layer addresses the replay node, and only through its own input.

    The shared `acp_adapter` is deliberately NOT a candidate, for the reason the
    capture node's own entry records one level up: a repository that moved the
    implementer tier must not silently move this node with it, because the whole
    value of the replay is that it is not the implementer.
    """
    assert _VERIFY in ACP_NODES
    assert NODE_INPUT_CANDIDATES[_VERIFY] == (_VERIFY_ADAPTER_INPUT,)


def test_proof_verify_carries_a_worst_case_visit_budget() -> None:
    """Lengthening the node's configured timeout lengthens the derived ceiling.

    The `fabro run` subprocess ceiling is derived from the graph's worst-case
    path, so a node absent from that derivation is budgeted at ZERO — the run
    would be killed by the Dispatcher's own subprocess timeout before the node it
    never accounted for could finish. Asserting through the derivation rather
    than against the visit table is what makes this a behaviour test.

    THREE visits, not four: the edge guard below admits two non-reproductions and
    routes the third to `non_converged`, so three entries is the most this node
    can consume however the review loop behaves.
    """
    raised = 14400
    longer = node_timeouts_from_block(block={"node_timeouts": {_VERIFY: raised}})

    assert not isinstance(longer, str), longer
    assert default_node_timeouts().seconds_for(node=_VERIFY) == 1800
    assert derive_fabro_timeout_seconds(timeouts=longer) == DEFAULT_FABRO_TIMEOUT_SECONDS + 3 * (
        raised - 1800
    )


def test_the_registered_variant_declares_the_verify_node_and_leaves_it_unreached() -> None:
    """Peer parity for the names the adapter, model and timeout layers address.

    A groom-kind variant MAY leave the replay node unreached by its edges, but it
    MUST still DECLARE it, so a repository configuring
    `dispatcher.acp_nodes.proof_verify` or `dispatcher.node_timeouts.proof_verify`
    is not refused for naming a node the variant's own payload lacks. REACHING it
    would try to replay a proof of a Definition of Done the groom run has only
    just written, against an implementation that does not exist yet.
    """
    assert _acp_node_names(payload=_VARIANT) == _acp_node_names(payload=_BUNDLE)
    assert _input_value(toml=_toml(payload=_VARIANT), name=_VERIFY_ADAPTER_INPUT) is not None
    assert not any(_VERIFY in edge for edge in _edges(text=_dot(payload=_VARIANT)))


def test_a_verified_verdict_is_the_only_thing_that_reaches_pr() -> None:
    """One `pr` edge, and it is CONDITIONAL on the approve label.

    Both halves are the assertion. "There is an edge to `pr`" would be satisfied
    just as well by an unconditional fallthrough — which is precisely the shape
    the contract forbids, because every verdict other than `verified` would then
    publish. So the `pr` edge is asserted to carry a condition, and to be the
    only one of its kind.
    """
    published = _verify_edges_to(target="pr")

    assert len(published) == 1, f"expected exactly one proof_verify -> pr edge, got {published}"
    assert "condition=" in published[0]
    assert "preferred_label=approve" in published[0]


def test_a_non_reproduction_routes_to_fix_under_a_visit_bound_of_three() -> None:
    """`not_reproduced` goes back to `fix`, and only below the third visit.

    The bound is read off the EDGE GUARD rather than off a node attribute, and
    the guard is on this node's OWN visit count — the same shape the janitor fix
    loop uses, for the same engine reason: a `max_visits` abort emits no outcome,
    so nothing could route the exhaustion onward.

    The literal `3` is asserted rather than a rendered input token, because
    `constraints.md` forbids these nodes from referencing an `inputs.*` token
    inside an edge condition: the pinned engine expands graph templates at
    run-create time and an un-expanded token in a condition is a guard that
    never matches.
    """
    repaired = _verify_edges_to(target="fix")

    assert len(repaired) == 1, f"expected exactly one proof_verify -> fix edge, got {repaired}"
    assert "preferred_label=fix" in repaired[0]
    assert "context.internal.node_visit_count < 3" in repaired[0]
    assert "inputs." not in repaired[0]


def test_the_third_non_reproduction_routes_to_the_non_converged_terminal() -> None:
    """Exhaustion reaches the EXISTING terminal, not a new one and not a park.

    `non_converged` is what the Dispatcher reads as `needs-regroom`: a slice
    whose proof will not replay three times running is the empirical too-big
    signal and belongs in grooming. Its guard is asserted as the exact
    complement of the `fix` edge's, so no verdict can fall between the two.
    """
    exhausted = _verify_edges_to(target="non_converged")

    assert len(exhausted) == 1, f"expected one proof_verify -> non_converged edge, {exhausted}"
    assert "preferred_label=fix" in exhausted[0]
    assert "context.internal.node_visit_count >= 3" in exhausted[0]
    assert "inputs." not in exhausted[0]


def test_a_failed_replay_parks_and_an_unmatched_verdict_falls_through_to_needs_human() -> None:
    """The node's two `needs_human` routes, and why the fallthrough is one of them.

    A FAILED outcome is the structured needs-human ending every ACP node here
    shares, weighted so it stays deterministic against the label conditions. The
    UNCONDITIONAL fallback also lands at `needs_human`, and that choice is
    load-bearing twice over: the engine rejects a node whose every outgoing edge
    carries a condition (`all_conditional_edges`, the defect that took the whole
    factory down twice), and of the four possible fallthrough targets it is the
    only one that neither publishes an unreplayed proof nor reports an unreadable
    verdict as a converged non-reproduction.
    """
    edges = _edges_from(text=_dot(payload=_BUNDLE), node=_VERIFY)
    parked = _verify_edges_to(target="needs_human")

    fallthrough = [edge for edge in edges if "condition=" not in edge]
    assert len(fallthrough) == 1, f"expected exactly one unconditional edge, got {fallthrough}"
    assert fallthrough[0].startswith(f"{_VERIFY} -> needs_human")
    assert "unmatched proof_verify outcome" in fallthrough[0]
    assert len(parked) == 2
    blocked = [edge for edge in parked if "condition=" in edge]
    assert len(blocked) == 1
    assert 'condition="outcome=failed"' in blocked[0]
    assert "weight=100" in blocked[0]


def test_the_verify_prompt_exists_and_replays_the_published_steps_verbatim() -> None:
    """Replay, verbatim, on the tree it receives — and author nothing new.

    Each needle is chosen so it cannot be present unless the prompt carries that
    duty rather than merely mentioning the vocabulary: the replay leg names the
    verbatim requirement that makes this a second reading of the SAME steps, and
    the independence leg names the record it replays rather than the Definition
    of Done it might otherwise re-derive.
    """
    path = _BUNDLE / "prompts" / _VERIFY_PROMPT

    assert path.is_file(), f"the reserved workflow ships no {_VERIFY_PROMPT} prompt"
    prompt = _prompt(name=_VERIFY_PROMPT)
    assert "replay" in prompt.lower()
    assert "verbatim" in prompt
    assert "factory_captured" in prompt
    assert "Definition of Done order" in prompt
    assert "environment-variable name" in prompt
    assert "never a value" in prompt


def test_the_verify_prompt_changes_nothing_it_is_grading() -> None:
    """The tree, the steps and the Definition of Done are all read-only here.

    All three prohibitions are asserted, not just the tree one: a replay that
    silently rewrote a step it could not follow would publish a `verified`
    record for steps nobody captured, which is the one failure this stage exists
    to make impossible.
    """
    prompt = _prompt(name=_VERIFY_PROMPT)

    assert "MUST NOT modify the tree" in prompt
    assert "do not rewrite" in prompt.lower()
    assert "Definition of Done" in prompt
    assert "git status --porcelain" in prompt


def test_the_verify_prompt_publishes_one_new_record_carrying_its_verdict() -> None:
    """Both verdict headers verbatim, as the contract fixes them.

    The header is asserted as the literal prefix for each verdict, because every
    downstream reader — the post-merge pointer write, the acceptance pass's proof
    evidence leg and the stale-pointer hygiene fact — finds a record by that line
    and nothing else. Both verdicts are required: a prompt carrying only the
    happy one would pass a one-sided probe while leaving a failed replay with no
    record to publish at all.
    """
    prompt = _prompt(name=_VERIFY_PROMPT)

    assert "Proof of Done — verified — run" in prompt
    assert "Proof of Done — not_reproduced — run" in prompt
    assert "one NEW comment" in prompt
    assert "MUST NOT be edited after posting" in prompt
    assert "pending human attestation" in prompt


def test_the_verify_prompt_names_the_verify_asset_form_and_its_capture_pair() -> None:
    """A `verify` asset is comparable to the `capture` asset of the SAME ordinal.

    The ordinal is the whole of that comparability, so the prompt has to name
    both the `__verify__` stage token the asset name carries and the pairing it
    exists for; a name alone would be satisfied by a record whose proofs no
    reader could line up against the capture.
    """
    prompt = _prompt(name=_VERIFY_PROMPT)

    assert "__verify__" in prompt
    assert "__capture__" in prompt
    assert "ordinal" in prompt
    assert "MUST NOT be committed" in prompt


def test_the_verify_prompt_routes_each_verdict_to_its_label() -> None:
    """The two routing labels, spelled as the graph's own edges read them.

    Asserted on the prompt as well as on the graph because the two halves fail
    independently: an edge keyed on a label no prompt ever emits routes nothing,
    and a label no edge matches falls through to whatever the node's
    unconditional fallback happens to be.
    """
    prompt = _prompt(name=_VERIFY_PROMPT)

    assert '{"preferred_next_label": "approve"}' in prompt
    assert '{"preferred_next_label": "fix"}' in prompt
    assert '{"outcome": "failed"' in prompt
