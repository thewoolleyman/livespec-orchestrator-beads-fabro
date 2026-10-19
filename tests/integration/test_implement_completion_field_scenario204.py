"""Scenario 204 — an implement turn that reports its work incomplete fails the stage.

`SPECIFICATION/scenarios.md` "## Scenario 204 — An implement turn that reports
its work incomplete fails the implement stage" has three sub-scenarios, and they
realize the `SPECIFICATION/contracts.md` paragraph "An implement turn that ends
incomplete does not succeed" (ratified v165, proposal implement-incomplete-fails):

    Given an implement turn whose final output's completion field reports the
      Definition of Done incomplete
    Then the stage outcome is failed with a cause naming partial progress
    And the run takes the implement stage's failure edge, and the dispatch
      outcome detail carries that cause

    Given an implement turn whose final output carries no completion field
    Then the stage outcome is failed with a cause naming partial progress

    Given an implement turn whose final output's completion field reports the
      Definition of Done complete
    Then the stage outcome is succeeded and the run proceeds to
      implementation_diff as before

WHAT THE MEASURED DEFECT WAS, because it decides the POLARITY every assertion
below turns on. On `bd-ib-davaxq` run 01M58QNY3ZNM2YCVVB9G2383M0 the implement
turn's reply read "Partial progress only", having committed one configuration
declaration and one test and never run the final check. The stage was recorded
SUCCEEDED, because the engine decides an agent node's outcome from the turn
merely ending, and the `implement -> implementation_diff` edge was the
UNCONDITIONAL FALLTHROUGH. The run then ran janitor, publish_draft and
proof_capture against a feature that was not there, and the fix turn it routed
to had to build the whole thing in one turn and died at its ceiling.

So the ONE thing that must not be weakened here is that the fallthrough is the
INCOMPLETE arm. A conforming turn names the complete route by condition; silence
reaches the partial-progress gate. Every sub-scenario above is an assertion about
that polarity read at a different layer.

WHAT EACH LAYER CAN AND CANNOT ESTABLISH, which is why the cases split the way
they do rather than one per layer:

- The completion field itself lives in the turn's final output, which only the
  ENGINE reads. Nothing host-side can observe a turn obeying its prompt, so the
  field's existence is bound as PROSE — and bound to the graph's own condition
  value rather than to a string retyped here, so a rename on either side reds
  instead of leaving the two halves describing different labels.
- The ROUTING is entirely a property of the committed edges, read off the
  committed lines rather than off a parse, because the parse drops edge
  attributes and the condition is exactly what distinguishes the three arms.
- The no-field arm's CAUSE is shell, so its node script is taken through the
  canonical parser and EXECUTED. A substring assertion cannot tell a cause record
  that is written from one sitting behind an earlier `exit`, and the record is
  consumed by a SECOND script — the `needs_human` terminal — so only running both
  shows the carry. The terminal's reading half is likewise taken from the
  committed bytes and run, never retyped.
- The dispatch outcome DETAIL is production Python, so it is driven through
  `fabro_run_terminal_outcome` against an inspect payload in the terminated shape
  that CLI really returns (a top-level `checkpoint`, a null `next_node_id`, and
  the engine's own `node_outcomes` map naming the failed node).
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_dot_graph import parse_dot_graph
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_fabro_terminal import (
    fabro_run_terminal_outcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import (
    NEEDS_HUMAN_MARKER,
    DispatchPlan,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port import FabroInspectResult
from livespec_orchestrator_beads_fabro.commands._fabro_port_records import (
    fabro_failure_detail_from_payload,
    fabro_status_kind_from_payload,
)

_BUNDLE = Path(".claude-plugin/.fabro/workflows/implement-work-item")
_IMPLEMENT_PROMPT = _BUNDLE / "prompts" / "implement.md"
_GATE_NODE = "implement_partial_progress"
_SENTINEL = "LIVESPEC_IMPLEMENT_PARTIAL_PROGRESS"
_COMPLETION_HEADING = "## Report whether the Definition of Done is complete"
# The one line of the terminal's script that begins its cause-reading half. The
# tail from here carries no push and no commit, so it is the part that can be run.
_TERMINAL_READ_MARKER = "reason_path=$(git rev-parse --git-path livespec-needs-human-reason);"
_ITEM = "bd-ib-ahxcjx"
_RUN = "01M5PARTIALPROGRESSRUNIDENT"
_SIGNATURE = "implement|deterministic|partial progress"
_CAUSE = (
    f"{_SENTINEL}: only the configuration declaration and one test are committed and the "
    "final check was never run, so the Definition of Done is not complete on this branch"
)


def _dot() -> str:
    return (_BUNDLE / "workflow.fabro").read_text(encoding="utf-8")


def _completion_section() -> str:
    """The implement prompt's completion-field section, verbatim.

    Scoped to the one section rather than the whole prompt because the
    needs-human protocol and the Definition-of-Done amendment each carry a
    structured-ending JSON object of their own, and a whole-file scan for JSON
    would read those as completion fields.
    """
    text = _IMPLEMENT_PROMPT.read_text(encoding="utf-8")
    section = re.search(
        rf"^{re.escape(_COMPLETION_HEADING)}\n.*?(?=\n## |\Z)", text, re.DOTALL | re.MULTILINE
    )
    assert section is not None, f"{_IMPLEMENT_PROMPT} declares no {_COMPLETION_HEADING!r} section"
    return section.group()


def _completion_objects() -> list[dict[str, object]]:
    """Every JSON object the completion-field section tells the turn to emit."""
    found: list[dict[str, object]] = []
    for line in _completion_section().splitlines():
        stripped = line.strip()
        if stripped.startswith("{") and stripped.endswith("}"):
            parsed = json.loads(stripped)
            assert isinstance(parsed, dict), stripped
            found.append(parsed)
    return found


def _edge_conditions(*, source: str) -> dict[str, str]:
    """Each target one node points at, mapped to its edge's `condition=` value.

    Read off the committed lines rather than through the parse, which drops edge
    attributes. An unconditional edge maps to the EMPTY STRING rather than being
    omitted, so a fallthrough that silently grew a condition changes this answer
    instead of vanishing from it.
    """
    conditions: dict[str, str] = {}
    for line in _dot().splitlines():
        edge = re.match(rf"\s*{source} -> (?P<target>\w+)\b(?P<attrs>.*)$", line)
        if edge is None:
            continue
        found = re.search(r'condition="(?P<value>[^"]*)"', edge.group("attrs"))
        conditions[edge.group("target")] = "" if found is None else found.group("value")
    return conditions


def _node_script(*, node: str) -> str:
    """One node's `script` attribute with its DOT escapes decoded, ready for `sh`."""
    graph = parse_dot_graph(text=_dot())
    assert not isinstance(graph, str), graph
    assert node in graph.nodes, sorted(graph.nodes)
    return graph.nodes[node]["script"]


