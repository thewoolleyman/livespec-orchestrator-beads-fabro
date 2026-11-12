"""Tests for the Definition-of-Done findings graded against the spec tree (v114).

The effective-acceptance-criteria clause of `SPECIFICATION/contracts.md` requires
the reference line to be "validated against the H2 set read from the spec tree's
own files, never against a test fixture", and requires an unresolved reference to
be reported as a finding "naming the unresolved heading text". These tests
therefore build a real spec tree in `tmp_path` and read the H2 set out of it.

THE COMMA CASE IS THE LOAD-BEARING ONE. Ratified scenario headings contain
commas — `## Scenario 133 — A mixed item is refused ai-only from every entry
path, parks for its human-attested leg, ...` has two — so a reference line split
naively on `, ` shreds one heading into three unresolvable fragments and reports
three findings against a perfectly valid item. The refusal reads exactly like a
real defect, so nothing downstream would catch it.

The reference check reads `origin/master` rather than the working tree
(work-item bd-ib-ahtcng); `test_dispatcher_definition_of_done_origin_revision.py`
and `test_dispatcher_definition_of_done_origin_spec.py` exercise that read against
real repositories. The trees built here are plain directories, which the suite's
hermetic stand-in (`_hermetic_origin_spec_headings`) answers from their own
`SPECIFICATION/` working tree, so these cases isolate the finding logic from the
git read.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_definition_of_done_findings import (
    definition_of_done_findings,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

_COMMA_HEADING = (
    "## Scenario 133 — A mixed item is refused ai-only from every entry path,"
    " parks for its human-attested leg, and the accept valve refuses until the record exists"
)
_PLAIN_HEADING = "## Effective acceptance criteria"


def _item(**overrides: object) -> WorkItem:
    base = WorkItem(
        id="bd-ib-v114",
        type="task",
        status="ready",
        title="A gated task",
        description="Do the thing.",
        origin="freeform",
        gap_id=None,
        rank="a2",
        assignee=None,
        depends_on=(),
        captured_at="2026-09-30T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="auto",
        acceptance_policy="ai-only",
    )
    return replace(base, **overrides)


def _spec_tree(*, tmp_path: Path) -> Path:
    """A repository carrying a governed spec tree with two real H2 headings."""
    repo = tmp_path / "repo"
    spec = repo / "SPECIFICATION"
    spec.mkdir(parents=True)
    _ = (spec / "contracts.md").write_text(
        f"# Contracts\n\n{_PLAIN_HEADING}\n\nSome prose.\n", encoding="utf-8"
    )
    _ = (spec / "scenarios.md").write_text(
        f"# Scenarios\n\n{_COMMA_HEADING}\n\nSome prose.\n", encoding="utf-8"
    )
    return repo


def _description(*, references: str) -> str:
    return (
        "## Definition of Done\n"
        "\n"
        "- The wall names the offending element of the section.\n"
        "\n"
        f"References: {references}\n"
    )


def test_a_reference_to_a_heading_the_spec_tree_carries_produces_no_finding(
    tmp_path: Path,
) -> None:
    repo = _spec_tree(tmp_path=tmp_path)
    item = _item(description=_description(references=_PLAIN_HEADING))

    assert definition_of_done_findings(item=item, cwd=repo) == ()


def test_a_goal_template_opener_in_every_editable_item_field_is_a_mechanical_finding(
    tmp_path: Path,
) -> None:
    opener = "{" + "{"
    item = _item(
        title=f"title {opener}",
        description=f"description {opener}",
        acceptance_criteria=f"acceptance {opener}",
        notes=f"notes {opener}",
    )

    findings = definition_of_done_findings(item=item, cwd=_spec_tree(tmp_path=tmp_path))

    assert len(findings) == 5
    template_findings = findings[:4]
    for field, offset, finding in zip(
        ("title", "description", "acceptance criteria", "notes"),
        (6, 12, 11, 6),
        template_findings,
        strict=True,
    ):
        assert field in finding
        assert f"offset {offset}" in finding
        assert opener not in finding


def test_a_reference_without_its_h2_marker_is_a_mechanical_finding(
    tmp_path: Path,
) -> None:
    repo = _spec_tree(tmp_path=tmp_path)
    reference = _PLAIN_HEADING.removeprefix("## ")
    item = _item(description=_description(references=reference))

    findings = definition_of_done_findings(item=item, cwd=repo)

    assert len(findings) == 1
    assert reference in findings[0]


def test_a_multi_reference_line_of_comma_carrying_headings_resolves_whole(
    tmp_path: Path,
) -> None:
    # Two references, one of which contains two commas of its own. A naive
    # `, ` split reports three unresolved fragments here.
    repo = _spec_tree(tmp_path=tmp_path)
    item = _item(description=_description(references=f"{_COMMA_HEADING}, {_PLAIN_HEADING}"))

    assert definition_of_done_findings(item=item, cwd=repo) == ()


def test_an_unresolved_reference_names_the_heading_text(tmp_path: Path) -> None:
    repo = _spec_tree(tmp_path=tmp_path)
    item = _item(description=_description(references="## Scenario 999 — No such heading"))

    findings = definition_of_done_findings(item=item, cwd=repo)

    assert len(findings) == 1
    assert "bd-ib-v114" in findings[0]
    assert "## Scenario 999 — No such heading" in findings[0]


def test_an_absent_section_names_the_missing_section(tmp_path: Path) -> None:
    findings = definition_of_done_findings(
        item=_item(description="Do the thing.\n"), cwd=_spec_tree(tmp_path=tmp_path)
    )

    assert len(findings) == 1
    assert "bd-ib-v114" in findings[0]
    assert "Definition of Done" in findings[0]


def test_a_section_with_no_reference_line_names_the_missing_reference_line(
    tmp_path: Path,
) -> None:
    description = "## Definition of Done\n\n- The section carries no reference line.\n"

    findings = definition_of_done_findings(
        item=_item(description=description), cwd=_spec_tree(tmp_path=tmp_path)
    )

    assert len(findings) == 1
    assert "References:" in findings[0]


def test_an_empty_reference_line_is_no_reference_line(tmp_path: Path) -> None:
    findings = definition_of_done_findings(
        item=_item(description=_description(references="")), cwd=_spec_tree(tmp_path=tmp_path)
    )

    assert len(findings) == 1
    assert "References:" in findings[0]


def test_a_human_attested_sub_heading_with_no_reason_line_is_a_finding(
    tmp_path: Path,
) -> None:
    description = (
        "## Definition of Done\n"
        "\n"
        "### Human-attested\n"
        "\n"
        "- A human attests this one.\n"
        "\n"
        f"References: {_PLAIN_HEADING}\n"
    )

    findings = definition_of_done_findings(
        item=_item(description=description), cwd=_spec_tree(tmp_path=tmp_path)
    )

    assert len(findings) == 1
    assert "bd-ib-v114" in findings[0]
    assert "Human-attested" in findings[0]
    assert "Reason:" in findings[0]


def test_a_host_captured_sub_heading_with_no_reason_line_is_a_finding(
    tmp_path: Path,
) -> None:
    # The MECHANICAL half of the gate runs on the host, so this is what withholds
    # `ready` from the item: the approve valve consumes the same finding set.
    description = (
        "## Definition of Done\n"
        "\n"
        "### Host-captured\n"
        "\n"
        "- An agent session captures this one on a host.\n"
        "\n"
        f"References: {_PLAIN_HEADING}\n"
    )

    findings = definition_of_done_findings(
        item=_item(description=description), cwd=_spec_tree(tmp_path=tmp_path)
    )

    assert len(findings) == 1
    assert "bd-ib-v114" in findings[0]
    assert "Host-captured" in findings[0]
    assert "Reason:" in findings[0]
    # The MODE and the REMEDY are the host ones. Both halves matter: the finding
    # naming `human_attested` would be a true statement about a different
    # sub-heading, and the remedy naming the sandbox capability would send the
    # author to write a sentence that cannot clear a host-captured declaration.
    assert "host_captured" in findings[0]
    assert "human_attested" not in findings[0]
    assert "released-build requirement" in findings[0]


def test_a_host_captured_sub_heading_with_a_reason_line_is_no_finding(
    tmp_path: Path,
) -> None:
    description = (
        "## Definition of Done\n"
        "\n"
        "### Host-captured\n"
        "\n"
        "Reason: the proof needs the released build installed on an operator host.\n"
        "\n"
        "- An agent session captures this one on a host.\n"
        "\n"
        f"References: {_PLAIN_HEADING}\n"
    )

    assert (
        definition_of_done_findings(
            item=_item(description=description), cwd=_spec_tree(tmp_path=tmp_path)
        )
        == ()
    )


def test_a_reasonless_sub_heading_closed_by_another_heading_is_still_a_finding(
    tmp_path: Path,
) -> None:
    # The sub-heading ends at the NEXT heading rather than at the end of the
    # section, so the missing `Reason:` line has to be caught on that boundary
    # too — otherwise an author could silence the finding by adding any heading
    # after the opt-out, which is the cheapest possible evasion of it.
    description = (
        "## Definition of Done\n"
        "\n"
        "### Human-attested\n"
        "\n"
        "- A human attests this one.\n"
        "\n"
        "### Host walls\n"
        "\n"
        "- The factory captures this one.\n"
        "\n"
        f"References: {_PLAIN_HEADING}\n"
    )

    findings = definition_of_done_findings(
        item=_item(description=description), cwd=_spec_tree(tmp_path=tmp_path)
    )

    assert len(findings) == 1
    assert "Human-attested" in findings[0]
    assert "Reason:" in findings[0]


def test_a_human_attested_sub_heading_with_a_reason_line_is_no_finding(
    tmp_path: Path,
) -> None:
    description = (
        "## Definition of Done\n"
        "\n"
        "### Human-attested\n"
        "\n"
        "Reason: the proof needs a session on an external administrative console.\n"
        "\n"
        "- A human attests this one.\n"
        "\n"
        f"References: {_PLAIN_HEADING}\n"
    )

    assert (
        definition_of_done_findings(
            item=_item(description=description), cwd=_spec_tree(tmp_path=tmp_path)
        )
        == ()
    )


def test_a_fixture_with_no_spec_tree_keeps_the_parse_checks(tmp_path: Path) -> None:
    # The stand-in resolves every reference for a directory that never built a
    # spec tree, so the parse checks (section present, reference line present)
    # are the only findings left standing.
    item = _item(description=_description(references="## Scenario 999 — No such heading"))

    assert definition_of_done_findings(item=item, cwd=tmp_path) == ()
    assert definition_of_done_findings(item=_item(), cwd=tmp_path) != ()
