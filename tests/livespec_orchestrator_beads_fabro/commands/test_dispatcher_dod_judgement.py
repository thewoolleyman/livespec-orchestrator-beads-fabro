"""Definition-of-Done judgement core contract."""

from __future__ import annotations

import importlib
from dataclasses import replace
from pathlib import Path

from livespec_orchestrator_beads_fabro.store import WorkItemComment
from livespec_orchestrator_beads_fabro.types import WorkItem


def _item() -> WorkItem:
    return WorkItem(
        id="bd-ib-7f66ar",
        type="feature",
        status="ready",
        title="Judge the Definition of Done before dispatch",
        description=(
            "## Definition of Done\n\n"
            "- The judgement runs before an item moves to ready.\n\n"
            "References: ## Scenario 174 — The judgement runs before admission\n"
        ),
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee=None,
        depends_on=(),
        captured_at="2026-10-20T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="auto",
        acceptance_policy="ai-only",
    )


def test_judgement_subject_and_verdict_cover_effective_criteria_and_referenced_headings(
    tmp_path: Path,
) -> None:
    module_path = (
        Path(__file__).parents[3]
        / ".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands"
        / "_dispatcher_dod_judgement.py"
    )
    assert module_path.is_file()
    judgement = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement"
    )
    spec = tmp_path / "SPECIFICATION"
    spec.mkdir()
    _ = (spec / "scenarios.md").write_text(
        "## Scenario 174 — The judgement runs before admission\n\n"
        "The referenced requirement governs the assertion.\n\n"
        "## Scenario 175 — Other\n\n"
        "Unrelated text.\n",
        encoding="utf-8",
    )

    subject = judgement.judgement_subject(item=_item(), cwd=tmp_path)

    assert "The judgement runs before an item moves to ready." in subject
    assert "The referenced requirement governs the assertion." in subject
    assert "Unrelated text." not in subject
    held = judgement.parse_judgement_reply(
        reply='{"outcome": "failed", "failure_reason": "missing heading; add it."}'
    )
    assert held.holds
    assert held.findings == ("missing heading; add it.",)
    assert judgement.parse_judgement_reply(reply="not a verdict").outcome == "did-not-run"
    assert judgement.judgement_subject_digest(item=_item(), cwd=tmp_path) != (
        judgement.judgement_subject_digest(
            item=replace(
                _item(),
                description=_item().description.replace("moves to ready", "moves to ready now"),
            ),
            cwd=tmp_path,
        )
    )


def test_judgement_records_every_unreadable_reply_as_did_not_run() -> None:
    judgement = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement"
    )

    for reply in (
        "",
        "   \n",
        "not json",
        "[]",
        '{"outcome": "unknown"}',
        '{"outcome": "failed"}',
        '{"outcome": "failed", "failure_reason": " "}',
        '{"outcome": "failed", "failure_reason": 7}',
    ):
        verdict = judgement.parse_judgement_reply(reply=reply)

        assert verdict.outcome == "did-not-run"
        assert verdict.cause == "unparseable-verdict"
        assert not verdict.holds


def test_judgement_admission_and_remedies_keep_each_finding_actionable() -> None:
    judgement = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement"
    )

    admitted = judgement.parse_judgement_reply(reply='{"outcome": "passed"}\n')

    assert admitted.outcome == "admitted"
    assert not admitted.holds
    assert admitted.finding_text == ""
    assert judgement.first_remedy(findings=()) is None
    judgment_remedy = judgement.first_remedy(
        findings=("item: missing reference; add Scenario 174.",)
    )
    assert judgment_remedy is not None
    assert judgment_remedy == "add Scenario 174."
    assert judgment_remedy != judgement.first_remedy(findings=("repair the item.",))


def test_unresolved_and_unreadable_spec_references_stay_distinct_from_no_reference(
    tmp_path: Path,
) -> None:
    judgement = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement"
    )
    absent = judgement.judgement_subject(item=_item(), cwd=tmp_path)
    spec = tmp_path / "SPECIFICATION"
    spec.mkdir()
    (spec / "unreadable.md").mkdir()
    unresolved = judgement.judgement_subject(
        item=replace(
            _item(),
            description=(
                "## Definition of Done\n\n"
                "- A reference can be missing.\n\n"
                "References: Missing heading\n"
            ),
        ),
        cwd=tmp_path,
    )
    no_reference = judgement.judgement_subject(
        item=replace(_item(), description="No Definition of Done section."), cwd=tmp_path
    )

    assert "does not resolve" in absent
    assert "Missing heading" in unresolved
    assert "does not resolve" in unresolved
    assert "Referenced heading" not in no_reference