def _run(*, script: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["sh", "-c", script],
        cwd=cwd,
        check=False,
        text=True,
        capture_output=True,
        input=f"{_RUN}\n",
    )


def _clone(*, root: Path) -> Path:
    clone = root / "clone"
    clone.mkdir(parents=True)
    _ = subprocess.run(
        ["git", "init", "-q"],
        cwd=clone,
        check=True,
        text=True,
        capture_output=True,
    )
    return clone


def _plan(*, root: Path) -> DispatchPlan:
    return DispatchPlan(
        repo=root,
        work_item_id=_ITEM,
        branch=f"feat/{_ITEM}",
        workflow_toml=root / "workflow.toml",
        goal_file=root / "goal.txt",
        fabro_bin="fabro",
        fabro_factory_name="hp",
        fabro_factory_server="https://hp.example:32276",
        fabro_factory_dev_token=None,
        janitor=None,
        janitor_checkout=root / ".janitor",
        janitor_core_checkout=root / ".janitor" / ".livespec-core",
        janitor_core_repo_url="https://github.com/thewoolleyman/livespec.git",
        janitor_core_ref="master",
        review_fix_visit_cap=3,
        merge_on_review_cap_outcome="succeeded",
    )


def _payload(*, failed_node: str | None) -> list[object]:
    """`fabro inspect --json` for a run the terminal ended, in its terminated shape.

    `failed_node` is None for the run the CONTROL describes — one the engine
    routed to the terminal with no failed predecessor recorded — because the
    detail's "failed at stage <name>" clause may not be a constant of every
    needs-human ending.
    """
    outcomes = (
        {}
        if failed_node is None
        else {
            failed_node: {
                "status": "failed",
                "failure": {
                    "category": "deterministic",
                    "signature": _SIGNATURE,
                    "causes": ["ACP protocol error", _CAUSE],
                },
            }
        }
    )
    return [
        {
            "run_id": _RUN,
            "status": {"kind": "failed"},
            "checkpoints": [
                {
                    "checkpoint": {
                        "current_node": "needs_human",
                        "next_node_id": None,
                        "completed_nodes": ["dod_gate", "implement"],
                        "loop_failure_signatures": {_SIGNATURE: 1},
                        "node_outcomes": outcomes,
                    }
                }
            ],
        }
    ]


def _outcome(*, root: Path, failed_node: str | None) -> DispatchOutcome:
    payload = _payload(failed_node=failed_node)
    outcome = fabro_run_terminal_outcome(
        outcome_type=DispatchOutcome,
        plan=_plan(root=root),
        run_id=_RUN,
        inspect=FabroInspectResult(
            command=CommandResult(exit_code=0, stdout="", stderr=""),
            payload=payload,
            status_kind=fabro_status_kind_from_payload(payload=payload),
            failure=fabro_failure_detail_from_payload(payload=payload),
        ),
        exit_code=1,
        stderr=f"{_CAUSE}\n{NEEDS_HUMAN_MARKER}: {_CAUSE}\n",
    )
    assert outcome is not None
    return outcome


