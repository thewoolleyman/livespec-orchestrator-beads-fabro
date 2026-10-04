"""Scenario 131, fifth gherkin — the implementer that finds the Definition of Done wrong.

`SPECIFICATION/scenarios.md` "## Scenario 131 — The Definition of Done gate
admits a coherent item, refuses a malformed one host-side, and rests an
incoherent one at needs-human" ends on a scenario the gate cannot cover,
because its subject is the stage AFTER the gate:

    Given a running implement node that determines the Definition of Done is
      incomplete
    When the node ends through the structured needs-human ending carrying the
      proposed amendment
    Then the item rests at blocked with reason needs-human and the amendment as
      the recorded question
    And no code that differs from the Definition of Done is published

The clause it realizes is the kept-current paragraph of
`SPECIFICATION/contracts.md` (ratified v114), which requires ONE rest state for
a wrong Definition of Done whichever stage notices it, and says in as many
words that the implement prompt MUST state the rule.
`tests.integration.test_workflow_dod_gate_scenario131` binds the gate's half of
that one rest state; this module binds the implementer's.

WHY THE JOURNEY IS ONE CASE RATHER THAN FOUR. The claim under test is not that
four mechanisms each work — each of them already did before this slice, which
is exactly why asserting them apart would prove nothing new. The claim is that
they COMPOSE into a single rest state: an amendment emitted by the implement
node reaches the `needs_human` terminal, the terminal mapper turns that into a
`blocked` outcome, the ledger write rests the item at `blocked / needs-human`,
and the amendment — not a generic apology — is the text the human is shown when
they come to decide. Split into four cases, every one of them passes against a
build in which the amendment is dropped somewhere between the run and the
valve, because no case would carry the same string through two layers.

WHAT IS STOOD IN, AND WHAT IS NOT. Only the `fabro` CLI is stood in, at the
runner seam the port publishes for it; the graph is the committed payload read
as bytes, the terminal mapper, the question reader, the valve summary and the
blocked ledger write are production code, and the tenant is the real
store/client seam over the in-memory backend. The run's inspect payload is the
one fixture, in the shape `_fabro_needs_human_question`'s own measured case
uses (run `01M10CYZ8S9TNPZ2MW096NJW7V`).

THE PUBLICATION HALF IS ASSERTED AS REACHABILITY, not as the absence of one
edge. "No code that differs is published" is a claim about everything
downstream of the amendment, and an absent `implement -> pr` edge would satisfy
a graph that reached `pr` through `implementation_diff` anyway. So the terminal
is asserted to reach NOTHING, and the control is that the publishing route is
real and reachable from the implement node's OTHER successor — without it, an
empty reachable set is equally consistent with a graph whose node names this
module simply misspelled.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import reset_fake_singleton
from livespec_orchestrator_beads_fabro._store_dispatch_factory import record_dispatch_run
from livespec_orchestrator_beads_fabro.commands._acp_workflow_graph import (
    WorkflowGraph,
    parse_workflow_graph,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_blocked import (
    escalate_needs_human_block,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_fabro_terminal import (
    fabro_run_terminal_outcome,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import store_config
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import (
    NEEDS_HUMAN_MARKER,
    DispatchPlan,
)
from livespec_orchestrator_beads_fabro.commands._fabro_needs_human_question import (
    needs_human_question_from_payload,
)
from livespec_orchestrator_beads_fabro.commands._needs_attention_needs_human_question import (
    needs_human_question_summary,
)
from livespec_orchestrator_beads_fabro.store import append_work_item, read_work_items
from livespec_orchestrator_beads_fabro.types import WorkItem

_BUNDLE = Path(".claude-plugin/.fabro/workflows/implement-work-item")
_IMPLEMENT_PROMPT = _BUNDLE / "prompts" / "implement.md"
_ITEM = "bd-ib-ymy7xq"
_RUN = "01M4AMENDMENTOFDEFINITIONOFDONE"
_FACTORY = "hp"
_SERVER = "https://hp.example:32276"
_TENANT = "livespec-orch-beads-fabro"

# The amendment an implementer proposes: the assertion as dispatched, what is
# wrong with it, and the replacement text. It is carried verbatim through every
# layer below, which is what makes "the amendment as the recorded question" a
# claim about THIS text rather than about some needs-human text.
_AMENDMENT = (
    f"Definition of Done amendment for {_ITEM}: the assertion 'the gate rejects a "
    "malformed section' cannot be satisfied as written, because the gate node runs "
    "only on items the host-side wall already admitted; proposed replacement: 'A "
    "dispatch of an item whose description carries no Definition of Done section is "
    "refused before any run exists, with exit code 5 naming the missing section.'"
)


def _dot() -> str:
    return (_BUNDLE / "workflow.fabro").read_text(encoding="utf-8")


def _prompt() -> str:
    """The implement prompt with every whitespace run collapsed to one space.

    The prompt is hard-wrapped, so a needle straddling a line break fails while
    the prose says exactly the thing — a probe that can only fail SILENTLY.
    Collapsing first is what makes these assertions able to return the other
    answer.
    """
    return re.sub(r"\s+", " ", _IMPLEMENT_PROMPT.read_text(encoding="utf-8"))


def _edge_conditions(*, source: str) -> dict[str, str]:
    """Each target one node points at, mapped to its edge's `condition=` value.

    The parsed graph drops edge attributes, and the condition is exactly what
    distinguishes the amendment's route from the ordinary fallthrough — so this
    reads the committed lines rather than the parse. An unconditional edge maps
    to the EMPTY STRING rather than being omitted, so a fallthrough that
    silently grew a condition changes this answer instead of vanishing from it;
    a commented line cannot match, because the match is anchored on the source
    name and a comment opens with its marker instead.
    """
    conditions: dict[str, str] = {}
    for line in _dot().splitlines():
        edge = re.match(rf"\s*{source} -> (?P<target>\w+)\b(?P<attrs>.*)$", line)
        if edge is None:
            continue
        found = re.search(r'condition="(?P<value>[^"]*)"', edge.group("attrs"))
        conditions[edge.group("target")] = "" if found is None else found.group("value")
    return conditions


def _reachable(*, graph: WorkflowGraph, start: str) -> frozenset[str]:
    """Every node reachable from one node by following edges."""
    seen: set[str] = set()
    frontier = [start]
    while frontier:
        for target in graph.successors(node=frontier.pop()):
            if target not in seen:
                seen.add(target)
                frontier.append(target)
    return frozenset(seen)


@dataclass(frozen=True, kw_only=True)
class _Captured:
    """The `fabro` CLI result shape the port reads, with no process spawned."""

    exit_code: int
    stdout: str
    stderr: str


class _InspectRunner:
    """The ONE seam that leaves the process: `fabro inspect <run> --json`."""

    def __init__(self, *, payload: object) -> None:
        self.payload = payload
        self.argv: list[list[str]] = []

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
    ) -> _Captured:
        del cwd, timeout_seconds, env, stdin
        self.argv.append(argv)
        return _Captured(exit_code=0, stdout=json.dumps(self.payload), stderr="")


def _inspect_payload(*, amendment: str) -> list[object]:
    """What `fabro inspect --json` returns for a run the implementer amended.

    `status.kind` is `failed`, never a park: under contract v093 a needs-human
    outcome TERMINATES the run. The amendment appears under the implement
    node's own `failure_reason` and again behind the terminal's sentinel,
    because that is both what the graph does and what the reader must survive —
    the `needs_human` script CONTAINS every sentinel literal by construction, so
    a reader keying on script source would answer with shell text instead.
    """
    return [
        {
            "run_id": _RUN,
            "status": {"kind": "failed"},
            "checkpoints": [{"checkpoint": {"next_node_id": "needs_human"}}],
            "nodes": [
                {"id": "implement", "output": {"failure_reason": amendment}},
                {
                    "id": "needs_human",
                    "output": {"stderr": f"{NEEDS_HUMAN_MARKER}: {amendment}\n"},
                },
            ],
        }
    ]


def _write_repo(*, root: Path) -> None:
    _ = (root / ".livespec.jsonc").write_text(
        json.dumps(
            {
                "livespec-orchestrator-beads-fabro": {
                    "connection": {
                        "tenant": _TENANT,
                        "prefix": "bd-ib",
                        "server_user": _TENANT,
                        "database": _TENANT,
                        "bd_path": "bd",
                        "fake": True,
                    },
                    "dispatcher": {
                        "default_factory": _FACTORY,
                        "factories": {_FACTORY: {"server": _SERVER}},
                    },
                }
            }
        ),
        encoding="utf-8",
    )


def _seed(*, root: Path) -> WorkItem:
    """One `active` work-item written through the REAL store seam."""
    item = WorkItem(
        id=_ITEM,
        type="task",
        status="active",
        blocked_reason=None,
        title="Implementer-noticed wrong Definition of Done",
        description="## Definition of Done\n\n- the gate rejects a malformed section.\n",
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee="fabro",
        depends_on=(),
        captured_at="2026-10-04T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
    )
    append_work_item(path=store_config(repo=root), item=item)
    return item


def _rested(*, root: Path) -> tuple[str, str | None]:
    rows = {row.id: row for row in read_work_items(path=store_config(repo=root))}
    return (rows[_ITEM].status, rows[_ITEM].blocked_reason)


def _plan(*, root: Path) -> DispatchPlan:
    return DispatchPlan(
        repo=root,
        work_item_id=_ITEM,
        branch=f"feat/{_ITEM}",
        workflow_toml=root / "workflow.toml",
        goal_file=root / "goal.txt",
        fabro_bin="fabro",
        fabro_factory_name=_FACTORY,
        fabro_factory_server=_SERVER,
        fabro_factory_dev_token=None,
        janitor=None,
        janitor_checkout=root / ".janitor",
        janitor_core_checkout=root / ".janitor" / ".livespec-core",
        janitor_core_repo_url="https://github.com/thewoolleyman/livespec.git",
        janitor_core_ref="master",
        review_fix_visit_cap=3,
        merge_on_review_cap_outcome="succeeded",
    )


@pytest.fixture
def tenant(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Drive the store onto the in-memory tenant, isolated per test."""
    monkeypatch.setenv("LIVESPEC_BEADS_FAKE", "1")
    monkeypatch.delenv("LIVESPEC_FABRO_FACTORY", raising=False)
    reset_fake_singleton()
    yield
    reset_fake_singleton()


