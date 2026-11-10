"""Referenced Definition-of-Done clauses stay readable in condensed prompts.

This regression uses the public livespec-dev-tooling v111 specification fixture
recorded at commit ``1ebd5994``.  It proves that a work item's own reference
line is retrieval evidence, rather than text which lexical retrieval may lose
to a much longer unrelated clause.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field, replace
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_definition_of_done import (
    definition_of_done,
)
from livespec_orchestrator_beads_fabro.commands._dod_governing_heading import (
    governing_heading_statement,
)
from livespec_orchestrator_beads_fabro.commands._spec_change_tier import (
    asked_for_behaviour,
)
from livespec_orchestrator_beads_fabro.commands._spec_stated_citation import (
    judged_prompt_ceiling,
)
from livespec_orchestrator_beads_fabro.commands._spec_tree_condensation import (
    _TERM,
    ELIDED_BODY_MARKER,
    PROMPT_CHARACTER_CEILING,
    _relevance_order,
    _sections_of,
    condensed_spec_tree,
)
from livespec_orchestrator_beads_fabro.types import WorkItem
from livespec_runtime.spec_stated import judge

_FIXTURE_ROOT = (
    Path(__file__).parents[2] / "fixtures" / "livespec-dev-tooling-v111" / "SPECIFICATION"
)
_REFERENCED_HEADING = "## Delegated gate-runner runs"
_SECOND_REFERENCED_HEADING = (
    "## Scenario: a seat's gate-runner full suite runs as a gate Job by default"
)
_THIRD_REFERENCED_HEADING = (
    "## Scenario: a delegated gate-runner run with no cluster verdict ends without a verdict"
)

_IALGTQ_DESCRIPTION = """## Definition of Done

References: ## Delegated gate-runner runs, ## Scenario: a seat's gate-runner full suite runs as a gate Job by default, ## Scenario: a delegated gate-runner run with no cluster verdict ends without a verdict

- In a repository with `delegated_gate = true`, on a host that can read the gates kubeconfig, `gate-start -- just check` writes a tree for the worktree's current content, including uncommitted changes, from a temporary index, and leaves the worktree's own index unchanged.
- That run publishes the tree to the gate mirror, runs the dispatched command as a gates Job against it, streams the Job's output into the run's `output.log`, and records `venue: cluster_job`, the Job name and the tree hash in the run record.
- A delegated `gate-start` run whose cluster returns no verdict ends as `DIED_WITHOUT_VERDICT`, `gate-wait` exits `75`, and the command is not re-run on the launching host.

### Host-captured

Reason: proof needs a delegating operator host (the dev host) holding the gates kubeconfig to submit a gate Job, and the released build pinned in this repository; a factory sandbox holds neither.

- On the dev host in livespec-dev-tooling, `gate-start -- just check` in a worktree with an uncommitted change runs as a gates Job against a tree including that change; the run record carries `venue: cluster_job`, the Job name and the tree hash, and the Job's output streams into the run's `output.log`.
- On the dev host, a `gate-start -- just check` whose gate Job is lost before reporting ends as `DIED_WITHOUT_VERDICT`, `gate-wait` exits `75`, and no local re-run starts.

## Context

This item is slice 2 of 2 of plan dev-host-test-gate-load's carrier for DoD assertion 4 (epic livespec-dev-tooling-6vuiwe). It was split out of livespec-dev-tooling-qgv3tb on 2026-11-02 after run 01M6D3BF5RMZ exhausted its implement re-entry budget waiting on commit hooks. It depends on qgv3tb, whose `livespec_dev_tooling/gate_runner_delegate.py` venue selector decides when this path runs.

Reuse the existing gate client rather than writing a second one: `gate_remote_delegate.gate_remote_request` / `gate_remote_verdict.run_gated_push` publish a tree and run a Job, and `commit_replay_delegate.py` (livespec-dev-tooling-kpk6uz) already runs a Job over a non-pushed tree. The detached runner is pack-generated from `livespec_dev_tooling/worktree_pack/gate-run.sh`. Contract: SPECIFICATION/contracts.md §"Delegated gate-runner runs" (v108).

