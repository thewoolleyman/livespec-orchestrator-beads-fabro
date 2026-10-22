"""Scenario 137 — a proof-record verdict re-captures instead of spending a fix round.

`SPECIFICATION/contracts.md` section "Definition-of-Done and Proof-of-Done
stages", the PROOF-RECORD-FINDING paragraph ratified in v175 (proposal
`proof-record-findings`), and the Scenario 137 sub-scenarios it added. Work-item
`bd-ib-j56cur`.

THE DEFECT THIS BINDS, measured rather than argued. The graph routed EVERY
blocking review verdict `review -> disposition -> review_fix`, and `review_fix`
is a code-fix node that cannot repair a proof record. Runs `01M5CE38SZJW`
(bd-ib-wkfwtx) and `01M5CDH2FZSE` (bd-ib-22yfvh) on 2026-10-20 each ended with
"node 20 exceeded its firing budget of 3" at review visit 4, the second after
390 minutes, with `just check` green in every fix round: from review visit 2 on,
every blocking finding was about the captured RECORD, and `proof_capture` was
re-entered carrying no knowledge of why its record had been rejected.

THREE LAYERS ARE ASSERTED AND NONE CAN ESTABLISH ANOTHER.

- The committed GRAPH decides where a `recapture` verdict goes and what it does
  NOT reach. No prompt reading can show that, and no execution can either.
- The route node's OWN SCRIPT BYTES decide the two-lap bound. A substring
  assertion cannot tell an arm that runs from one sitting behind an earlier
  `exit`, so the bound is proved by EXECUTING the committed script in a throwaway
  clone, the way `test_proof_grade_scenario195` proves the grade route's.
- The PROMPT PAYLOADS are the implementation of every duty an agent performs:
  which findings `review` classifies as proof-record, that it publishes them on
  the pull request, that `proof_capture` reads them by both routes, the
  self-containment carveout, and the TREE comparison that keeps a checkpoint
  commit from making a record stale. The prompt IS the deliverable for those, so
  the committed bytes are the subject.

WHY EVERY PROMPT NEEDLE IS READ FROM A WHITESPACE-COLLAPSED PAYLOAD. These files
are hard-wrapped, so a needle straddling a line break fails while the prose says
exactly the thing — a probe that can only fail SILENTLY. Collapsing first is what
makes these assertions able to return the other answer, the same discipline
`test_proof_behaviour_capability_and_scenario_reference` uses for the same reason.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._acp_workflow_graph import parse_workflow_graph
from livespec_orchestrator_beads_fabro.commands._dispatcher_dot_graph import parse_dot_graph
from livespec_orchestrator_beads_fabro.commands._dispatcher_open_command_node import COMMAND_NODES
from livespec_orchestrator_beads_fabro.commands._dispatcher_publication_state import (
    PUBLICATION_STATE_GIT_PATH,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PAYLOAD = _REPO_ROOT / ".claude-plugin" / ".fabro" / "workflows" / "implement-work-item"
_GRAPH = _PAYLOAD / "workflow.fabro"
_PROMPTS = _PAYLOAD / "prompts"

_REVIEW = "review"
_ROUTE = "recapture_route"
_CAPTURE = "proof_capture"
_DISPOSITION = "disposition"
_REVIEW_FIX = "review_fix"
_NON_CONVERGED = "non_converged"

# The label `review` emits and the edge condition that selects the route. Spelled
# once, because the prompt and the graph agreeing is the property under test and
# two independently-typed copies could not establish it.
_RECAPTURE_LABEL = "recapture"
_RECAPTURE_CONDITION = f"preferred_label={_RECAPTURE_LABEL}"

# Fabro's one carry mode that includes the source-labelled agent response. The
# DEFAULT is `compact`, which EXCLUDES response text — so under the default the
# reviewer's findings never reach `proof_capture` through the preamble at all,
# which is exactly the channel the ratified clause requires.
_RESPONSE_BEARING_FIDELITY = "summary:high"


def _graph_text() -> str:
    return _GRAPH.read_text(encoding="utf-8")


def _code_text() -> str:
    """The graph with its `//` comment lines dropped.

    An absence assertion over the raw text cannot distinguish a token the graph
    DECLARES from one its comments merely NAME while recording why it is there —
    and this graph's comments name every token they discuss, deliberately.
    """
    return "\n".join(
        line for line in _graph_text().splitlines() if not line.strip().startswith("//")
    )


def _edges() -> list[tuple[str, str, str]]:
    """Every edge as `(source, destination, condition)`, read structurally.

    `parse_dot_graph` is the reader the credential derivation uses, so an edge
    this case reasons about is an edge that derivation also sees.
    """
    parsed = parse_dot_graph(text=_graph_text())
    assert not isinstance(parsed, str), parsed
    return [
        (edge.source, edge.destination, edge.attributes.get("condition", ""))
        for edge in parsed.edges
    ]


def _prompt(*, name: str) -> str:
    """One prompt payload with every whitespace run collapsed to a single space."""
    path = _PROMPTS / name
    assert path.is_file(), path
    return re.sub(r"\s+", " ", path.read_text(encoding="utf-8"))


def test_a_proof_record_verdict_routes_to_proof_capture_and_reaches_no_fix_stage() -> None:
    """Assertion 1: `recapture` ends review at `proof_capture`, past disposition.

    THE ABSENCES ARE THE LOAD-BEARING HALF. "There is a route to `proof_capture`"
    would be satisfied just as well by a node that ALSO routed to `disposition`,
    and on this engine an unconditional edge beside a conditional one is taken
    whenever the condition does not match — so the claim is that the recapture
    route's whole onward edge set is `non_converged` and `proof_capture`, nothing
    else. The contract says so in as many words: a recapture verdict "MUST NOT
    route to `disposition` or `review_fix`, so the verdict consumes no
    `disposition` visit, no `review_fix` visit and no review-fix round".
    """
    edges = _edges()

    assert (_REVIEW, _ROUTE, _RECAPTURE_CONDITION) in edges, edges
    onward = {
        (destination, condition) for source, destination, condition in edges if source == _ROUTE
    }
    assert onward == {(_NON_CONVERGED, "outcome=failed"), (_CAPTURE, "")}, onward
    # No OTHER edge leaves review on this label either: a second arm would make
    # the route non-deterministic on the very verdict it exists to serve.
    assert [
        destination
        for source, destination, condition in edges
        if source == _REVIEW and condition == _RECAPTURE_CONDITION
    ] == [_ROUTE]
    # And the fix verdict's own route is untouched, which is what keeps the
    # mixed-verdict rule below meaningful rather than vacuous.
    assert (_REVIEW, _DISPOSITION, "preferred_label=fix") in edges, edges

    code = _code_text()
    assert (
        f'{_REVIEW} -> {_ROUTE} [label="{_RECAPTURE_LABEL}", condition="{_RECAPTURE_CONDITION}"]'
        in code
    )
    # The retired visit-count guard must not come back here: an `inputs.*` token
    # or `context.internal.node_visit_count` inside a condition is refused by the
    # Petri-era engine AT LOAD, which is why this bound lives in the node.
    assert "context.internal.node_visit_count" not in code
    assert "inputs.recapture" not in code


def test_the_review_prompt_emits_recapture_for_a_wholly_proof_record_verdict() -> None:
    """Assertion 1, prompt half: the verdict vocabulary and what each label means.

    The graph can only route a label `review` actually emits, and the routing JSON
    is the whole of that decision — so the token, the condition under which it is
    chosen, and the four finding kinds that qualify are read off the payload the
    Dispatcher ships.
    """
    prompt = _prompt(name="review.md")

    assert f'{{"preferred_next_label": "{_RECAPTURE_LABEL}"' in prompt
    assert "PROOF-RECORD finding" in prompt
    # The four kinds, each named by the property that identifies it rather than
    # by a paraphrase a reviewer would have to reconstruct.
    assert "not current" in prompt
    assert "test-suite output alone" in prompt
    assert "program the record is required to contain and does not contain" in prompt
    assert "prints the claimed conclusion" in prompt
    # The classification is SHOWN, which is the only thing that separates a
    # reviewer who made it from one who skipped it.
    assert "(proof-record)" in prompt
    assert "(tree)" in prompt
    assert "an unmarked blocking line is an unreviewable verdict" in prompt
    # And what the label buys: no disposition visit, no review_fix visit, no round.
    assert "no disposition visit, no review_fix visit and no review-fix round" in prompt


def test_the_recapture_findings_reach_proof_capture_by_both_channels() -> None:
    """Assertion 2: the engine preamble AND the review record on the pull request.

    THE FIDELITY ATTRIBUTE IS NOT COSMETIC. Fabro's default `compact` preamble
    excludes agent response text, so without `summary:high` on `proof_capture`
    the reviewer's findings cannot reach it through the preamble at all — which is
    precisely the silence the measured loop ran in. The incoming edges are checked
    too: an edge-level `fidelity` OUTRANKS the node's, so one there would restore
    the compact carry while this attribute stayed in place, and the `fix` node's
    own comment records that same trap.
    """
    graph = parse_workflow_graph(text=_graph_text())
    capture = next(node for node in graph.nodes if node.name == _CAPTURE)
    assert capture.attributes.get("fidelity") == _RESPONSE_BEARING_FIDELITY

    incoming = [
        line.strip()
        for line in _graph_text().splitlines()
        if "->" in line and line.strip().split("->", 1)[1].strip().startswith(_CAPTURE)
    ]
    assert incoming
    assert all(
        "fidelity=" not in line or f'fidelity="{_RESPONSE_BEARING_FIDELITY}"' in line
        for line in incoming
    ), incoming

    review = _prompt(name="review.md")
    assert "Review findings — run " in review
    assert "gh pr comment" in review
    assert "post **exactly one NEW comment** on the same draft pull request" in review

    capture_prompt = _prompt(name="proof-capture.md")
    assert "Review findings — run " in capture_prompt
    assert "engine preamble of preceding stage output" in capture_prompt
    assert "Read it whenever the preamble carries no finding" in capture_prompt
    assert "LIVESPEC_RECAPTURE:" in capture_prompt
    # The new record has to be CURRENT and has to answer each finding, which is
    # the clause's own requirement on this entry.
    assert "CURRENT for the publish head" in capture_prompt


def _route_script() -> str:
    """The committed `recapture_route` script, decoded by the graph reader.

    Taken through `parse_dot_graph` rather than retyped, so what executes below is
    the bytes the stage executes: every guard in this node is shell, and a
    substring assertion cannot tell an arm that RUNS from one sitting behind an
    earlier `exit`.
    """
    parsed = parse_dot_graph(text=_graph_text())
    assert not isinstance(parsed, str), parsed
    return parsed.nodes[_ROUTE]["script"]


def _clone(*, tmp_path: Path) -> Path:
    """A throwaway git clone, which is what makes the counter per-run.

    The route resolves its counter through `git rev-parse --git-path`, so a
    fixture that was not a repository would fail closed for the wrong reason.
    """
    repo = tmp_path / "clone"
    repo.mkdir(parents=True)
    _ = subprocess.run(["git", "init", "--quiet"], cwd=repo, check=True)
    return repo


def _routed(*, repo: Path) -> subprocess.CompletedProcess[str]:
    """Execute the route node's script in one clone and report what it decided."""
    return subprocess.run(
        ["sh", "-c", _route_script()],
        cwd=repo,
        check=False,
        capture_output=True,
        text=True,
    )


