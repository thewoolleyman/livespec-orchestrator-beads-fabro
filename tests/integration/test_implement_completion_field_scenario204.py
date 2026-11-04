"""Scenario 204 — a Green turn that reports its work incomplete fails the stage.

`SPECIFICATION/scenarios.md` "Scenario 204" and the paragraph "An implement turn
that ends incomplete does not succeed" of `SPECIFICATION/contracts.md` section
"Self-contained plugin dispatch" (v165, carried by v262 onto the Green node).

TWO LAYERS, AND NEITHER ESTABLISHES THE OTHER. The committed GRAPH decides where
an incomplete turn routes and what the gate costs, which no execution of a script
can show; the gate's own SCRIPT BYTES decide what counts as a stated completion,
which no reading of the graph can show. The sub-scenarios run those bytes against
a real clone, so the exit code under assertion is the whole of the engine's
decision — a command node has exactly two outcomes.

The record is a file as well as the reply field because no node sees another
node's reply text: the gate reads the Green reply on stdin first and falls back to
the per-clone record inside `$GIT_DIR`. The committed PROSE half of that
instruction is `tests/prompts/test_implement_completion_field.py`.
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
_GRAPH = (
    _REPO_ROOT
    / ".claude-plugin"
    / ".fabro"
    / "workflows"
    / "implement-work-item"
    / "workflow.fabro"
)

_GATE = "implement_completion"
_GREEN = "green"
_COMMIT_GREEN = "commit_green"
_DIFF = "implementation_diff"
_NEEDS_HUMAN = "needs_human"
_JANITOR = "janitor"

_RECORD_GIT_PATH = "livespec-implement-completion"
_STAGE_CAUSE_GIT_PATH = "livespec-stage-cause"

_PARTIAL_PROGRESS = "LIVESPEC_IMPLEMENT_PARTIAL_PROGRESS"
_COMPLETE_SENTINEL = "LIVESPEC_IMPLEMENT_COMPLETE"

_COMPLETE_FIELD = '{"definition_of_done_complete": true}'
_INCOMPLETE_FIELD = (
    '{"outcome": "failed", "failure_reason": "LIVESPEC_IMPLEMENT_PARTIAL_PROGRESS: '
    'the configuration declaration and one test landed; the feature is not built", '
    '"definition_of_done_complete": false}'
)

# The gate sits behind `green`, which can be visited three times, so it is billed
# at EXACTLY three: a node absent from the ceiling table is billed at ZERO, and
# "greater than zero" would pass for a budget of one.
_GATE_VISITS = 3
_CONFIGURED_DELTA = 137


def _graph_text() -> str:
    return _GRAPH.read_text(encoding="utf-8")


def _edges() -> tuple[tuple[str, str, str], ...]:
    """Every committed edge as (source, target, condition), via the production reader."""
    parsed = parse_dot_graph(text=_graph_text())
    assert not isinstance(parsed, str), parsed
    return tuple(
        (edge.source, edge.destination, edge.attributes.get("condition", ""))
        for edge in parsed.edges
    )


def _targets(*, source: str) -> list[tuple[str, str]]:
    return [(target, condition) for one, target, condition in _edges() if one == source]


def _gate_script() -> str:
    """The committed gate's own script, decoded by the production reader."""
    parsed = parse_dot_graph(text=_graph_text())
    assert not isinstance(parsed, str), parsed
    return parsed.nodes[_GATE]["script"]


def _clone(*, tmp_path: Path) -> Path:
    """A throwaway git clone, which is what makes the record per-run."""
    repo = tmp_path / "clone"
    repo.mkdir(parents=True)
    _ = subprocess.run(["git", "init", "--quiet"], cwd=repo, check=True)
    return repo


def _recorded(*, repo: Path, field: str) -> None:
    _ = (repo / ".git" / _RECORD_GIT_PATH).write_text(f"{field}\n", encoding="utf-8")


def _graded(*, repo: Path, response: str | None = None) -> subprocess.CompletedProcess[str]:
    """Execute the gate's script in one clone and report what it decided."""
    return subprocess.run(
        ["sh", "-c", _gate_script()],
        cwd=repo,
        check=False,
        capture_output=True,
        text=True,
        input=response,
    )


def _stage_cause(*, repo: Path) -> str:
    return (repo / ".git" / _STAGE_CAUSE_GIT_PATH).read_text(encoding="utf-8")


def test_the_green_turn_reaches_the_completion_gate_before_its_commit() -> None:
    """The gate sits between `green` and `commit_green`, with an unconditional fallthrough.

    POSITION is the assertion: `green` must reach neither its commit, the diff
    breaker nor the janitor directly, and a failed gate reaches
    `implement_hook_route`, the incomplete-turn route that re-enters `green`. The
    gate's own fallthrough is asserted UNCONDITIONAL because a node whose every
    outgoing edge carries a condition is rejected before anything runs.
    """
    onward = _targets(source=_GREEN)
    gate_onward = _targets(source=_GATE)

    assert (_GATE, "") in onward, onward
    assert [target for target, _ in onward if target in (_COMMIT_GREEN, _DIFF, _JANITOR)] == []
    assert (_NEEDS_HUMAN, "outcome=failed") in onward
    assert (_COMMIT_GREEN, "") in gate_onward, gate_onward
    assert ("implement_hook_route", "outcome=failed") in gate_onward, gate_onward
    assert [condition for _, condition in gate_onward if condition == ""] == [""]