Write each assertion's complete contract as ONE Red test before its Green, so a later Red is not refused by the aggregate's coverage member.
"""

_ITEM = WorkItem(
    id="livespec-dev-tooling-ialgtq",
    title=(
        "gate-start runs a delegated full suite as a gates Job over the worktree "
        "tree and ends a lost Job without a verdict (slice 2 of 2)"
    ),
    description=_IALGTQ_DESCRIPTION,
    acceptance_criteria="",
    type="feature",
    status="ready",
    origin="freeform",
    gap_id=None,
    rank="a0",
    assignee=None,
    depends_on=(),
    captured_at="2026-11-02T00:00:00Z",
    resolution=None,
    reason=None,
    audit=None,
    superseded_by=None,
)


@dataclass(kw_only=True)
class _PromptRecorder:
    """A model seam retaining the bytes its judgement renderer received."""

    prompts: list[str] = field(default_factory=list)

    def __call__(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return (
            '{"kind": "unstated", "stated_by": [], "generalization_target": null, "rationale": ""}'
        )


def _fixture_tree() -> dict[str, str]:
    """The v111 top-level specification files, in the spec reader's shape."""
    return {path.name: path.read_text() for path in sorted(_FIXTURE_ROOT.glob("*.md"))}


def _body(*, tree: dict[str, str], heading: str) -> str:
    """The exact H2 body a fixture tree gives one heading."""
    return next(
        section.body
        for path in tree
        for section in _sections_of(path=path, text=tree[path])
        if section.heading == heading
    )


def _old_raw_order(*, tree: dict[str, str], statement: str) -> list[str | None]:
    """The pre-fix raw-sum ordering, retained only as a regression control."""
    sections = [
        section for path in sorted(tree) for section in _sections_of(path=path, text=tree[path])
    ]
    wanted = frozenset(_TERM.findall(statement.casefold()))
    frequency = Counter(term for section in sections for term in section.terms & wanted)
    return [
        section.heading
        for section in sorted(
            sections,
            key=lambda section: (
                -sum(1.0 / (1 + frequency[term]) for term in section.terms & wanted),
                section.path,
                section.index,
            ),
        )
    ]


def test_references_are_selected_before_lexically_more_relevant_unreferenced_clauses() -> None:
    """A referenced clause is whole before retrieval spends a byte elsewhere."""
    referenced = "## Governing contract"
    unrelated = "## Lexically tempting background"
    governing_body = "The definitive contract applies here. " * 120
    tempting_body = "delegated gate runner full suite worktree verdict " * 1000
    tree = {"contracts.md": f"{referenced}\n\n{governing_body}\n{unrelated}\n\n{tempting_body}"}
    statement = (
        "## Definition of Done\n\n"
        f"References: {referenced}\n\n"
        "- A delegated gate runner full suite records a worktree verdict."
    )

    condensed = condensed_spec_tree(spec_tree=tree, statement=statement, ceiling=16_000)

    assert governing_body in condensed["contracts.md"]
    assert tempting_body not in condensed["contracts.md"]
    assert (
        ELIDED_BODY_MARKER in condensed["contracts.md"]
        or "partially withheld" in condensed["contracts.md"]
    )


def test_referenced_clauses_are_partially_withheld_in_reference_order_and_fit_the_prompt() -> None:
    """A small budget spends itself on references, in their authored order."""
    first = "## First governing contract"
    second = "## Second governing contract"
    first_body = "First contract detail. " * 2500
    second_body = "Second contract detail. " * 2500
    tree = {"contracts.md": f"{first}\n\n{first_body}\n{second}\n\n{second_body}"}
    statement = f"## Definition of Done\n\nReferences: {first}, {second}\n\n- A fact."

    condensed = condensed_spec_tree(spec_tree=tree, statement=statement, ceiling=20_000)
    rendered = condensed["contracts.md"]
    recorder = _PromptRecorder()
    _ = judge(spec_tree=condensed, statement=statement, run_model=recorder)

    assert first_body[:100] in rendered
    assert first_body not in rendered
    assert "partially withheld" in rendered
    assert second_body not in rendered
    assert rendered.index(first) < rendered.index(second)
    assert len(recorder.prompts[0]) < 20_000


def test_length_normalisation_prefers_the_short_distinctive_clause_over_a_tenfold_longer_one() -> (
    None
):
    """Clause length cannot buy relevance merely by accumulating vocabulary."""
    short = "## Short distinctive clause"
    long = "## Long background clause"
    distinctive = "distinctivealpha distinctivebeta distinctivegamma"
    broad = "broadone broadtwo broadthree broadfour broadsix broadseven"
    short_body = f"{distinctive} " + ("short context " * 300)
    filler = " ".join(f"filler{number:03}" for number in range(500))
    long_body = f"{broad} {filler} " + ("padding " * 5000)
    tree = {"contracts.md": f"{short}\n\n{short_body}\n{long}\n\n{long_body}"}
    statement = f"{distinctive} {broad}"

    ordered = _relevance_order(
        sections=[section for path in tree for section in _sections_of(path=path, text=tree[path])],
        statement=statement,
        term_pattern=_TERM,
    )

    assert len(long_body) > len(short_body) * 10
    assert [section.heading for section in ordered[:2]] == [short, long]