def _state_dir(*, repo: Path) -> Path:
    return repo / ".git" / PUBLICATION_STATE_GIT_PATH


def test_the_first_two_recapture_verdicts_recapture_and_the_third_stops(
    tmp_path: Path,
) -> None:
    """Assertion 3: lap 1 and lap 2 exit ZERO, lap 3 exits NON-ZERO.

    Run as a SEQUENCE in one clone rather than from seeded counter files, because
    the sequence is the claim: the node has to count its own entries, and a test
    that wrote the counter itself would pass against a node that never
    incremented it. Zero exit takes the unconditional edge into `proof_capture`;
    non-zero takes the named edge to `non_converged`, which is the only ending the
    contract admits for a third recapture verdict.
    """
    repo = _clone(tmp_path=tmp_path)

    first = _routed(repo=repo)
    second = _routed(repo=repo)
    third = _routed(repo=repo)

    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
    assert third.returncode != 0, third.stdout
    assert "LIVESPEC_RECAPTURE:" in first.stderr
    assert "lap 1 of 2" in first.stderr
    assert "lap 2 of 2" in second.stderr
    assert "LIVESPEC_RECAPTURE_EXHAUSTED" in third.stderr
    # The brief the re-capture reads is echoed here, which is the position
    # `proof_capture`'s preamble looks at first, and it NAMES the durable route.
    assert "review record on the pull request" in first.stderr
    assert "no disposition visit, no review_fix visit and no review-fix round" in first.stderr