def test_the_implement_prompt_routes_a_wrong_definition_of_done_to_the_amendment() -> None:
    """The kept-current rule, stated where the implementer reads it.

    Each needle is chosen so it CANNOT be present unless the prompt carries
    that duty rather than merely mentioning the vocabulary: the no-divergent
    delivery leg names the prohibition the clause states, the amendment leg
    names the failure reason's own content, and the proof-mode leg names the
    one edit an implementer is specifically forbidden from making instead of
    the general "do not edit" the section-ownership leg already covers.

    The structured-ending needle is deliberately NOT the bare
    `{"outcome": "failed"` shape: the prompt's generic needs-human protocol
    already carries that, so it would pass on a prompt that said nothing about
    a Definition of Done at all.
    """
    prompt = _prompt()

    # The rule itself — a run may not deliver what it was not dispatched with.
    assert "MUST NOT deliver behaviour that differs from the Definition of Done" in prompt
    # The trigger, and the ending it takes.
    assert "the section is wrong or incomplete" in prompt
    assert "the proposed amendment as the failure reason" in prompt
    assert "Definition of Done amendment for" in prompt
    # The two things the implementer must NOT do instead.
    assert "Publish no code that differs from the section" in prompt
    assert "do NOT edit the section" in prompt
    assert "MUST NOT change a proof mode" in prompt
    # Where the decision goes, and that it is the same one the gate takes.
    assert "resolve-blocked:" in prompt
    assert "whichever stage notices it" in prompt


