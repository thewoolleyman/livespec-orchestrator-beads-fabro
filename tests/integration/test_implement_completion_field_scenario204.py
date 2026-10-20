"""Scenario 204 — an implement turn that reports its work incomplete fails the stage.

`SPECIFICATION/scenarios.md` "Scenario 204" and the paragraph "An implement turn
that ends incomplete does not succeed" of `SPECIFICATION/contracts.md` section
"Self-contained plugin dispatch" (v165). The incident the clause repairs is run
01M58QNY3ZNM2YCVVB9G2383M0 of work-item bd-ib-davaxq: the implement turn ended
with the words "Partial progress only", having committed one configuration
declaration and one test, and the stage was recorded SUCCEEDED because an ACP
node whose turn simply ends succeeds. The run then spent janitor, publish_draft
and proof_capture on that tree before proof_capture found the feature absent and
routed to `fix`, which died at its ceiling building the whole feature in one
turn.

TWO LAYERS, AND NEITHER ESTABLISHES THE OTHER. The committed GRAPH decides where
an incomplete turn routes and what the stage's own completion gate costs, which
no execution of a script can show; the gate's own SCRIPT BYTES decide what counts
as a stated completion, which no reading of the graph can show. The three
sub-scenarios run those bytes against a real clone, so the record the gate reads
is the record a stage would read, and the exit code under assertion is the whole
of the engine's decision — a command node has exactly two outcomes.

WHY THE RECORD IS A FILE AND THE ASSERTION IS NOT "the reply said so". The field
the clause names rides in the turn's final reply, and the only reply field the
ENGINE decides a node's outcome from is the structured ending itself: a reply
stating the work incomplete without that ending still succeeds, and a reply
stating nothing is indistinguishable from a conforming one. No node sees another
node's reply text, so the prompt directs the turn to record the SAME field inside
this clone's own `$GIT_DIR` and the gate reads it there. The committed PROSE half
of that instruction is `tests/prompts/test_implement_completion_field.py`; this
module owns the mechanism it feeds.
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
    default_node_timeouts,
    derive_fabro_timeout_seconds,
    node_timeouts_from_block,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PAYLOAD = _REPO_ROOT / ".claude-plugin" / ".fabro" / "workflows" / "implement-work-item"
_GRAPH = _PAYLOAD / "workflow.fabro"

_GATE = "implement_completion"
_IMPLEMENT = "implement"
_DIFF = "implementation_diff"
_NEEDS_HUMAN = "needs_human"
_JANITOR = "janitor"

# The per-clone record the prompt directs the turn to write and this gate reads,
# resolved through `git rev-parse --git-path` so it lands in the clone's own
# `$GIT_DIR` rather than in the worktree a checkpoint commit would carry.
_RECORD_GIT_PATH = "livespec-implement-completion"
# The stage-cause pair the `needs_human` terminal renders as the recorded
# question, written by the same convention `pr_refresh` writes it with.
_STAGE_CAUSE_GIT_PATH = "livespec-stage-cause"

_PARTIAL_PROGRESS = "LIVESPEC_IMPLEMENT_PARTIAL_PROGRESS"
_COMPLETE_SENTINEL = "LIVESPEC_IMPLEMENT_COMPLETE"

# The two declared spellings of the completion field, as the prompt directs them.
_COMPLETE_FIELD = '{"definition_of_done_complete": true}'
_INCOMPLETE_FIELD = (
    '{"outcome": "failed", "failure_reason": "LIVESPEC_IMPLEMENT_PARTIAL_PROGRESS: '
    'the configuration declaration and one test landed; the feature is not built", '
    '"definition_of_done_complete": false}'
)

# The gate's worst-case visit budget, which is the retryable node it guards:
# `implement` carries `max_retries=1`, so two attempts can each reach it. The
# figure is spelled here because the assertion below is that the gate is billed
# at EXACTLY this count — a node absent from the subprocess-ceiling table is
# billed at ZERO, which is a node the Dispatcher can kill the engine out from
# under, and "greater than zero" would pass for a budget of one.
_GATE_VISITS = 2
# A delta over the fully-defaulted resolution, chosen small and non-round so the
# arithmetic below cannot coincide with any literal the committed graph carries.
_CONFIGURED_DELTA = 137


def _graph_text() -> str:
    return _GRAPH.read_text(encoding="utf-8")


def _edges() -> tuple[tuple[str, str, str], ...]:
    """Every committed edge as (source, target, condition).

    Read through the PRODUCTION graph reader rather than a regular expression of
    this module's own: a second account of the DOT grammar fails by silently
    dropping an edge, and a route never offered looks exactly like one refused.
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


