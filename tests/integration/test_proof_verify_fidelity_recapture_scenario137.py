"""Scenario 137 and 138 — a record-fidelity non-reproduction re-captures instead of entering fix.

`SPECIFICATION/contracts.md` section "Definition-of-Done and Proof-of-Done
stages", the `proof_verify` paragraph and the "Proof findings are the fix stage's
work order" paragraph ratified in v205 (proposal `proof-fidelity-recapture`).
Work-item `bd-ib-v3uksp`.

THE DEFECT THIS BINDS, measured on petri run `01M5JME62ZF8` (bd-ib-7k7re5,
2026-10-22): `proof_verify` recorded `not_reproduced` on two assertions ONLY
because the replayed program's combined terminal output interleaved stdout and
stderr differently, the behaviour being identical. The graph sent that verdict to
`fix`, which was handed the FIRST capture's superseded finding, refused an
artificial tree change, and the run rested at needs-human on approved work.

THREE LAYERS ARE ASSERTED, and none can establish another: the committed GRAPH
decides where each label goes; the PROMPT payloads are the implementation of the
classification and of which record `fix` and `proof_capture` read; the recapture
route node's SCRIPT BYTES decide the shared two-lap bound and are executed.

EVERY PROMPT NEEDLE IS READ FROM A WHITESPACE-COLLAPSED PAYLOAD, because the
prompts are hard-wrapped and a needle straddling a line break would fail while
the prose says exactly the thing.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_dot_graph import parse_dot_graph

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PAYLOAD = _REPO_ROOT / ".claude-plugin" / ".fabro" / "workflows" / "implement-work-item"
_GRAPH = _PAYLOAD / "workflow.fabro"
_PROMPTS = _PAYLOAD / "prompts"

_VERIFY = "proof_verify"
_ROUTE = "recapture_route"
_CAPTURE = "proof_capture"
_FIX = "fix"
_NON_CONVERGED = "non_converged"
_RECAPTURE_CONDITION = "preferred_label=recapture"


def _graph_text() -> str:
    return _GRAPH.read_text(encoding="utf-8")


def _edges() -> list[tuple[str, str, str]]:
    parsed = parse_dot_graph(text=_graph_text())
    assert not isinstance(parsed, str), parsed
    return [
        (edge.source, edge.destination, edge.attributes.get("condition", ""))
        for edge in parsed.edges
    ]


def _prompt(*, name: str) -> str:
    path = _PROMPTS / name
    assert path.is_file(), path
    return re.sub(r"\s+", " ", path.read_text(encoding="utf-8"))


def test_a_fidelity_verdict_routes_proof_verify_to_recapture_route_and_not_to_fix() -> None:
    """Assertion 1, graph half: the recapture label leaves `proof_verify` for the route node."""
    edges = _edges()

    assert (_VERIFY, _ROUTE, _RECAPTURE_CONDITION) in edges, edges
    assert [
        destination
        for source, destination, condition in edges
        if source == _VERIFY and condition == _RECAPTURE_CONDITION
    ] == [_ROUTE]
    # The route node's whole onward set is unchanged: the re-capture, or the
    # bound. A fidelity verdict therefore reaches `proof_capture` and no other node.
    onward = {
        (destination, condition) for source, destination, condition in edges if source == _ROUTE
    }
    assert onward == {(_NON_CONVERGED, "outcome=failed"), (_CAPTURE, "")}, onward
    assert (_VERIFY, _CAPTURE, "") not in edges
    assert (_VERIFY, _CAPTURE, _RECAPTURE_CONDITION) not in edges


def test_a_behaviour_verdict_still_routes_proof_verify_to_fix() -> None:
    """Assertion 2, graph half: the `fix` label keeps its edge, alone."""
    edges = _edges()

    assert (_VERIFY, _FIX, "preferred_label=fix") in edges, edges
    assert [
        destination
        for source, destination, condition in edges
        if source == _VERIFY and condition == "preferred_label=fix"
    ] == [_FIX]


def test_the_proof_verify_prompt_classifies_each_difference_and_emits_the_matching_label() -> None:
    """Assertions 1 and 2, prompt half: fidelity emits recapture, behaviour emits fix."""
    prompt = _prompt(name="proof-verify.md")

    assert "classify the difference as either FIDELITY or BEHAVIOUR" in prompt
    assert (
        "FIDELITY means the replay's observable behavioural result equals the captured one "
        "and only the record's rendering differs" in prompt
    )
    assert "interleaving or ordering of output streams, whitespace, or formatting" in prompt
    assert "A difference you cannot positively show to be fidelity is BEHAVIOUR" in prompt
    # The classification is SHOWN in the record, per not-reproduced assertion.
    assert "Difference: fidelity" in prompt
    assert "Difference: behaviour" in prompt
    # Recapture only when EVERY not-reproduced assertion is fidelity.
    assert "EVERY assertion you name as not reproduced is FIDELITY" in prompt
    assert '{"preferred_next_label": "recapture"}' in prompt
    assert "ONE behaviour difference among them makes the whole verdict a behaviour verdict" in (
        prompt
    )
    assert '{"preferred_next_label": "fix"}' in prompt
    assert "a fidelity verdict never routes to `fix`" in prompt


def test_the_fix_prompt_takes_the_record_graded_in_that_visit_as_its_work_order() -> None:
    """Assertion 3: `fix` names the `proof_verify` record of the visit, never a superseded capture."""
    prompt = _prompt(name="fix.md")

    assert "take as your work order the record the entering stage graded in that visit" in prompt
    assert (
        "on entry from `proof_verify`, the `not_reproduced` record that visit published" in prompt
    )
    assert "on entry from `proof_capture`, that visit's `not_captured` record" in prompt
    assert "A finding from a capture that a later `proof_capture` visit superseded" in prompt
    assert "is NOT your work order" in prompt
    # The pull-request fallback keeps the same rule: it reads the latest record of
    # the ENTERING stage's own verdict word, so an older capture's record cannot
    # outrank the replay record that sent the run here.
    assert "the latest record of the entering stage" in prompt


def test_proof_capture_reads_the_proof_verify_record_on_a_fidelity_recapture() -> None:
    """The recapture work order of a fidelity verdict is the `not_reproduced` record."""
    prompt = _prompt(name="proof-capture.md")

    assert "recapture entry from `proof_verify`" in prompt
    assert "Proof of Done — not_reproduced — run " in prompt
    assert "Difference: fidelity" in prompt


def _route_script() -> str:
    parsed = parse_dot_graph(text=_graph_text())
    assert not isinstance(parsed, str), parsed
    return parsed.nodes[_ROUTE]["script"]


def test_the_route_node_names_both_sources_and_still_bounds_the_third_recapture(
    tmp_path: Path,
) -> None:
    """The shared two-lap bound: a fidelity verdict is counted like a review recapture."""
    repo = tmp_path / "clone"
    repo.mkdir()
    _ = subprocess.run(["git", "init", "--quiet"], cwd=repo, check=True)

    results = [
        subprocess.run(
            ["sh", "-c", _route_script()],
            cwd=repo,
            check=False,
            capture_output=True,
            text=True,
        )
        for _ in range(3)
    ]

    assert [result.returncode for result in results] == [0, 0, 1]
    assert "LIVESPEC_RECAPTURE: recapture lap 1 of 2" in results[0].stderr
    assert "proof_verify" in results[0].stderr
    assert "LIVESPEC_RECAPTURE_EXHAUSTED" in results[2].stderr