def test_v111_ialgtq_keeps_the_delegated_gate_runner_clause_and_every_h2_heading() -> None:
    """The reported live failure stays fixed against its archived v111 input."""
    tree = _fixture_tree()
    statement = asked_for_behaviour(item=_ITEM)
    condensed = condensed_spec_tree(spec_tree=tree, statement=statement)
    # The control reads the archived input: the statement as it rendered the whole
    # description, proof-mode sub-heading and `Reason:` line included, which is
    # the text the reported failure was measured on.
    archived_statement = "\n\n".join(
        [
            f"Work item {_ITEM.id}",
            f"Title: {_ITEM.title}",
            f"Description: {_ITEM.description.strip()}",
            "Acceptance criteria: (none recorded)",
        ]
    )
    old_order = _old_raw_order(tree=tree, statement=archived_statement)

    assert _REFERENCED_HEADING in old_order[4:], (
        "the archived fixture no longer proves that raw relevance would have "
        "withheld the cited delegated-gate clause"
    )
    assert _body(tree=tree, heading=_REFERENCED_HEADING) in "".join(condensed.values())
    for path, text in tree.items():
        for section in _sections_of(path=path, text=text):
            if section.heading is not None:
                assert section.heading in condensed[path]


def test_governing_heading_judgement_pins_the_same_references_as_the_work_item_judgement() -> None:
    """Verdict reuse reads the exact referenced clauses a fresh prompt receives."""
    tree = _fixture_tree()
    section = definition_of_done(description=_ITEM.description)
    fresh = condensed_spec_tree(spec_tree=tree, statement=asked_for_behaviour(item=_ITEM))
    governing = condensed_spec_tree(
        spec_tree=tree,
        statement=governing_heading_statement(item=_ITEM, section=section),
    )

    expected = {_REFERENCED_HEADING, _SECOND_REFERENCED_HEADING, _THIRD_REFERENCED_HEADING}
    assert expected <= {clause.heading for clause in fresh.clauses}
    assert expected <= {clause.heading for clause in governing.clauses}


def test_a_bare_reference_line_pins_its_clause_as_the_reuse_statement_renders_it() -> None:
    """The governing-heading statement carries no Definition-of-Done heading."""
    referenced = "## Governing contract"
    governing_body = "The definitive contract applies here. " * 120
    tempting_body = "delegated gate runner full suite worktree verdict " * 1000
    tree = {
        "contracts.md": (
            f"{referenced}\n\n{governing_body}\n"
            f"## Lexically tempting background\n\n{tempting_body}"
        )
    }
    item = replace(
        _ITEM,
        title="Delegated gate runner",
        description=(
            "## Definition of Done\n\n"
            f"References: {referenced}\n\n"
            "- A delegated gate runner full suite records a worktree verdict.\n"
        ),
    )
    statement = governing_heading_statement(
        item=item, section=definition_of_done(description=item.description)
    )

    condensed = condensed_spec_tree(spec_tree=tree, statement=statement, ceiling=16_000)

    assert not statement.startswith("## Definition of Done")
    assert f"References: {referenced}" in statement
    assert governing_body in condensed["contracts.md"]
    assert referenced in {clause.heading for clause in condensed.clauses}


def test_an_unnamed_relevant_clause_is_still_carried_in_part_once_references_fit() -> None:
    """Pinning references spends budget first, then retrieval spends the rest."""
    referenced = "## Governing contract"
    governing_body = "The definitive contract applies here. " * 20
    tempting_body = "delegated gate runner full suite worktree verdict " * 1000
    tree = {
        "contracts.md": (
            f"{referenced}\n\n{governing_body}\n"
            f"## Lexically tempting background\n\n{tempting_body}"
        )
    }
    statement = (
        "## Definition of Done\n\n"
        f"References: {referenced}\n\n"
        "- A delegated gate runner full suite records a worktree verdict."
    )

    rendered = condensed_spec_tree(spec_tree=tree, statement=statement, ceiling=16_000)[
        "contracts.md"
    ]

    assert governing_body in rendered
    assert tempting_body[:200] in rendered
    assert tempting_body not in rendered
    assert "partially withheld" in rendered