def test_an_unreadable_recapture_counter_stops_instead_of_looping(tmp_path: Path) -> None:
    """A counter nothing can compare cannot bound a loop, so the route fails CLOSED.

    The direction is the whole assertion. A route that LOOPED on an unreadable
    counter would restore the unbounded re-capture this node exists to bound, and
    it would do so silently; stopping names the cause and ends the run at the
    terminal the Dispatcher already reads.

    The counter is located by READING THE STATE DIRECTORY the node wrote rather
    than by retyping its filename, so this case cannot pass by corrupting a file
    the node does not consult.
    """
    repo = _clone(tmp_path=tmp_path)
    first = _routed(repo=repo)
    assert first.returncode == 0, first.stderr
    written = sorted(path for path in _state_dir(repo=repo).iterdir() if path.is_file())
    assert len(written) == 1, written
    _ = written[0].write_text("not-a-number\n", encoding="utf-8")

    result = _routed(repo=repo)

    assert result.returncode != 0, result.stdout
    assert "LIVESPEC_RECAPTURE_COUNT_UNREADABLE" in result.stderr
    assert "LIVESPEC_RECAPTURE_EXHAUSTED" in result.stderr


def test_the_recapture_cycle_is_cut_by_the_route_nodes_own_visit_cap() -> None:
    """Assertion 3, engine half: the new cycle is bounded, so a dispatch resolves.

    `review -> recapture_route -> proof_capture -> review` is a NEW cycle, and
    `review` and `proof_capture` both carry NO `max_visits` deliberately. The
    credential-lifetime derivation reports an uncut cycle UNBOUNDED and REFUSES
    the dispatch rather than inventing a default, so without a cap here the graph
    would not dispatch at all — a failure the routing assertions above would not
    notice, because the edges would be perfectly shaped.

    The value is the EXACT bound the contract admits: three verdicts, the third of
    which the counter routes out. A fourth entry is reachable only if the counter
    file were lost, which is the one case where the engine abort is right.
    """
    parsed = parse_dot_graph(text=_graph_text())
    assert not isinstance(parsed, str), parsed
    assert parsed.nodes[_ROUTE]["max_visits"] == "3"
    # The two nodes the cycle runs through still carry none, which is what makes
    # the cap above load-bearing rather than redundant.
    assert "max_visits" not in parsed.nodes[_REVIEW]
    assert "max_visits" not in parsed.nodes[_CAPTURE]


