"""Scenario 138, proof half — a capture finding is the fix stage's work order.

Binds the five gherkin scenarios of `SPECIFICATION/scenarios.md` "Scenario 138"
that concern the PROOF-TO-FIX handoff, and the `SPECIFICATION/contracts.md`
clauses they realize (ratified v115): the proof-findings-are-the-fix-stage's-work-order
paragraph of the Definition-of-Done-and-Proof-of-Done-stages section, and the
`not_captured` verdict the Proof-of-Done-record section adds. That is: the
published record, the visit cap on the capture-to-fix edge, the pull-request
fallback, the unchanged-tree prohibition, and the red-janitor route that must
keep working exactly as it did.

WHAT THIS MODULE DOES NOT BIND, said plainly so the heading's coverage row is
not read as discharged. Scenario 138's remaining gherkin scenarios are about the
PARKED ACCEPTANCE VERDICT — the ledger comment naming the verdict and the
pending legs, the pointer write and its repair, the dispatch result's honest
non-green status, and the dispatch-id attribution. Those belong to requirement
carrier R7's acceptance slice, not to this one, and the row stays `TODO` until a
test binds them.

WHY THE CAP IS `fix.max_visits` AND NOT AN EDGE GUARD — AND NOTE THAT THIS
SECTION SAID THE OPPOSITE UNTIL 2026-10-09. v115 read the cap off an edge guard
on the node's own visit count, for a correct reason: the pinned engine ABORTS a
run at entry to a node that has reached `max_visits`
(`Error::VisitLimitExceeded`) rather than emitting a failed outcome, so no edge
can route the exhaustion onward. That reason still holds; what changed is that
the guard's input does not exist on the engine the factory is moving onto.
`context.internal.node_visit_count` is NOT POPULATED on the Petri-era candidate
(plan `fabro-currency` research note 007, probe p3: a self-loop guarded on it
looped ZERO times, taking the unconditional edge at visit 1), so the guard's
conjunct is permanently false there and the guarded route is unreachable rather
than merely unbounded. Probe p3f showed `max_visits=N` failing the run
deterministically after N firings, which is the only cap that works on both
builds. So the bound moved onto the node and the exhaustion ROUTE was given up
with it — a trade the measurement forces, not a preference.

WHY THE TWO PROOF ROUTES ARE COMPARED TO EACH OTHER. `proof_capture` and
`proof_verify` bound their fix routes the same way for the same engine reason,
so asserting each in its own test would let one drift while both stayed green.
The two conditions are compared as a pair and the shared bound is asserted once.

THE ENGINE LEG IS NOT HERE, DELIBERATELY. Whether the new conditions PARSE on
the engine is a question only `fabro validate` can answer, and this repository
answers it in `check-fabro-graph-validity` — which globs the same payload set,
hands each graph to the engine, and proves the instrument can return a hit by
requiring the engine to REJECT an all-conditional-edges mutant of each graph.
`fabro` is a host artifact and is structurally absent from a CI runner and from
a Fabro sandbox, and this tier may not spawn a subprocess at all
(`check-tests-no-subprocess-spawn`), so duplicating that leg here would be a
test that cannot run where it matters.
"""

from __future__ import annotations

import re
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_record import (
    PROOF_RECORD_VERDICTS,
)

_BUNDLE = Path(".claude-plugin/.fabro/workflows/implement-work-item")
_CAPTURE = "proof_capture"
_VERIFY = "proof_verify"
# The record header, as the contract fixes it: the title, the em dash, the
# verdict, then the `run ` introducer. Both prompts render it verbatim and every
# downstream reader finds a record by this line and nothing else.
_RECORD_HEADER = re.compile(r"Proof of Done — (?P<verdict>\S+) — run ")
_VISIT_COUNT = "context.internal.node_visit_count"


def _dot() -> str:
    graph = _BUNDLE / "workflow.fabro"
    assert graph.is_file(), graph
    return graph.read_text(encoding="utf-8")


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


