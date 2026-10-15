"""Tests for the pure core of the host-side Definition-of-Done judgement.

The "Judged before admission" and "Judged again before dispatch" paragraphs of
`SPECIFICATION/contracts.md` name two inputs the judgement is handed — "its
effective criteria and referenced specification headings" — and state the reuse
rule in BYTES: a recorded verdict is reused "while the item's effective criteria
and referenced headings are byte-unchanged since that verdict was taken". These
tests pin that the subject carries both inputs and that the digest moves when
either one does.

THE UNPARSEABLE-REPLY CASES ARE THE LOAD-BEARING ONES. The clause groups "no
eligible model, a timeout, or an unparseable verdict" as the conditions under
which the judgement CANNOT RUN, and every one of them must route the item as it
would be routed without the judgement. Reading an unreadable reply as a pass
reaches the same routing while asserting something false, and nothing downstream
re-tests it — so a reply with no JSON, a non-object JSON, an unknown outcome and
a `failed` object naming nothing are each asserted to report `did-not-run`
rather than `admitted`.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement import (
    CAUSE_UNPARSEABLE_VERDICT,
    JUDGEMENT_ADMITTED,
    JUDGEMENT_HELD,
    JUDGEMENT_UNAVAILABLE,
    first_remedy,
    judgement_subject,
    judgement_subject_digest,
    parse_judgement_reply,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

_SCENARIO_HEADING = "## Scenario 174 — The judgement runs before admission"
_CONTRACT_HEADING = "## Effective acceptance criteria"
_SCENARIO_BODY = "The pre-admission judgement runs against the effective criteria."


def _item(**overrides: object) -> WorkItem:
    base = WorkItem(
        id="bd-ib-7f66ar",
        type="feature",
        status="pending-approval",
        title="Judge the Definition of Done before admission",
        description=_description(references=_SCENARIO_HEADING),
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee=None,
        depends_on=(),
        captured_at="2026-10-15T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="auto",
        acceptance_policy="ai-only",
    )
    return replace(base, **overrides)


def _description(*, references: str) -> str:
    return (
        "## Definition of Done\n"
        "\n"
        "- The judgement runs before the item is routed to ready.\n"
        "\n"
        f"References: {references}\n"
    )


def _spec_tree(*, tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    spec = repo / "SPECIFICATION"
    spec.mkdir(parents=True)
    _ = (spec / "contracts.md").write_text(
        f"# Contracts\n\nPreamble prose.\n\n{_CONTRACT_HEADING}\n\nCriteria prose.\n",
        encoding="utf-8",
    )
    _ = (spec / "scenarios.md").write_text(
        f"# Scenarios\n\n{_SCENARIO_HEADING}\n\n{_SCENARIO_BODY}\n\n## Scenario 175 — Other\n\nNo.\n",
        encoding="utf-8",
    )
    return repo


def test_the_subject_carries_the_effective_criteria_and_each_referenced_heading_body(
    tmp_path: Path,
) -> None:
    subject = judgement_subject(item=_item(), cwd=_spec_tree(tmp_path=tmp_path))

    assert "bd-ib-7f66ar" in subject
    assert "The judgement runs before the item is routed to ready." in subject
    # The referenced heading's OWN body, which is what the assertion is judged
    # against — not merely the heading text echoed back off the reference line.
    assert _SCENARIO_BODY in subject
    # The next H2 bounds the section, so a neighbouring scenario's body is out.
    assert "No." not in subject


def test_a_bare_reference_form_resolves_the_same_heading_as_the_marked_form(
    tmp_path: Path,
) -> None:
    repo = _spec_tree(tmp_path=tmp_path)
    bare = _item(description=_description(references="Effective acceptance criteria"))
    marked = _item(description=_description(references=_CONTRACT_HEADING))

    assert "Criteria prose." in judgement_subject(item=bare, cwd=repo)
    assert "Criteria prose." in judgement_subject(item=marked, cwd=repo)


def test_a_reference_that_resolves_to_nothing_is_rendered_as_a_stated_absence(
    tmp_path: Path,
) -> None:
    repo = _spec_tree(tmp_path=tmp_path)
    # A directory named like a spec file is unreadable, exercising the per-file
    # fail-soft without blinding the whole read.
    (repo / "SPECIFICATION" / "unreadable.md").mkdir()
    unresolved = _item(description=_description(references="## No such heading"))

    subject = judgement_subject(item=unresolved, cwd=repo)

    assert "## No such heading" in subject
    assert "does not resolve" in subject


def test_a_repository_with_no_spec_tree_renders_every_reference_as_unresolved(
    tmp_path: Path,
) -> None:
    subject = judgement_subject(item=_item(), cwd=tmp_path)

    assert "does not resolve" in subject


def test_an_item_with_no_criteria_and_no_references_renders_a_stated_absence(
    tmp_path: Path,
) -> None:
    subject = judgement_subject(
        item=_item(description="No section here at all."), cwd=_spec_tree(tmp_path=tmp_path)
    )

    assert "no effective acceptance criteria" in subject
    assert "Referenced heading" not in subject


def test_the_digest_moves_when_the_criteria_change_and_when_a_heading_body_changes(
    tmp_path: Path,
) -> None:
    repo = _spec_tree(tmp_path=tmp_path)
    item = _item()
    baseline = judgement_subject_digest(item=item, cwd=repo)

    assert judgement_subject_digest(item=item, cwd=repo) == baseline
    edited_criteria = _item(
        description=_description(references=_SCENARIO_HEADING).replace("ready", "ready now")
    )
    assert judgement_subject_digest(item=edited_criteria, cwd=repo) != baseline
    _ = (repo / "SPECIFICATION" / "scenarios.md").write_text(
        f"# Scenarios\n\n{_SCENARIO_HEADING}\n\nAmended prose.\n", encoding="utf-8"
    )
    assert judgement_subject_digest(item=item, cwd=repo) != baseline


def test_a_passing_verdict_object_reads_as_admitted() -> None:
    reply = 'I read every assertion.\n{"outcome": "passed"}\n'

    assert parse_judgement_reply(reply=reply).outcome == JUDGEMENT_ADMITTED


def test_a_failing_verdict_object_reads_as_held_with_one_finding_per_line() -> None:
    reason = "bd-ib-1: the References line omits the scenario; add it.\nbd-ib-1: second fault; fix."
    reply = f"Findings follow.\n{json.dumps({'outcome': 'failed', 'failure_reason': reason})}"

    verdict = parse_judgement_reply(reply=reply)

    assert verdict.outcome == JUDGEMENT_HELD
    assert verdict.holds
    assert len(verdict.findings) == 2
    assert verdict.finding_text.splitlines()[0].endswith("add it.")


def test_every_unreadable_reply_shape_reports_did_not_run_rather_than_a_pass() -> None:
    for reply in (
        "",
        "   \n  \n",
        "no json here at all",
        "[1, 2, 3]",
        '{"outcome": "something-else"}',
        '{"outcome": "failed"}',
        '{"outcome": "failed", "failure_reason": "   "}',
        '{"outcome": "failed", "failure_reason": 17}',
    ):
        verdict = parse_judgement_reply(reply=reply)

        assert verdict.outcome == JUDGEMENT_UNAVAILABLE, reply
        assert verdict.cause == CAUSE_UNPARSEABLE_VERDICT, reply
        assert not verdict.holds, reply


def test_the_first_remedy_is_the_clause_after_the_last_separator_of_the_first_finding() -> None:
    assert first_remedy(findings=()) is None
    assert (
        first_remedy(findings=("bd-ib-1: the line omits the scenario; add that heading.",))
        == "add that heading."
    )
    # A finding carrying no separator is returned whole: a hygiene fact naming
    # nothing is a row nobody can act on.
    assert (
        first_remedy(findings=("bd-ib-1: repair the section.",)) == "bd-ib-1: repair the section."
    )