def _gate_script() -> str:
    """The committed gate's own script, decoded by the production reader.

    Taken through `parse_dot_graph` rather than retyped, so what executes below
    is the bytes a stage executes: every arm of this node is shell, and a
    substring assertion cannot tell an arm that RUNS from one sitting behind an
    earlier `exit`.
    """
    parsed = parse_dot_graph(text=_graph_text())
    assert not isinstance(parsed, str), parsed
    return parsed.nodes[_GATE]["script"]


def _clone(*, tmp_path: Path) -> Path:
    """A throwaway git clone, which is what makes the record per-run.

    The gate resolves both its record and its stage-cause file through
    `git rev-parse --git-path`, so a fixture that was not a repository would have
    it fail closed for the wrong reason — and a fixed shared path would let this
    suite, which the janitor stage itself runs, name the state of the very run
    executing it.
    """
    repo = tmp_path / "clone"
    repo.mkdir(parents=True)
    _ = subprocess.run(["git", "init", "--quiet"], cwd=repo, check=True)
    return repo


def _recorded(*, repo: Path, field: str) -> None:
    """Write the completion field as the prompt directs the turn to write it."""
    _ = (repo / ".git" / _RECORD_GIT_PATH).write_text(f"{field}\n", encoding="utf-8")


def _graded(*, repo: Path) -> subprocess.CompletedProcess[str]:
    """Execute the gate's script in one clone and report what it decided."""
    return subprocess.run(
        ["sh", "-c", _gate_script()],
        cwd=repo,
        check=False,
        capture_output=True,
        text=True,
    )


def _stage_cause(*, repo: Path) -> str:
    return (repo / ".git" / _STAGE_CAUSE_GIT_PATH).read_text(encoding="utf-8")


def test_the_implement_turn_reaches_the_completion_gate_before_any_downstream_spend() -> None:
    """The gate sits between the implement turn and the diff breaker, unconditionally.

    POSITION is the assertion, not mere presence. A gate the graph reached after
    janitor, publication or capture would be a gate that fired once the spend the
    clause exists to prevent had already happened — which is exactly the shape of
    the run that motivated it. So the fallthrough out of `implement` must be this
    node, and `implement` must reach neither the breaker nor the janitor directly.

    The gate's own fallthrough is asserted UNCONDITIONAL in the same breath,
    because a node whose every outgoing edge carries a condition is rejected
    before anything runs (`all_conditional_edges`), which took the whole factory
    down twice.
    """
    onward = _targets(source=_IMPLEMENT)
    gate_onward = _targets(source=_GATE)

    assert (_GATE, "") in onward, onward
    assert [target for target, _ in onward if target in (_DIFF, _JANITOR)] == []
    assert (_DIFF, "") in gate_onward, gate_onward
    assert [condition for _, condition in gate_onward if condition == ""] == [""]


def test_an_incomplete_turn_takes_the_same_failure_edge_as_any_other_implement_failure() -> None:
    """The gate's failure edge leads to the terminal an `outcome=failed` implement reaches.

    The clause asks for the SAME failure edge, so both halves are read off the
    committed graph: the gate names `needs_human` as its `outcome=failed` route,
    and `implement` still names that terminal for its own failures. Asserting only
    the gate's edge would pass for a graph that had meanwhile rerouted the
    turn's own failures somewhere else, and the claim is that the two endings
    converge.
    """
    assert (_NEEDS_HUMAN, "outcome=failed") in _targets(source=_GATE)
    assert (_NEEDS_HUMAN, "outcome=failed") in _targets(source=_IMPLEMENT)


