"""Scenario 195 — the verified record is graded per assertion before publication.

`SPECIFICATION/scenarios.md` "Scenario 195" and the `proof_grade` /
`proof_grade_route` paragraphs of `SPECIFICATION/contracts.md` section
"Self-contained plugin dispatch" -> "The stages" (v156). The incident the slice
repairs is `bd-ib-rszkjc`, merged as pull request 3130 with a `verified` record
carrying no per-assertion verdict at all: every stage went green, the pull
request merged, and the post-merge acceptance pass then parked the item
NEEDS_ATTENTION with all three assertions pending a Proof of Done record.

Two layers are asserted here and neither can establish the other. The committed
GRAPH decides where a grade failure routes and what timeout the node enforces,
which no execution of the program can show; and the shipped PROGRAM BYTES decide
what counts as a per-assertion verdict, which no reading of the graph can show.
The sub-scenarios that need both run the program's own bytes against a real git
clone with the forge stood in at `gh`, so the record the grade reads is the
record a stage would read.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_dot_graph import parse_dot_graph
from livespec_orchestrator_beads_fabro.commands._dispatcher_graph_render import (
    node_timeout_seconds,
    render_workflow_graph,
)
from livespec_orchestrator_beads_fabro.commands._node_timeouts import (
    DEFAULT_NODE_TIMEOUT_SECONDS,
    node_timeouts_from_block,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PAYLOAD = _REPO_ROOT / ".claude-plugin" / ".fabro" / "workflows" / "implement-work-item"
_GRAPH = _PAYLOAD / "workflow.fabro"

_GRADE = "proof_grade"
_ROUTE = "proof_grade_route"
_VERIFY = "proof_verify"
_REVIEW = "review"
_FIX = "fix"
_NON_CONVERGED = "non_converged"

# The one value the case configures, chosen so it can equal neither the
# fully-defaulted resolution nor any literal the committed graph happens to
# carry: a figure that collided with either would pass for a node whose timeout
# nothing resolved.
_CONFIGURED_SECONDS = 1234


def _graph_text() -> str:
    return _GRAPH.read_text(encoding="utf-8")


def _edges() -> tuple[tuple[str, str, str], ...]:
    """Every edge of the committed graph as (source, target, condition).

    Read through the PRODUCTION graph reader rather than a regular expression
    here: a reader of this module's own would be a second account of the DOT
    grammar, and the way that fails is that it silently drops an edge — a route
    never offered an alternative looks exactly like a route that rejected it.
    """
    parsed = parse_dot_graph(text=_graph_text())
    assert not isinstance(parsed, str), parsed
    return tuple(
        (edge.source, edge.destination, edge.attributes.get("condition", ""))
        for edge in parsed.edges
    )


def _targets(*, source: str) -> list[tuple[str, str]]:
    """One node's outgoing (target, condition) pairs, in declaration order."""
    return [(target, condition) for one, target, condition in _edges() if one == source]


def test_a_target_naming_proof_grade_in_node_timeouts_is_not_refused() -> None:
    """`dispatcher.node_timeouts.proof_grade` resolves rather than refusing.

    The table is validated before any run exists and its refusal NAMES the key,
    so a node the graph does not declare would be rejected there. This is the
    half of Scenario 89's claim that belongs to the new node: a repository that
    wants a different ceiling for the grade must be able to ask for one.
    """
    resolved = node_timeouts_from_block(block={"node_timeouts": {_GRADE: _CONFIGURED_SECONDS}})

    assert not isinstance(resolved, str), resolved
    assert resolved.seconds_for(node=_GRADE) == _CONFIGURED_SECONDS