def _source_of(*, edge: str) -> str:
    return edge.split("->", 1)[0].strip()


def _target_of(*, edge: str) -> str:
    """One edge's target NODE NAME, tokenized rather than prefix-matched.

    A prefix test is wrong here and wrong in the dangerous direction: `fix` is a
    prefix of nothing in this graph, but `pr` is a prefix of `proof_capture`, so
    a `startswith` family of helpers invites exactly the confusion that makes a
    "nothing reaches X" assertion unable to fail.
    """
    return edge.split("->", 1)[1].strip().split(maxsplit=1)[0]


def _edges_from(*, node: str) -> list[str]:
    return [edge for edge in _edges(text=_dot()) if _source_of(edge=edge) == node]


def _edge(*, source: str, target: str) -> str:
    """The ONE edge between two nodes, asserted to be unique as it is fetched.

    Uniqueness is part of every claim this module makes about routing: a second
    edge with a looser guard would satisfy "an edge with this condition exists"
    while routing the traffic the guard was written to stop.
    """
    found = [edge for edge in _edges_from(node=source) if _target_of(edge=edge) == target]
    assert len(found) == 1, f"expected exactly one {source} -> {target} edge, got {found}"
    return found[0]


def _condition_of(*, edge: str) -> str:
    """One edge's `condition="..."` value, asserted present as it is fetched."""
    match = re.search(r'condition="(?P<condition>[^"]*)"', edge)
    assert match is not None, f"edge carries no condition: {edge}"
    return match.group("condition")


def _prompt(*, name: str) -> str:
    """One prompt with every whitespace run collapsed to one space.

    The prompts are hard-wrapped, so a needle straddling a line break fails
    while the prose says exactly the thing — a probe that can only fail
    SILENTLY. Collapsing first is what makes these assertions able to return the
    other answer.
    """
    path = _BUNDLE / "prompts" / name
    assert path.is_file(), path
    return re.sub(r"\s+", " ", path.read_text(encoding="utf-8"))


def test_the_capture_prompt_publishes_a_not_captured_record_for_its_finding() -> None:
    """The finding survives the run as a record, not only as stage output.

    The contract gives the finding TWO routes to `fix` — the engine's preamble of
    preceding stage output, and the stage's own record on the pull request — and
    the second exists because the first can be lost. A capture stage that routed
    to `fix` while publishing nothing would satisfy the routing half and leave a
    run whose only account of the defect dies with its preamble.

    The verdict word is read OUT OF THE PROMPT and checked against the product
    enumeration rather than compared to a literal written here. That is what
    binds the two halves of this slice to each other: a prompt publishing a word
    the reader's closed verdict set does not carry produces a comment the reader
    DROPS, and the drop is indistinguishable from a stage that published nothing.
    """
    prompt = _prompt(name="proof-capture.md")

    verdicts = {match.group("verdict") for match in _RECORD_HEADER.finditer(prompt)}
    assert "not_captured" in verdicts, f"the capture prompt renders no such header: {verdicts}"
    assert verdicts <= set(PROOF_RECORD_VERDICTS), verdicts - set(PROOF_RECORD_VERDICTS)
    assert "assertion text, verbatim" in prompt
    assert "FINDING" in prompt
    assert "what you observed" in prompt
    assert "one NEW comment" in prompt
    assert "never an edit of an earlier record" in prompt
    assert '{"preferred_next_label": "fix"}' in prompt


def test_the_capture_prompt_still_refuses_to_touch_the_tree_while_reporting() -> None:
    """Publishing the finding is not a licence to repair it.

    This is the one regression the record duty could plausibly introduce: the
    section that now writes a record is the same section that must NOT write
    code, and a prompt gaining a publish step while losing the read-only
    prohibition would route a defect to `fix` with the tree already changed
    underneath the janitor that passed it and the reviewer about to read it.
    """
    prompt = _prompt(name="proof-capture.md")

    assert "MUST NOT modify the tree" in prompt
    assert "do not edit anything" in prompt.lower()
    assert "IMPLEMENTATION DEFECT" in prompt
    assert "git status --porcelain" in prompt


