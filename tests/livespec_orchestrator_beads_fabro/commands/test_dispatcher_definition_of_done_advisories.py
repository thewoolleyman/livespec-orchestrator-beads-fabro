"""Tests for the ADVISORY half of the host-side Definition-of-Done wall (v115).

The Definition-of-Done-and-Proof-of-Done clause of `SPECIFICATION/contracts.md`
splits a filing-time finding in two, and the split decides a lifecycle
transition: "A MECHANICAL finding ... withholds `ready` ... A test-existence or
scenario-reference finding the wall recognises is ADVISORY: it MUST be displayed
and MUST NOT withhold `ready`, because only the gate can judge it." These cases
bind the advisory half.

WHY THE MODULE IS IMPORTED INSIDE EACH TEST BODY. A top-level
`import _dispatcher_definition_of_done_advisories` would make the Red a
COLLECTION error — zero assertions run — which proves only that a module is
unimportable and not that the behaviour is unimplemented. The first assertion of
the shape case is therefore a genuine check on the module path, which fails
before any import is reached.

WHY EVERY NEGATIVE CASE CARRIES A POSITIVE CONTROL IN THE SAME FIXTURE. An
advisory rule that returned nothing at all would satisfy every "no finding"
assertion here on its own. Each clearing case is therefore the SAME description
and the SAME spec tree as a case that does report, differing in exactly the one
element the rule keys on.
"""

from __future__ import annotations

import importlib
from dataclasses import replace
from pathlib import Path

from livespec_orchestrator_beads_fabro.types import WorkItem

_MODULE = "livespec_orchestrator_beads_fabro.commands._dispatcher_definition_of_done_advisories"
_MODULE_PATH = Path(
    ".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/"
    "_dispatcher_definition_of_done_advisories.py"
)

# A scenario heading whose title shares its distinctive vocabulary with the
# assertion below it, which is what the candidate rule keys on.
_SCENARIO_HEADING = (
    "## Scenario 999 — The dispatcher refuses an unresolvable workflow variant"
    " before claiming the item"
)
_GENERIC_HEADING = "## Runtime requirements"
# The assertion the heading above governs. Its distinctive terms — dispatcher,
# refuses, unresolvable, workflow, variant, claiming — overlap the heading well
# past the threshold, so a build that never reported a candidate would fail.
_GOVERNED_ASSERTION = (
    "The dispatcher refuses an unresolvable workflow variant before claiming the item."
)
# An assertion sharing nothing distinctive with the heading above. It is the
# control for the candidate rule: a build that reported a candidate for every
# assertion would fail on it.
_UNGOVERNED_ASSERTION = "The emitted overlay file carries one environment table."


def _item(**overrides: object) -> WorkItem:
    base = WorkItem(
        id="bd-ib-adv",
        type="task",
        status="ready",
        title="An advisory-graded task",
        description="Do the thing.",
        origin="freeform",
        gap_id=None,
        rank="a2",
        assignee=None,
        depends_on=(),
        captured_at="2026-10-04T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="auto",
        acceptance_policy="ai-only",
    )
    return replace(base, **overrides)


def _repo(*, tmp_path: Path, scenarios: str | None = None) -> Path:
    """A repository carrying a governed spec tree with one scenario heading."""
    repo = tmp_path / "repo"
    spec = repo / "SPECIFICATION"
    spec.mkdir(parents=True)
    body = (
        f"# Scenarios\n\n{_SCENARIO_HEADING}\n\nSome prose.\n" if scenarios is None else scenarios
    )
    _ = (spec / "scenarios.md").write_text(body, encoding="utf-8")
    _ = (spec / "contracts.md").write_text(
        f"# Contracts\n\n{_GENERIC_HEADING}\n\nSome prose.\n", encoding="utf-8"
    )
    return repo


def _description(*, assertions: tuple[str, ...], references: str) -> str:
    bullets = "".join(f"- {assertion}\n" for assertion in assertions)
    return f"## Definition of Done\n\n{bullets}\nReferences: {references}\n"


def _findings(*, item: WorkItem, cwd: Path) -> tuple[str, ...]:
    module = importlib.import_module(_MODULE)
    return module.advisory_definition_of_done_findings(item=item, cwd=cwd)