def test_the_configured_value_lands_as_the_literal_timeout_of_the_proof_grade_node() -> None:
    """The resolved seconds are WRITTEN IN, and read back off the rendered artifact.

    Read back rather than re-derived from the configuration, which is the whole
    point of Scenario 89: the pinned engine types a quoted duration at PARSE time
    and the template expansion never re-types what it rendered, so a templated
    timeout yields a STRING the node's accessor does not answer for and the node
    runs with NO TIMEOUT AT ALL, silently.

    The DEFAULTED rendering is the control. Without it, "the node carries 1234s"
    is equally consistent with a graph that happens to spell 1234s as its
    committed literal, which the rewrite would then have left untouched.
    """
    committed = _graph_text()
    configured = node_timeouts_from_block(block={"node_timeouts": {_GRADE: _CONFIGURED_SECONDS}})
    defaulted = node_timeouts_from_block(block={})
    assert not isinstance(configured, str), configured
    assert not isinstance(defaulted, str), defaulted

    rendered = render_workflow_graph(committed_text=committed, timeouts=configured)
    control = render_workflow_graph(committed_text=committed, timeouts=defaulted)

    assert not isinstance(rendered, str), rendered
    assert not isinstance(control, str), control
    assert node_timeout_seconds(graph_text=rendered.text, node=_GRADE) == _CONFIGURED_SECONDS
    assert (
        node_timeout_seconds(graph_text=control.text, node=_GRADE) == DEFAULT_NODE_TIMEOUT_SECONDS
    )
    assert rendered.node_seconds[_GRADE] == _CONFIGURED_SECONDS


def test_a_grade_failure_re_enters_proof_verify_through_its_own_route_node() -> None:
    """The retry path is `proof_grade_route -> proof_verify`, and nothing else.

    The clause is explicit that "A retry through `proof_grade_route` re-enters
    `proof_verify` DIRECTLY, visits neither `review` nor `fix`, and is charged to
    neither the review-fix budget nor `fix`'s visit cap". That is a claim about
    the GRAPH, so it is read off the committed edges: a route that reached the
    replay by way of `review` would re-review a tree nobody changed and would
    spend one of the three review rounds an item gets for actual findings, while
    one that reached it by way of `fix` would send an implementer to repair code
    the replay already reproduced.

    DIRECTNESS is asserted as the ABSENCE of the two forbidden targets as well as
    the presence of the right one, because "there is an edge to `proof_verify`"
    would be satisfied just as well by a node that also routed to `review` — and
    on this engine an unconditional edge beside a conditional one is reached
    whenever the condition does not match.
    """
    onward = _targets(source=_ROUTE)

    assert (_VERIFY, "") in onward, onward
    assert [target for target, _ in onward if target in (_REVIEW, _FIX)] == []
    assert [target for target, _ in _targets(source=_GRADE) if target == _ROUTE] == [_ROUTE]


def test_the_grade_routes_an_ungradeable_record_to_its_route_node_and_nothing_else() -> None:
    """The failure edge leads to the route node, and the advance stays unconditional.

    Both halves are the assertion, and the second is what keeps the engine
    loading the graph at all: a command node whose every outgoing edge carries a
    condition is rejected outright before anything runs
    (`all_conditional_edges`), which took the whole factory down twice. So the
    ungradeable record is the NAMED exception and `pr_refresh` is the
    fallthrough — never the other way round, which would publish every
    unreadable grade.
    """
    onward = _targets(source=_GRADE)

    assert (_ROUTE, "outcome=failed") in onward, onward
    assert ("pr_refresh", "") in onward, onward
    assert [condition for _, condition in onward if condition == ""] == [""]


def _route_script() -> str:
    """The committed `proof_grade_route` node's own script, decoded by the reader.

    Taken through `parse_dot_graph` rather than retyped, so what executes below is
    the bytes a stage executes: every guard in this node is shell, and a substring
    assertion cannot tell an arm that RUNS from one sitting behind an earlier
    `exit`.
    """
    parsed = parse_dot_graph(text=_graph_text())
    assert not isinstance(parsed, str), parsed
    return parsed.nodes[_ROUTE]["script"]