def test_a_capture_finding_routes_to_fix_bounded_by_the_shared_fix_budget() -> None:
    """`preferred_label=fix` goes to `fix`, and `fix.max_visits` is what bounds it.

    v115 bounded this edge with a `context.internal.node_visit_count < 3` guard,
    for the sound reason that a `max_visits` abort emits no outcome and so cannot
    be routed onward. Plan `fabro-currency` P4 removed the guard because the key
    it reads IS NOT POPULATED on the Petri-era engine (research note 007, probe
    p3): the conjunct is permanently false there, so a capture finding could
    never reach `fix` at all and would slip into the unconditional `review`
    fallthrough — reaching the reviewer with the defect unreported, which is the
    one outcome this edge exists to prevent. Routing on `preferred_label` alone
    behaves identically on both engines.

    The absent `inputs.` token is asserted in its own right. `constraints.md`
    forbids these nodes from referencing an `inputs.*` token inside an edge
    condition, and the Petri-era engine rejects one at load with
    `attractor.condition.syntax` — a bound written that way does not merely fail
    to bind, it refuses the whole graph.
    """
    repaired = _edge(source=_CAPTURE, target="fix")

    assert _condition_of(edge=repaired) == "preferred_label=fix"
    assert _VISIT_COUNT not in repaired
    assert "inputs." not in repaired
    assert "max_visits=" in (_node_body(text=_dot(), node="fix") or "")


def test_capture_exhaustion_has_no_routed_terminal_on_this_engine() -> None:
    """The exhaustion EDGE is gone, and its absence is the assertion.

    v115 paired the `< 3` guard with a complementary `>= 3` edge to
    `non_converged`, so no third `fix` verdict could fall past both conditions
    into the `review` fallthrough. Plan `fabro-currency` P4 removed BOTH, because
    the visit-count key is not populated on the Petri-era engine and a
    half-removed pair is the gap the complement existed to close.

    WHAT THAT COSTS, asserted rather than left implicit: capture-loop exhaustion
    no longer reaches `non_converged` and no longer emits LIVESPEC_NON_CONVERGED
    for the Dispatcher to read as `needs-regroom`. It arrives instead as a
    `fix.max_visits` RUN FAILURE. Restoring a routed exhaustion needs a counter
    the engine will evaluate in a condition, which this engine does not supply.
    """
    targets = {_target_of(edge=edge) for edge in _edges_from(node=_CAPTURE)}

    assert "non_converged" not in targets
    assert _VISIT_COUNT not in "".join(_edges_from(node=_CAPTURE))


def test_the_two_proof_fix_routes_are_one_bound_rather_than_two_literals() -> None:
    """The capture route and the replay route are compared to each other.

    Both nodes bound their fix route the same way for the same engine reason, so
    asserting each in its own test would let one drift while both stayed green.
    Since plan `fabro-currency` P4 the shared bound is `fix.max_visits` and the
    shared edge condition is `preferred_label=fix` with NO visit term, which is
    asserted as an identity between the two rather than as two substring hits.
    """
    conditions = {
        node: _condition_of(edge=_edge(source=node, target="fix")) for node in (_CAPTURE, _VERIFY)
    }

    assert conditions[_CAPTURE] == conditions[_VERIFY] == "preferred_label=fix"
    # Neither node routes an exhaustion any more, which is the half that would
    # otherwise drift apart silently.
    for node in (_CAPTURE, _VERIFY):
        assert "non_converged" not in {
            _target_of(edge=edge) for edge in _edges_from(node=node)
        }, node
    bound = re.search(r"max_visits=(?P<value>\d+)", _node_body(text=_dot(), node="fix") or "")
    assert bound is not None