def test_heading_lookup_skips_irrelevant_sections_and_ends_at_the_next_heading(
    tmp_path: Path,
) -> None:
    judgement = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement"
    )
    spec = tmp_path / "SPECIFICATION"
    spec.mkdir()
    _ = (spec / "aaa-empty.md").write_text("", encoding="utf-8")
    _ = (spec / "contracts.md").write_text(
        "# Preamble\n\n"
        "## Other\n\n"
        "Other body.\n\n"
        "## Target\n\n"
        "Target body.\n\n"
        "## Following\n\n"
        "Following body.\n",
        encoding="utf-8",
    )
    item = replace(
        _item(),
        description=(
            "## Definition of Done\n\n" "- Targeted reference.\n\n" "References: Target\n"
        ),
    )

    subject = judgement.judgement_subject(item=item, cwd=tmp_path)

    assert "Target body." in subject
    assert "Following body." not in subject


def test_subject_carries_the_goal_fields_the_rubric_grades(tmp_path: Path) -> None:
    """The rubric's check 1 reads the DESCRIPTION's first heading (bd-ib-kt4mgw).

    A subject that showed only the effective-criteria projection left a judge
    nothing to read for that check, so a strict one refused every valid section.
    """
    judgement = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement"
    )
    goal = importlib.import_module("livespec_orchestrator_beads_fabro.commands._dispatcher_goal")
    lessons_file = tmp_path / "loop-reflection-gate" / "lessons.md"
    lessons_file.parent.mkdir()
    _ = lessons_file.write_text(
        "# Lessons\n\n## Lessons\n\nPrefer one rendering of a shared brief.\n",
        encoding="utf-8",
    )
    item = replace(
        _item(),
        acceptance_criteria="- A native criterion travels with the item.",
        notes="A note the operator left on the item.",
    )
    rider = "Rider: narrow the first assertion to the admission wall."
    record = "livespec-dod-judgement-unavailable\n\nThe judgement did not run."

    subject = judgement.judgement_subject(item=item, cwd=tmp_path, comments=(rider, record))
    rendered = goal.render_goal(
        item=item,
        repo=tmp_path,
        branch="feat/bd-ib-7f66ar",
        comments=tuple(
            WorkItemComment(text=text, author=None, created_at=None) for text in (rider, record)
        ),
        lessons="Prefer one rendering of a shared brief.",
    )

    assert item.description in subject
    first_heading = next(line for line in subject.splitlines() if line.startswith("## "))
    assert first_heading == "## Definition of Done"
    assert subject.index(item.description) < subject.index("## Effective acceptance criteria")
    for field in (
        item.description,
        "- A native criterion travels with the item.",
        "A note the operator left on the item.",
        "Prefer one rendering of a shared brief.",
        rider,
    ):
        assert field in subject
        assert field in rendered
    assert "livespec-dod-judgement-unavailable" not in subject
    assert "livespec-dod-judgement-unavailable" not in rendered
    assert "feat/bd-ib-7f66ar" not in subject
    assert judgement.judgement_subject(item=item, cwd=tmp_path, comments=(rider,)) == subject


def test_the_ratified_spec_identity_moves_with_the_tree_and_names_an_unreadable_one(
    tmp_path: Path,
) -> None:
    """The half of the reuse digest an item's own text cannot see.

    Since `bd-ib-m76p2n` the governing-heading verdict is a reading of the WHOLE
    ratified tree, so a scenario the item cites NOWHERE can become the clause
    that governs it. The subject carries only the bodies of the headings the
    reference line names, so the tree's own identity is what retires a verdict
    across that change.

    The unreadable arm answers a SELF-DESCRIBING word rather than the digest of
    nothing, because an empty digest reads as a tree that exists and is empty —
    which would make every unreadable reading agree with every other one and
    reuse a verdict across a change nobody could see. It is reached with a
    DIRECTORY named like a spec file rather than by clearing mode bits: this
    suite runs as root, which bypasses them, so a `chmod` fixture reads
    successfully and the case passes against an implementation with no
    read-failure arm at all.
    """
    module_path = (
        Path(__file__).parents[3]
        / ".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands"
        / "_dispatcher_dod_judgement.py"
    )
    assert module_path.is_file()
    judgement = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement"
    )
    spec = tmp_path / "SPECIFICATION"
    spec.mkdir()
    scenarios = spec / "scenarios.md"
    _ = scenarios.write_text("## Scenario 1 — One\n\nBody.\n", encoding="utf-8")

    before = judgement.spec_tree_identity(cwd=tmp_path)
    _ = scenarios.write_text(
        "## Scenario 1 — One\n\nBody.\n\n## Scenario 2 — Two\n\nAdded.\n", encoding="utf-8"
    )
    after = judgement.spec_tree_identity(cwd=tmp_path)

    assert before != after
    assert judgement.spec_tree_identity(cwd=tmp_path / "absent") == "unreadable"

    (spec / "unreadable.md").mkdir()

    assert judgement.spec_tree_identity(cwd=tmp_path) == "unreadable"