def test_an_implement_amendment_rests_the_item_at_blocked_needs_human_and_publishes_nothing(
    tmp_path: Path,
    tenant: None,
) -> None:
    """The fifth gherkin, end to end: amendment in, blocked/needs-human out.

    Read the module docstring for why these four legs are one case. The
    assertions below run in the order the journey does.
    """
    del tenant
    _write_repo(root=tmp_path)
    item = _seed(root=tmp_path)
    graph = parse_workflow_graph(text=_dot())

    # LEG 1 — the committed graph. A failed implement outcome is routed by
    # CONDITION to the terminal, while the ordinary route is the unconditional
    # fallthrough that conditional edges outrank. Both targets are pinned in
    # one answer, so an added third route changes it rather than slipping past.
    assert _edge_conditions(source="implement") == {
        "needs_human": "outcome=failed",
        "implementation_diff": "",
    }
    # Nothing is downstream of the terminal, so nothing it reaches can publish.
    assert _reachable(graph=graph, start="needs_human") == frozenset()
    # The control: the publishing route EXISTS and is reachable the other way,
    # so the empty set above is an absence rather than a misspelt node name.
    assert {"publish_draft", "pr", "verify_pr", "exit"} <= _reachable(
        graph=graph, start="implementation_diff"
    )

    # LEG 2 — the production terminal mapper, on the sentinel the terminal
    # node emits. The item is blocked and the remedy is the ledger valve, not
    # an attach to a run that no longer exists.
    outcome = fabro_run_terminal_outcome(
        outcome_type=DispatchOutcome,
        plan=_plan(root=tmp_path),
        run_id=_RUN,
        inspect=None,
        exit_code=1,
        stderr=f"{_AMENDMENT}\n{NEEDS_HUMAN_MARKER}: {_AMENDMENT}\n",
    )
    assert outcome is not None
    assert (outcome.status, outcome.stage, outcome.fabro_run_id) == ("blocked", "fabro-run", _RUN)
    assert f"resolve-blocked:{_ITEM}:ready" in outcome.detail
    assert "fabro attach" not in outcome.detail

    # LEG 3 — the ledger rest state, written by production code over the real
    # store seam and read back through it.
    journal = JournalFile(path=tmp_path / "dispatch-journal.jsonl")
    escalate_needs_human_block(repo=tmp_path, item=item, outcome=outcome, journal=journal)
    assert _rested(root=tmp_path) == ("blocked", "needs-human")
    records = [json.loads(line) for line in journal.path.read_text().splitlines()]
    assert [record["stage"] for record in records] == ["needs-human-blocked"]
    assert records[0]["reason"] == "needs-human"

    # LEG 4 — the amendment is what the human is shown. The run is stamped onto
    # the item through the production writer, so the valve lane resolves the run
    # the way it does in production rather than being handed one.
    record_dispatch_run(
        path=store_config(repo=tmp_path),
        work_item_id=_ITEM,
        run_id=_RUN,
        factory_name=_FACTORY,
        factory_server=_SERVER,
    )
    runner = _InspectRunner(payload=_inspect_payload(amendment=_AMENDMENT))
    question = needs_human_question_from_payload(payload=runner.payload)
    assert question is not None
    assert question.prompt == _AMENDMENT
    summary = needs_human_question_summary(
        project_root=tmp_path,
        item_id=_ITEM,
        default_summary=f"resolve-blocked:{_ITEM}:ready",
        runner=runner,
    )
    assert _AMENDMENT in summary
    assert f"resolve-blocked:{_ITEM}:ready" in summary
    # The read was aimed at the factory the run was stamped with, not at a
    # default host where it would have returned cleanly and found nothing. The
    # binary itself is whatever this environment resolves and is not asserted.
    assert [argv[1:] for argv in runner.argv] == [["inspect", _RUN, "--json", "--server", _SERVER]]