def test_review_remains_the_capture_nodes_only_unconditional_route() -> None:
    """Adding the exhaustion edge did not take the fallthrough position.

    The engine REJECTS a node whose every outgoing edge carries a condition
    (`all_conditional_edges`) before any node runs — the defect that took this
    factory down twice — so the fallthrough is load-bearing. It must also still
    be `review`: the ordinary path is a successful capture, and moving the
    fallthrough to a terminal would strand every clean run.
    """
    edges = _edges_from(node=_CAPTURE)

    assert [edge for edge in edges if "condition=" not in edge] == [f"{_CAPTURE} -> review"]
    assert {_target_of(edge=edge) for edge in edges} == {
        "needs_human",
        "fix",
        "review",
    }


def test_the_fix_budget_is_shared_across_every_loop_feeding_it() -> None:
    """`fix.max_visits` is THE bound now, and it is shared by three producers.

    Until plan `fabro-currency` P4 each producer carried its own graceful `< 3`
    edge guard and this attribute was the abort backstop sitting strictly above
    their sum — six reachable entries behind three separate caps. Those guards
    are gone (the key is not populated on the Petri-era engine), so the three
    loops now draw on this ONE budget and exhausting it is a run FAILURE rather
    than a route.

    The arithmetic is kept as a floor rather than dropped: the budget must still
    admit at least two entries per producer, or a single misbehaving loop could
    starve the others of any attempt at all. The PRODUCER COUNT is the tripwire —
    a fourth node routing into `fix` would re-open this silently, and this is the
    assertion that notices.
    """
    text = _dot()
    producers = {
        _source_of(edge=edge) for edge in _edges(text=text) if _target_of(edge=edge) == "fix"
    }

    assert producers == {"janitor", _CAPTURE, _VERIFY}
    backstop = re.search(r"max_visits=(?P<value>\d+)", _node_body(text=text, node="fix") or "")
    assert backstop is not None
    # AT LEAST two entries per producer, not strictly more: the budget IS the
    # bound now rather than a backstop sitting above three separate caps, and it
    # is sized to exactly what those retired caps admitted (plan
    # `fabro-currency` P4), which is two apiece.
    assert int(backstop.group("value")) >= 2 * len(producers)


def test_the_fix_prompt_reads_the_pull_request_when_the_preamble_carries_none() -> None:
    """The second route is named, and the failed outcome is moved behind it.

    Before v115 a preamble with no finding was itself the blocker: the prompt
    sent the stage straight to the failed outcome. The record on the pull request
    is the other route the contract requires the finding to travel, so an
    unreadable preamble is an instruction to read that route — and only the
    absence of BOTH is missing or unreadable.

    The needles name the record's own header prefix and the verdicts that carry a
    finding, because a prompt merely saying "read the proof record" would pass a
    looser probe while pointing at nothing a reader could find.
    """
    prompt = _prompt(name="fix.md")

    assert "Proof of Done — " in prompt
    assert "not_captured" in prompt
    assert "not_reproduced" in prompt
    assert "gh pr list --head" in prompt
    assert "LATEST" in prompt
    assert "preamble carries no finding AND the pull request carries no such record" in prompt
    assert "missing or unreadable" in prompt
    assert '{"outcome": "failed"' in prompt


def test_the_fix_prompt_forbids_succeeding_on_an_unchanged_tree() -> None:
    """A proof finding ends in a tree change or in the needs-human ending.

    This is the failure the two stranded overseer runs actually hit: the fix
    stage knew only a red janitor, found the checks green, changed nothing and
    reported success, and the run ended with the defect unaddressed and its draft
    stranded. Both permitted endings are asserted together, because a prompt
    carrying only the prohibition leaves the stage with nowhere legitimate to go
    and would turn every disputed finding into a hang.
    """
    prompt = _prompt(name="fix.md")

    assert "MUST NOT end succeeded with an unchanged tree" in prompt
    assert "tree change" in prompt.lower()
    assert "stating why the finding is wrong" in prompt
    assert "green janitor does not discharge" in prompt
    assert "git status --porcelain" in prompt