def test_overflowed_references_share_budget_with_deep_relevant_paragraphs_first() -> None:
    """Referenced sections spend an overflow budget on their matching paragraphs.

    Each cited section puts its governing paragraph after enough unrelated text
    that the former leading-prefix selection withholds both paragraphs.  The
    two cited paragraphs share different terms with the asked-for behaviour,
    which also proves that one reference cannot consume the other reference's
    useful share of the prompt.
    """
    first_heading = "## First cited contract"
    second_heading = "## Second cited contract"
    first_leading = "unrelated introduction " * 4_000
    second_leading = "unrelated background " * 4_000
    refresh_repair = "**Refresh repair.** A refused refresh commit restores the pre-refresh head.\n"
    budget_sharing = "A cited section shares the prompt budget with every cited paragraph.\n"
    tree = {
        "contracts.md": (
            f"{first_heading}\n\n{first_leading}\n\n{refresh_repair}\n"
            f"{second_heading}\n\n{second_leading}\n\n{budget_sharing}\n"
        )
    }
    statement = (
        "## Definition of Done\n\n"
        f"References: {first_heading}, {second_heading}\n\n"
        "- A refused refresh commit takes refresh repair.\n"
        "- Every cited paragraph shares the prompt budget.\n"
    )

    condensed = condensed_spec_tree(spec_tree=tree, statement=statement, ceiling=24_000)
    rendered = condensed["contracts.md"]

    assert refresh_repair in rendered
    assert budget_sharing in rendered
    assert first_leading not in rendered
    assert second_leading not in rendered
    assert condensed == condensed_spec_tree(spec_tree=tree, statement=statement, ceiling=24_000)


def test_uq2ocd_overflow_keeps_the_whole_deep_refresh_repair_paragraph() -> None:
    """The reported UQ2ocd shape preserves its cited refresh-repair evidence."""
    references = (
        "## Dispatcher admission, WIP cap, and post-merge acceptance, "
        "## Scenario 176 — The spec-change tier is decided by the spec-stated judgement, "
        "and a feature waits for ratification, "
        "## Self-contained plugin dispatch, ## Work-item state semantics, "
        "## Dispatch-time baseline conformance gate"
    )
    item = replace(
        _ITEM,
        id="bd-ib-uq2ocd",
        title="A refresh commit refused by a hook takes the Refresh repair route",
        description=(
            "## Definition of Done\n\n"
            f"References: {references}\n\n"
            "- A refresh commit refused by the commit hook restores the pre-refresh head "
            "and routes to refresh repair.\n"
        ),
    )
    # The ceiling below was measured against the tree current when this shape was
    # reported, so the tree is pinned to that immutable snapshot (v283) rather than
    # to the live specification, whose every growth would silently move the edge.
    tree = {
        path.name: path.read_text()
        for path in sorted(
            Path(__file__).parents[3].joinpath("SPECIFICATION", "history", "v283").glob("*.md")
        )
    }
    self_contained = _body(tree=tree, heading="## Self-contained plugin dispatch")
    refresh_start = self_contained.index("**Refresh repair.**")
    refresh_repair = self_contained[refresh_start:].split("\n\n", maxsplit=1)[0]
    statement = asked_for_behaviour(item=item)

    condensed = condensed_spec_tree(spec_tree=tree, statement=statement, ceiling=168_422)

    assert refresh_repair in "".join(condensed.values())


def test_uq2ocd_shape_keeps_its_refresh_repair_paragraph_at_the_production_ceiling() -> None:
    """The statement's own field labels carry no topic, so they do not outrank its subject.

    At the ceiling production derives from the v328 tree, the five cited sections
    overflow, and the labels a rendered statement carries ("Acceptance criteria",
    "Definition of Done", "Title") used to rank unrelated paragraphs above the
    cited Refresh repair paragraph.
    """
    item = replace(
        _ITEM,
        id="bd-ib-uq2ocd",
        title="A refresh commit refused by a hook takes the Refresh repair route",
        description=(
            "## Definition of Done\n\n"
            "References: ## Dispatcher admission, WIP cap, and post-merge acceptance, "
            "## Self-contained plugin dispatch, ## Work-item state semantics, "
            "## Dispatch-time baseline conformance gate\n\n"
            "- A refresh commit refused by the commit hook restores the pre-refresh head "
            "and routes to refresh repair.\n"
        ),
    )
    tree = {
        path.name: path.read_text()
        for path in sorted(
            Path(__file__).parents[3].joinpath("SPECIFICATION", "history", "v328").glob("*.md")
        )
    }
    self_contained = _body(tree=tree, heading="## Self-contained plugin dispatch")
    refresh_start = self_contained.index("**Refresh repair.**")
    refresh_repair = self_contained[refresh_start:].split("\n\n", maxsplit=1)[0]

    condensed = condensed_spec_tree(
        spec_tree=tree,
        statement=asked_for_behaviour(item=item),
        ceiling=judged_prompt_ceiling(spec_tree=tree, ceiling=PROMPT_CHARACTER_CEILING),
    )

    assert refresh_repair in "".join(condensed.values())