def _clone(*, tmp_path: Path) -> Path:
    """A throwaway git clone, which is what makes the state directory per-run.

    The route resolves its counter through `git rev-parse --git-path`, so a
    fixture that was not a repository would have it fail closed for the wrong
    reason.
    """
    repo = tmp_path / "clone"
    repo.mkdir(parents=True)
    _ = subprocess.run(["git", "init", "--quiet"], cwd=repo, check=True)
    return repo


def _recorded(*, repo: Path, count: str, finding: str = "an earlier grade failure") -> None:
    """Seed the run's recorded grade-failure count, as `proof_grade` writes it."""
    state = repo / ".git" / "livespec-publication"
    state.mkdir(parents=True, exist_ok=True)
    _ = (state / "livespec-proof-grade-failures").write_text(f"{count}\n", encoding="utf-8")
    _ = (state / "livespec-proof-grade-finding").write_text(f"{finding}\n", encoding="utf-8")


def _routed(*, repo: Path) -> subprocess.CompletedProcess[str]:
    """Execute the route node's script in one clone and report what it decided."""
    return subprocess.run(
        ["sh", "-c", _route_script()],
        cwd=repo,
        check=False,
        capture_output=True,
        text=True,
    )


def test_the_route_retries_while_fewer_than_three_grade_failures_stand(tmp_path: Path) -> None:
    """Zero, one and two recorded failures all exit ZERO, which re-enters the replay.

    Every count below the bound is asserted rather than one of them, because the
    comparison the arm rests on is an inequality and an off-by-one there is
    exactly the defect that either retires the retry on its first use or spends a
    fourth agent turn. The ZERO case is the one a reader is most likely to think
    unreachable: `proof_grade_route` is entered only after a recorded failure, so
    an absent counter means the grade could not record one — and retrying there is
    correct, because the bound has not been reached.
    """
    for count in ("0", "1", "2"):
        repo = _clone(tmp_path=tmp_path / count)
        if count != "0":
            _recorded(repo=repo, count=count)

        result = _routed(repo=repo)

        assert result.returncode == 0, (count, result.stderr)
        assert "LIVESPEC_PROOF_GRADE_RETRY" in result.stderr, count


def test_the_third_recorded_failure_routes_the_run_to_non_converged(tmp_path: Path) -> None:
    """The third failure exits NON-ZERO, which is the edge into `non_converged`.

    The exit code is the whole decision — the engine gives a command node two
    outcomes — so this case and the one above are each other's control: a script
    that always exited zero satisfies the first, and one that always exited
    non-zero satisfies this. The last recorded FINDING is asserted present in the
    output too, because a non-convergence that names no cause sends an operator
    to read three dead stages by hand.
    """
    repo = _clone(tmp_path=tmp_path)
    _recorded(repo=repo, count="3", finding="assertion 2 states no prose verdict")

    result = _routed(repo=repo)

    assert result.returncode != 0, result.stderr
    assert "LIVESPEC_PROOF_GRADE_NON_CONVERGED" in result.stderr
    assert "assertion 2 states no prose verdict" in result.stderr
    assert (_NON_CONVERGED, "outcome=failed") in _targets(source=_ROUTE)


def test_a_counter_nothing_can_compare_routes_to_non_converged_rather_than_retrying(
    tmp_path: Path,
) -> None:
    """A corrupt count is at the bound, not below it.

    This is the fail-closed direction and the one the natural coding of the
    comparison gets WRONG: `test "$count" -ge 3` returns 2 on a non-numeric
    value, which an `if` reads as "below the bound", so a counter nothing can
    compare would retry for ever — spending an agent turn each time until the
    engine's own visit cap aborted the run with no cause for anyone to read.
    """
    repo = _clone(tmp_path=tmp_path)
    _recorded(repo=repo, count="not-a-number")

    result = _routed(repo=repo)

    assert result.returncode != 0, result.stderr
    assert "LIVESPEC_PROOF_GRADE_ROUTE_COUNT_UNREADABLE" in result.stderr