def test_the_advisory_module_is_a_module_of_its_own_exporting_its_two_public_names() -> None:
    """The shape case, and the one whose first assertion fails before any import.

    The two names are separate because the callers differ: the hygiene lane needs
    only the findings, while a surface naming the governing scenario needs the
    heading set the candidate rule read.
    """
    assert _MODULE_PATH.is_file()

    module = importlib.import_module(_MODULE)

    assert set(module.__all__) == {
        "SCENARIO_HEADING_PREFIX",
        "advisory_definition_of_done_findings",
        "scenario_headings",
    }
    assert module.SCENARIO_HEADING_PREFIX == "Scenario "


def test_the_scenario_headings_are_read_from_the_spec_trees_own_scenarios_file(
    tmp_path: Path,
) -> None:
    module = importlib.import_module(_MODULE)

    headings = module.scenario_headings(repo=_repo(tmp_path=tmp_path))

    assert headings == (_SCENARIO_HEADING[len("## ") :],)


def test_a_non_scenario_h2_and_a_level_one_heading_are_not_scenario_headings(
    tmp_path: Path,
) -> None:
    """The file's other headings must not enter the candidate set.

    A build that returned every heading would report a candidate against an
    assertion no scenario governs, which is a finding the operator cannot repair.
    """
    module = importlib.import_module(_MODULE)
    repo = _repo(
        tmp_path=tmp_path,
        scenarios="# Scenarios\n\n## Runtime notes\n\nprose\n",
    )

    assert module.scenario_headings(repo=repo) == ()


def test_an_unreadable_scenarios_file_yields_no_headings(tmp_path: Path) -> None:
    """An environment fault withholds the candidate rule rather than inventing one."""
    module = importlib.import_module(_MODULE)
    repo = tmp_path / "repo"
    (repo / "SPECIFICATION" / "scenarios.md").mkdir(parents=True)

    assert module.scenario_headings(repo=repo) == ()


def test_an_item_with_no_definition_of_done_section_reports_no_advisory_finding(
    tmp_path: Path,
) -> None:
    """The absent section is the MECHANICAL wall's finding, reported once over there.

    Reporting it here too would name one fault twice and would withhold `ready`
    on an advisory row, which is exactly the consequence the split forbids.
    """
    item = _item(description="Just prose, no section at all.")

    assert _findings(item=item, cwd=_repo(tmp_path=tmp_path)) == ()


def test_a_test_existence_assertion_is_reported_with_the_form_and_the_remedy(
    tmp_path: Path,
) -> None:
    item = _item(
        description=_description(
            assertions=("Tests prove the valve refuses an unverified item.",),
            references=_SCENARIO_HEADING,
        )
    )

    findings = _findings(item=item, cwd=_repo(tmp_path=tmp_path))

    assert len(findings) == 1
    assert item.id in findings[0]
    assert "tests prove" in findings[0]
    assert "restate it as the behaviour" in findings[0]


def test_an_aggregate_passing_assertion_is_reported_as_a_test_existence_form(
    tmp_path: Path,
) -> None:
    """The janitor already guarantees the aggregate, so restating it carries nothing."""
    item = _item(
        description=_description(
            assertions=("The full just check aggregate passes.",),
            references=_SCENARIO_HEADING,
        )
    )

    findings = _findings(item=item, cwd=_repo(tmp_path=tmp_path))

    assert len(findings) == 1
    assert "aggregate passes" in findings[0]


def test_a_behavioural_assertion_reports_no_test_existence_finding(tmp_path: Path) -> None:
    """The control for the two cases above, in the same fixture and reference line."""
    item = _item(
        description=_description(
            assertions=(_UNGOVERNED_ASSERTION,),
            references=_SCENARIO_HEADING,
        )
    )

    assert _findings(item=item, cwd=_repo(tmp_path=tmp_path)) == ()