def test_the_watchdog_knows_the_recapture_route_is_a_command_node() -> None:
    """Assertion 3, liveness half: the route is in `COMMAND_NODES` or it is false-killed.

    A command node emits a start event and a completion event and NOTHING
    between them, so both liveness layers are flat for its whole duration
    however healthy the run is. `_dispatcher_open_command_node` is what widens
    the stall window to such a node's own timeout, and it answers from a tuple
    asserted against the graph — so a script node missing from it reports
    "nothing open" while the node IS open, which is how three healthy runs were
    cancelled on hp between 2026-10-08 and 2026-10-12.

    Asserted here as well as in that module's own case because this is the node
    THIS item adds: the sibling case states the general invariant, and this one
    states that the recapture route satisfies it, so neither passes by accident
    of the other.
    """
    assert _ROUTE in COMMAND_NODES, COMMAND_NODES
    # Sorted, which is the tuple's own order and the property a later insertion
    # is most likely to break.
    assert list(COMMAND_NODES) == sorted(COMMAND_NODES)


def test_an_exhausted_review_fix_budget_does_not_pre_empt_a_recapture_verdict() -> None:
    """Assertion 3, second half: the recapture route consults neither fix budget.

    The budget lives as `max_visits=3` on `disposition` and `review_fix`, and
    `max_visits` ABORTS the run at entry rather than routing — so an exhausted
    budget could only pre-empt a recapture verdict if the recapture route entered
    one of those nodes. It does not, which is asserted as REACHABILITY rather than
    as prose: no path from `recapture_route` reaches either node without passing
    back through `review`, which is a fresh verdict and not this one.
    """
    edges = _edges()
    assert (
        next(
            node
            for node in parse_workflow_graph(text=_graph_text()).nodes
            if node.name == _REVIEW_FIX
        ).attributes.get("max_visits")
        == "3"
    )
    assert (
        next(
            node
            for node in parse_workflow_graph(text=_graph_text()).nodes
            if node.name == _DISPOSITION
        ).attributes.get("max_visits")
        == "3"
    )

    reached: set[str] = set()
    frontier = [_ROUTE]
    while frontier:
        node = frontier.pop()
        for source, destination, _ in edges:
            if source != node or destination in reached:
                continue
            reached.add(destination)
            # `review` is where a NEW verdict is issued, so the walk stops there:
            # anything past it belongs to that verdict, not to this one.
            if destination != _REVIEW:
                frontier.append(destination)
    assert _DISPOSITION not in reached, sorted(reached)
    assert _REVIEW_FIX not in reached, sorted(reached)

    prompt = _prompt(name="review.md")
    assert "An exhausted review-fix budget does NOT pre-empt a `recapture` verdict" in prompt
    assert "merge_on_review_cap" in prompt