def test_a_target_naming_the_completion_gate_in_node_timeouts_is_not_refused() -> None:
    """`dispatcher.node_timeouts.implement_completion` resolves rather than refusing."""
    resolved = node_timeouts_from_block(
        block={"node_timeouts": {_GATE: DEFAULT_NODE_TIMEOUT_SECONDS + _CONFIGURED_DELTA}}
    )

    assert not isinstance(resolved, str), resolved
    assert resolved.seconds_for(node=_GATE) == DEFAULT_NODE_TIMEOUT_SECONDS + _CONFIGURED_DELTA


def test_the_configured_value_lands_as_the_literal_timeout_of_the_completion_gate() -> None:
    """The resolved seconds are WRITTEN IN, and read back off the rendered artifact.

    The DEFAULTED rendering is the control: without it, "the node carries this
    figure" is equally consistent with a graph that spells it as a literal.
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
    """The gate carries the visit budget of the retryable `green` turn it guards.

    A node ABSENT from that budget is billed at ZERO, and the figure it feeds is
    the `fabro run` subprocess ceiling, so an unbilled node is one the Dispatcher
    can kill the engine out from under mid-run.
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

    The cause is asserted on BOTH surfaces the ending needs it on: the stderr line
    the Dispatcher carries onto the outcome detail, and the stage-cause file the
    `needs_human` terminal renders. It names the `implement` stage, not this gate.
    """
    repo = _clone(tmp_path=tmp_path)
    _recorded(repo=repo, field=_INCOMPLETE_FIELD)

    result = _graded(repo=repo)

    assert result.returncode != 0, result.stderr
    assert _PARTIAL_PROGRESS in result.stderr
    assert _stage_cause(repo=repo).startswith("stage: implement\n")
    assert _PARTIAL_PROGRESS in _stage_cause(repo=repo)


def test_a_turn_that_states_no_completion_field_is_treated_as_incomplete(tmp_path: Path) -> None:
    """Sub-scenario two: an unstated completion is partial progress, not a success.

    The EMPTY record is asserted beside the absent one because an emptied file is
    what a half-written record leaves behind, and a `test -f` guard would admit it.
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

    BOTH RENDERINGS OF THE SAME FIELD are asserted: the declared spelling carries
    one space after the colon while compact JSON states the field just as well.
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


def test_a_complete_structured_final_reply_succeeds_without_a_completion_record(
    tmp_path: Path,
) -> None:
    """The gate reads the Green reply's structured field before the legacy record."""
    repo = _clone(tmp_path=tmp_path)

    result = _graded(repo=repo, response=_COMPLETE_FIELD)

    assert result.returncode == 0, result.stderr
    assert _COMPLETE_SENTINEL in result.stderr


def test_a_structured_reply_that_only_mentions_the_field_is_not_a_completion_record(
    tmp_path: Path,
) -> None:
    """Only the field itself, rather than a string containing its name, states completion."""
    repo = _clone(tmp_path=tmp_path)

    result = _graded(repo=repo, response='{"note": "definition_of_done_complete"}')

    assert result.returncode != 0, result.stderr
    assert "stated no completion field" in result.stderr


def test_a_stale_cause_from_an_earlier_stage_does_not_survive_a_passing_gate(
    tmp_path: Path,
) -> None:
    """The gate clears the stage-cause file before deciding.

    The terminal renders whatever that file holds, so a cause left standing by an
    earlier stage would be reported as the question for a run that failed elsewhere.
    """
    repo = _clone(tmp_path=tmp_path)
    _ = (repo / ".git" / _STAGE_CAUSE_GIT_PATH).write_text(
        "stage: dod_gate\ncause: an earlier stage's finding\n", encoding="utf-8"
    )
    _recorded(repo=repo, field=_COMPLETE_FIELD)

    result = _graded(repo=repo)

    assert result.returncode == 0, result.stderr
    assert not (repo / ".git" / _STAGE_CAUSE_GIT_PATH).exists()


def test_a_nonempty_reply_without_the_field_falls_back_to_the_completion_record(
    tmp_path: Path,
) -> None:
    """A reply that carries no completion field does not hide a present record.

    "stated no completion field" is reserved for a reply AND a record that both
    lack it.
    """
    complete = _clone(tmp_path=tmp_path / "complete")
    incomplete = _clone(tmp_path=tmp_path / "incomplete")
    absent = _clone(tmp_path=tmp_path / "absent")
    _recorded(repo=complete, field=_COMPLETE_FIELD)
    _recorded(repo=incomplete, field='{"definition_of_done_complete": false}')

    passed = _graded(repo=complete, response="{}")
    failed = _graded(repo=incomplete, response="Partial work only. {}")
    neither = _graded(repo=absent, response="{}")

    assert passed.returncode == 0, passed.stderr
    assert _COMPLETE_SENTINEL in passed.stderr
    assert failed.returncode != 0, failed.stderr
    assert "does not state the work-item Definition of Done complete" in failed.stderr
    assert '"definition_of_done_complete": false' in failed.stderr
    assert neither.returncode != 0, neither.stderr
    assert "stated no completion field" in neither.stderr