def test_the_implement_prompt_directs_the_turn_to_end_with_the_completion_field() -> None:
    """Sub-scenario premise: the prompt requires the field the stage's outcome reads.

    The two objects are PARSED rather than grepped, and the complete one's label
    is compared against the graph's own condition value: a needle retyped here
    would keep agreeing with itself after either side was renamed, which is the
    one way this binding can rot into a probe that cannot fail.
    """
    section = _completion_section()
    objects = _completion_objects()
    complete_label = _edge_conditions(source="implement")["implementation_diff"]

    assert "decided from a structured completion field in this" in section
    assert "turn's final output, NOT from the turn merely ending" in section
    assert "with a single JSON object on the LAST line, stating whether the work item's" in section
    assert "Definition of Done is complete on the committed branch" in section
    assert len(objects) == 2, objects
    assert objects[0] == {"preferred_next_label": complete_label.split("=", 1)[1]}
    assert objects[1]["outcome"] == "failed"
    assert str(objects[1]["failure_reason"]).startswith(f"{_SENTINEL}: ")


def test_an_incomplete_completion_field_fails_the_stage_and_carries_the_cause(
    tmp_path: Path,
) -> None:
    """Sub-scenario one: incomplete rides the implement stage's own failure edge.

    The route is asserted as the WHOLE answer for the node, so an added fourth
    edge reds rather than slipping past, and the detail is read off production
    code. The control is the SAME payload with no failed predecessor recorded:
    without it, "the detail names the implement stage" is equally consistent
    with a renderer that names a stage on every needs-human ending.
    """
    assert _edge_conditions(source="implement") == {
        "needs_human": "outcome=failed",
        "implementation_diff": "preferred_label=definition_of_done_complete",
        _GATE_NODE: "",
    }

    outcome = _outcome(root=tmp_path, failed_node="implement")

    assert (outcome.status, outcome.stage, outcome.fabro_run_id) == ("blocked", "fabro-run", _RUN)
    assert "failed at stage implement" in outcome.detail
    assert f"innermost cause: {_CAUSE}" in outcome.detail
    assert f"resolve-blocked:{_ITEM}:ready" in outcome.detail
    assert "failed at stage implement" not in _outcome(root=tmp_path, failed_node=None).detail


def test_a_final_output_with_no_completion_field_fails_with_a_partial_progress_cause(
    tmp_path: Path,
) -> None:
    """Sub-scenario two: silence is treated as incomplete, and the cause says so.

    Both scripts are the committed bytes and both are RUN, because the gate
    WRITES a cause record that the terminal READS and neither half can establish
    the carry alone. The control is the same terminal tail in a clone where the
    gate never ran: without it, "the terminal named partial progress" is equally
    consistent with a terminal that says so on every ending.
    """
    clone = _clone(root=tmp_path)
    gate = _run(script=_node_script(node=_GATE_NODE), cwd=clone)

    assert gate.returncode != 0
    assert _SENTINEL in gate.stderr
    assert "partial progress" in gate.stderr
    recorded = (clone / ".git" / "livespec-stage-cause").read_text(encoding="utf-8")
    assert recorded.splitlines()[0] == "stage: implement"
    assert recorded.splitlines()[1].startswith(f"cause: {_SENTINEL}: ")

    terminal = _node_script(node="needs_human")
    tail = terminal[terminal.index(_TERMINAL_READ_MARKER) :]
    carried = _run(script=tail, cwd=clone)

    assert carried.returncode != 0
    assert f"{NEEDS_HUMAN_MARKER}: stage implement failed: {_SENTINEL}: " in carried.stderr
    assert _SENTINEL not in _run(script=tail, cwd=_clone(root=tmp_path / "control")).stderr


def test_a_complete_completion_field_keeps_the_route_to_implementation_diff() -> None:
    """Sub-scenario three: the complete field keeps the routing it always had.

    `implementation_diff`'s own successors are asserted UNCHANGED beside the
    condition, because "the complete field reaches the diff breaker" says nothing
    about the run proceeding "as before" if what follows the breaker moved. The
    control is the gate node, whose only route ends the run — without it, a graph
    in which every arm reached publication would satisfy the reachability claim.
    """
    conditions = _edge_conditions(source="implement")
    graph = parse_dot_graph(text=_dot())
    assert not isinstance(graph, str), graph
    successors = {edge.destination for edge in graph.edges if edge.source == "implementation_diff"}

    assert conditions["implementation_diff"] == "preferred_label=definition_of_done_complete"
    assert successors == {"janitor", "dead_implementer"}
    assert _edge_conditions(source="implementation_diff") == {
        "janitor": "outcome=succeeded",
        "dead_implementer": "",
    }
    # The complete route is the only one of the three arms that is not a dead
    # end: the gate hands the run to the terminal, and the terminal hands it
    # nowhere at all.
    assert _edge_conditions(source=_GATE_NODE) == {"needs_human": ""}
    assert _edge_conditions(source="needs_human") == {}