def test_a_step_that_runs_a_program_must_publish_that_programs_source() -> None:
    """A published step is replayable only if its PROGRAM travels with it.

    This is the defect that graded this slice's own first capture
    `not_reproduced`, which is why it belongs beside the routing cases rather
    than in a prompt-prose module: the capture authored a step reading "with the
    program shown in the capture", fed a heredoc to `python -`, and published the
    invocation line and the program's STDOUT with no heredoc body. Steps 1 and 2
    of that assertion reproduced and showed the committed source was correct, so
    nothing about the implementation was wrong — the RECORD was unreplayable, and
    an unreplayable step grades the assertion as if the code had failed.

    BOTH prompts are asserted in one case because the duty is a pair and either
    half alone is satisfiable by a round trip that still loses the program. A
    capture rule with no verify rule leaves a verifier free to reconstruct the
    program from its output and bank a green no later replay can earn; a verify
    rule with no capture rule turns every such record into a non-reproduction
    with nothing upstream obliged to prevent it.

    The needles name the OUTPUT-IS-NOT-SOURCE clause specifically, not merely the
    words "program" or "source". A prompt already says both of those things
    several times over, so a probe reaching for them would pass against the very
    prompt that permitted this defect — it could not return the other answer.
    """
    capture = _prompt(name="proof-capture.md")
    verify = _prompt(name="proof-verify.md")

    # The capture side: the program's own text is part of the record.
    assert "Self-contained in its PROGRAM TEXT" in capture
    assert "COMPLETE SOURCE" in capture
    assert "heredoc into an interpreter" in capture
    assert (
        "Publishing only the invocation line and the program's OUTPUT does not satisfy" in capture
    )
    assert "UNREPLAYABLE" in capture
    # And the duty is restated where the comment body is enumerated, because the
    # body list is the surface the publishing step actually works from.
    assert "COMPLETE SOURCE of any program it runs" in capture

    # The verify side: a missing program is graded, never rebuilt.
    assert "Never reconstruct a missing program" in verify
    assert "you may not infer that source from the output" in verify
    assert "a test of a program YOU wrote" in verify

    # Instrument control: these are substring probes over a collapsed prompt, so
    # one needle that is deliberately absent proves they can still return False.
    # Without it, a helper silently returning something truthy for every query
    # would make every assertion above pass against any prompt at all.
    #
    # The needle is the PERMISSION this rule withdraws, and it is chosen that way
    # on purpose. The obvious control — the offending phrase "with the program
    # shown in the capture" — is WRONG here and wrong in the direction that reads
    # as a real finding: the new rule QUOTES that phrase as the promise it makes
    # binding, so the probe hits the rule itself. Presence is not assertion, and a
    # control has to key on something no correct prompt can contain.
    assert "output alone is sufficient" not in capture


def test_a_red_janitor_still_reaches_fix_with_its_failure_output() -> None:
    """The unchanged half, asserted as a regression guard rather than as news.

    The contract says a `fix` visit entered from a red janitor is unchanged and
    receives the janitor's failure output as before, so this case is expected to
    have passed before the capture cap existed — that is the point of it. The
    janitor edge is asserted to carry NO `preferred_label` term, because the
    plausible regression is a proof-shaped guard copied onto an edge whose source
    emits no label at all, which would route every red janitor to the
    fallthrough.

    The `summary:high` fidelity is read off the node because the preamble route
    depends on it: compact mode omits agent responses, so a janitor failure would
    arrive stripped of the output step 1 of the prompt tells the stage to read.
    """
    red = _edge(source="janitor", target="fix")
    prompt = _prompt(name="fix.md")

    assert _condition_of(edge=red) == "outcome!=succeeded"
    assert _VISIT_COUNT not in red
    assert "preferred_label" not in red
    assert 'fidelity="summary:high"' in (_node_body(text=_dot(), node="fix") or "")
    assert "janitor failure output" in prompt
    assert "red gate" in prompt