def test_a_target_naming_the_completion_gate_in_node_timeouts_is_not_refused() -> None:
    """`dispatcher.node_timeouts.implement_completion` resolves rather than refusing.

    The table is validated before any run exists and its refusal NAMES the key,
    so a repository that wants a different ceiling for this gate must be able to
    ask for one — and this repository does, at a figure far below the graph's own
    default, because the gate is one file read.
    """
    resolved = node_timeouts_from_block(
        block={"node_timeouts": {_GATE: DEFAULT_NODE_TIMEOUT_SECONDS + _CONFIGURED_DELTA}}
    )

    assert not isinstance(resolved, str), resolved
    assert resolved.seconds_for(node=_GATE) == DEFAULT_NODE_TIMEOUT_SECONDS + _CONFIGURED_DELTA


def test_the_configured_value_lands_as_the_literal_timeout_of_the_completion_gate() -> None:
    """The resolved seconds are WRITTEN IN, and read back off the rendered artifact.

    Read back rather than re-derived from the configuration: the pinned engine
    types a quoted duration at PARSE time and the template expansion never
    re-types what it rendered, so a templated timeout yields a STRING the node's
    accessor does not answer for and the node runs with NO TIMEOUT AT ALL,
    silently. The DEFAULTED rendering is the control — without it, "the node
    carries this figure" is equally consistent with a graph that happens to spell
    it as its committed literal.
    """
    configured = node_timeouts_from_block(
        block={"node_timeouts": {_GATE: DEFAULT_NODE_TIMEOUT_SECONDS + _CONFIGURED_DELTA}}
    )
    defaulted = node_timeouts_from_block(block={})
    assert not isinstance(configured, str), configured
    assert not isinstance(defaulted, str), defaulted

    rendered = render_workflow_graph(committed_text=_graph_text(), timeouts=configured)
    control = render_workflow_graph(committed_text=_graph_text(), timeouts=defaulted)

    assert not isinstance(rendered, str), rendered
    assert not isinstance(control, str), control
    assert (
        node_timeout_seconds(graph_text=rendered.text, node=_GATE)
        == DEFAULT_NODE_TIMEOUT_SECONDS + _CONFIGURED_DELTA
    )
    assert node_timeout_seconds(graph_text=control.text, node=_GATE) == DEFAULT_NODE_TIMEOUT_SECONDS


def test_the_completion_gate_is_billed_into_the_fabro_subprocess_ceiling() -> None:
    """The gate carries the visit budget of the retryable turn it guards.

    A node ABSENT from that budget is billed at ZERO, and the figure it feeds is
    the `fabro run` subprocess ceiling — so an unbilled node is one the Dispatcher
    can kill the engine out from under mid-run. The assertion is the EXACT count
    rather than "more than nothing", because a budget of one is reachable by a
    second attempt of the turn this gate guards and would read as correct.
    """
    default_ceiling = derive_fabro_timeout_seconds(timeouts=default_node_timeouts())
    configured = node_timeouts_from_block(
        block={"node_timeouts": {_GATE: DEFAULT_NODE_TIMEOUT_SECONDS + _CONFIGURED_DELTA}}
    )
    assert not isinstance(configured, str), configured

    assert derive_fabro_timeout_seconds(timeouts=configured) == (
        default_ceiling + _GATE_VISITS * _CONFIGURED_DELTA
    )