def test_a_carrier_relation_stated_inside_the_section_is_reported(tmp_path: Path) -> None:
    """The carrier relation belongs to the epic's carrier map, never to the section."""
    item = _item(
        description=_description(
            assertions=("This child carries the plan assertion about overlay tables.",),
            references=_SCENARIO_HEADING,
        )
    )

    findings = _findings(item=item, cwd=_repo(tmp_path=tmp_path))

    assert len(findings) == 1
    assert "plan assertion" in findings[0]
    assert "carrier map" in findings[0]


def test_the_same_carrier_statement_as_prose_before_the_heading_is_not_a_finding(
    tmp_path: Path,
) -> None:
    """The ratified converse, and the reason the rule reads the SECTION only.

    The clause permits the description to repeat the carrier relation "as prose
    before the Definition of Done heading"; only a bullet INSIDE the section is a
    finding. The section parse starts at the description's first heading, so the
    permitted form is never an assertion at all.
    """
    item = _item(
        description=(
            "This child carries the plan assertion about overlay tables.\n"
            "\n"
            f"{_description(assertions=(_UNGOVERNED_ASSERTION,), references=_SCENARIO_HEADING)}"
        )
    )

    assert _findings(item=item, cwd=_repo(tmp_path=tmp_path)) == ()


def test_a_generic_reference_where_a_scenario_states_the_behaviour_names_that_scenario(
    tmp_path: Path,
) -> None:
    item = _item(
        description=_description(
            assertions=(_GOVERNED_ASSERTION,),
            references=_GENERIC_HEADING,
        )
    )

    findings = _findings(item=item, cwd=_repo(tmp_path=tmp_path))

    assert len(findings) == 1
    assert item.id in findings[0]
    assert _SCENARIO_HEADING[len("## ") :] in findings[0]


def test_a_reference_line_naming_a_scenario_reports_no_scenario_reference_finding(
    tmp_path: Path,
) -> None:
    """The control: the SAME assertion, differing only in the reference line."""
    item = _item(
        description=_description(
            assertions=(_GOVERNED_ASSERTION,),
            references=_SCENARIO_HEADING,
        )
    )

    assert _findings(item=item, cwd=_repo(tmp_path=tmp_path)) == ()


def test_a_bare_scenario_title_with_no_marker_also_counts_as_naming_a_scenario(
    tmp_path: Path,
) -> None:
    """A reference that omits the `## ` marker names the same real heading."""
    item = _item(
        description=_description(
            assertions=(_GOVERNED_ASSERTION,),
            references=_SCENARIO_HEADING[len("## ") :],
        )
    )

    assert _findings(item=item, cwd=_repo(tmp_path=tmp_path)) == ()


def test_a_generic_reference_with_no_governing_scenario_reports_nothing(
    tmp_path: Path,
) -> None:
    """The second control: the SAME generic reference, an assertion no scenario states."""
    item = _item(
        description=_description(
            assertions=(_UNGOVERNED_ASSERTION,),
            references=_GENERIC_HEADING,
        )
    )

    assert _findings(item=item, cwd=_repo(tmp_path=tmp_path)) == ()


def test_an_unreadable_spec_tree_withholds_the_scenario_rule_entirely(tmp_path: Path) -> None:
    """No heading set is not an empty heading set; absence of evidence reports nothing."""
    item = _item(
        description=_description(
            assertions=(_GOVERNED_ASSERTION,),
            references=_GENERIC_HEADING,
        )
    )

    assert _findings(item=item, cwd=tmp_path / "absent") == ()


def test_every_recognised_form_of_one_assertion_is_reported_together(tmp_path: Path) -> None:
    """One assertion can carry more than one advisory fault, and each is named.

    Collapsing them would hide whichever the first rule did not match, and the two
    remedies are different edits.
    """
    item = _item(
        description=_description(
            assertions=(
                "Regression tests cover the plan assertion this child carries.",
                _GOVERNED_ASSERTION,
            ),
            references=_GENERIC_HEADING,
        )
    )

    findings = _findings(item=item, cwd=_repo(tmp_path=tmp_path))

    assert len(findings) == 3
    assert any("regression tests" in finding for finding in findings)
    assert any("plan assertion" in finding for finding in findings)
    assert any(_SCENARIO_HEADING[len("## ") :] in finding for finding in findings)