def test_a_mixed_verdict_fixes_the_tree_and_still_carries_its_record_findings() -> None:
    """Assertion 4: a tree finding keeps the fix route; the record findings ride along.

    The route is the graph's existing one and is asserted unchanged. What is NEW is
    the carry: the `proof_capture` visit the fix round re-enters through `janitor`
    and `publish_draft` must receive that verdict's proof-record findings, and the
    ONLY thing that can carry them that far is the review record on the pull
    request — by then the review is several stages behind in the preamble. So the
    prompt must post that record on a `fix` verdict too, not only on a recapture.
    """
    edges = _edges()
    assert (_REVIEW, _DISPOSITION, "preferred_label=fix") in edges
    assert (_DISPOSITION, _REVIEW_FIX, "preferred_label=fix") in edges
    assert (_REVIEW_FIX, "janitor", "") in edges
    assert ("publish_draft", _CAPTURE, "") in edges

    review = _prompt(name="review.md")
    assert "**At least one blocking finding tagged `(tree)`** → `fix`" in review
    assert "Post it on a `recapture` verdict AND on a `fix` verdict" in review
    assert "whatever proof-record findings ride along beside it" in review

    capture = _prompt(name="proof-capture.md")
    # The capture prompt reads the record on EITHER entry, which is what makes the
    # fix-round carry work: it does not key on having been re-entered by recapture.
    assert "A fix round reaches you several stages later instead" in capture


def test_a_captured_step_program_rides_in_the_record_unless_tracked_or_installed() -> None:
    """Assertion 5: the self-containment rule and its two exemptions, exactly.

    The rule only bites where it should. A record forced to inline a tracked
    script or a system tool would be unreadable and the requirement would be
    ignored, so the clause exempts a program the repository TRACKS at the record's
    named commit when invoked by its path, and an INSTALLED tool invoked by its
    name. Everything else goes into the record or into a proof asset the record
    names — which is the second publication route, and it was absent from this
    prompt before: a program too large to inline had nowhere to go.
    """
    prompt = _prompt(name="proof-capture.md")

    assert (
        "Every program a step executes that is NEITHER tracked in the repository at the "
        "commit this record names NOR an installed tool invoked by its name MUST be written "
        "into the record itself" in prompt
    )
    assert "into a proof asset the record names through the proof asset store" in prompt
    assert "These two are exempt, and naming them is enough" in prompt
    assert "may be invoked by its path" in prompt
    assert "INSTALLED tool may be invoked by its name" in prompt
    # The untracked scratch directory is called out by name, because that is the
    # shape the measured records actually used.
    assert '"${TMPDIR:-/tmp}/proof-capture"` is untracked by construction' in prompt
    assert "blocking proof-record finding at review" in prompt


def test_review_reads_record_currency_as_a_tree_comparison_not_a_timestamp() -> None:
    """Assertion 6: equal trees are CURRENT, so a checkpoint commit is not staleness.

    This is the gap the petri-seat rider measured, and it defeats the other five
    assertions on its own: the engine commits a checkpoint after every node, and
    `proof_capture`'s lands AFTER the record is posted, so a record naming the
    publish head AT CAPTURE TIME is still a commit or two below the reviewed head
    — five to fifteen seconds older, with an identical tree. Under the retired
    timestamp comparison that was a blocking finding every single round.

    The ABSENCE of the retired instruument is asserted beside the presence of the
    new one, because the two can coexist: a prompt that gained the tree comparison
    while keeping "compare the record's own timestamp against the branch's commit
    timestamps" would still produce the finding every round.
    """
    prompt = _prompt(name="review.md")

    assert "the TREE of the commit the record names equals the TREE of that head" in prompt
    assert "git diff --quiet <the record's sha> <the head under review>" in prompt
    assert "A commit that changes no tree MUST NOT make a record stale" in prompt
    assert "Do NOT judge currency by timestamp, by sha equality, or by commit order" in prompt
    assert "never require the record to POSTDATE the head" in prompt
    assert "Compare the record's own timestamp and run id against the branch's" not in prompt

    # The record's side of the same contract: it STATES the sha its steps ran
    # against, which is what the comparison above has to read.
    capture = _prompt(name="proof-capture.md")
    assert "Publish-branch head: <the full 40-character commit sha" in capture