def test_a_turn_whose_field_reports_the_work_incomplete_fails_the_stage(tmp_path: Path) -> None:
    """Sub-scenario one: a stated incomplete exits NON-ZERO with a partial-progress cause.

    The exit code is the routing — non-zero is the `outcome=failed` edge — and the
    cause is asserted on BOTH surfaces the ending needs it on: the stderr line the
    Dispatcher carries onto the dispatch outcome detail, and the stage-cause file
    the `needs_human` terminal renders as the recorded question. The stage it
    names is `implement`, not this gate: the fault is the turn's, and a question
    naming the gate would send a human to read the wrong stage.
    """
    repo = _clone(tmp_path=tmp_path)
    _recorded(repo=repo, field=_INCOMPLETE_FIELD)

    result = _graded(repo=repo)

    assert result.returncode != 0, result.stderr
    assert _PARTIAL_PROGRESS in result.stderr
    assert _stage_cause(repo=repo).startswith(f"stage: {_IMPLEMENT}\n")
    assert _PARTIAL_PROGRESS in _stage_cause(repo=repo)


def test_a_turn_that_states_no_completion_field_is_treated_as_incomplete(tmp_path: Path) -> None:
    """Sub-scenario two: an unstated completion is partial progress, not a success.

    This is the arm no prompt instruction can carry, and the one the motivating
    run would still fail today without it: a turn that says nothing cannot be
    told from a conforming one by any reading of its reply, so the gate reads the
    ABSENCE as the clause does. The EMPTY record is asserted beside the absent one
    because an emptied file is what a half-written record leaves behind, and a
    `test -f` guard would admit it.
    """
    absent = _clone(tmp_path=tmp_path / "absent")
    empty = _clone(tmp_path=tmp_path / "empty")
    _ = (empty / ".git" / _RECORD_GIT_PATH).write_text("", encoding="utf-8")

    for name, repo in (("absent", absent), ("empty", empty)):
        result = _graded(repo=repo)

        assert result.returncode != 0, (name, result.stderr)
        assert _PARTIAL_PROGRESS in result.stderr, name
        assert _PARTIAL_PROGRESS in _stage_cause(repo=repo), name


def test_a_turn_whose_field_reports_the_work_complete_keeps_its_routing(tmp_path: Path) -> None:
    """Sub-scenario three: a stated complete exits ZERO and leaves no cause behind.

    The control for the two cases above: a script that always exited non-zero
    would satisfy both of them and would stop every conforming run at the gate.
    The ABSENCE of a stage-cause file is asserted with it, because a cause left
    standing by a passing gate is one a LATER stage's failure would be reported
    with — the terminal reads that file whichever stage ended the run.

    BOTH RENDERINGS OF THE SAME FIELD are asserted, because the prompt's
    declared spelling carries one space after the colon while a turn that writes
    compact JSON has stated the field perfectly well — and a gate matching the
    declared bytes literally would read that turn as incomplete and fail a
    finished run with a cause blaming the agent.
    """
    for name, field in (
        ("declared", _COMPLETE_FIELD),
        ("compact", _COMPLETE_FIELD.replace(": ", ":")),
    ):
        repo = _clone(tmp_path=tmp_path / name)
        _recorded(repo=repo, field=field)

        result = _graded(repo=repo)

        assert result.returncode == 0, (name, result.stderr)
        assert _COMPLETE_SENTINEL in result.stderr, name
        assert not (repo / ".git" / _STAGE_CAUSE_GIT_PATH).exists(), name


def test_a_stale_cause_from_an_earlier_stage_does_not_survive_a_passing_gate(
    tmp_path: Path,
) -> None:
    """The gate clears the stage-cause file before deciding, as `pr_refresh` does.

    Its own arms are covered above; what this adds is the INHERITED value. The
    terminal renders whatever that file holds, so a cause written by an earlier
    stage and left standing would be reported as the question for a run that
    failed somewhere else entirely — a confident wrong answer with nothing in the
    record to show it was stale.
    """
    repo = _clone(tmp_path=tmp_path)
    _ = (repo / ".git" / _STAGE_CAUSE_GIT_PATH).write_text(
        "stage: dod_gate\ncause: an earlier stage's finding\n", encoding="utf-8"
    )
    _recorded(repo=repo, field=_COMPLETE_FIELD)

    result = _graded(repo=repo)

    assert result.returncode == 0, result.stderr
    assert not (repo / ".git" / _STAGE_CAUSE_GIT_PATH).exists()
