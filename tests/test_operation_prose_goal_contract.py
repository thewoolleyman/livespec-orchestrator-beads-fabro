"""Outcome-first contract tests for the seven operation prose files."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROSE = ROOT / ".claude-plugin" / "prose"


def _read(name: str) -> str:
    return (PROSE / name).read_text(encoding="utf-8")


def test_plan_opens_with_the_archive_goal_and_stop_contract() -> None:
    text = _read("plan.md")
    goal = text.index("## Goal")
    flow = text.index("## Flow")
    prerequisites = text.index("## Pre-requisites")

    assert goal < flow < prerequisites
    opening = text[goal:flow].lower()
    required = (
        "successful archive",
        "child disposition",
        "current independent completeness-review evidence",
        "verified` plan proof of done",
        "released artifact where a release applies",
        "required human attestations",
        "### continue",
        "re-read current state",
        "recorded eligible next action",
        "continuation is authorized",
        "store-write consent",
        "### suspend",
        "recorded human gate",
        "bounded wait",
        "run",
        "deadline",
        "supervising mechanism",
        "### fail",
        "unresolved input, refusal, or outage",
        "incomplete work",
        "human decision",
    )
    assert all(phrase in opening for phrase in required)


def test_plan_picker_defaults_to_the_typed_action_under_standing_direction() -> None:
    text = _read("plan.md")
    resume = text[text.index("#### Unattended resume") : text.index("### Step 4")]

    assert "presents the epic's `next_action` as the default choice" in resume
    assert "standing maintainer directive to continue satisfies that picker" in resume
    assert "take the default without re-prompting" in resume
    assert "Store-write consent remains governed by the consent contract" in resume


def test_plan_handoff_is_not_progress_and_exit_is_audited() -> None:
    text = _read("plan.md")
    handoff = text[text.index("### Step 4") : text.index("### Step 5")]

    assert "Recording a handoff does not complete an executable next action" in handoff
    assert "Before ending" in handoff
    assert "successful archive" in handoff
    assert "specific unresolved input or refusal" in handoff
    assert "run and verified continuation mechanism" in handoff
    assert "report the work as incomplete" in handoff


def test_plan_flow_precedes_a_compact_reference_and_mutation_check() -> None:
    text = _read("plan.md")
    lines = text.splitlines()
    flow = text.index("## Flow")
    reference = text.index("## Reference")
    prerequisites = text.index("### Pre-requisites")
    store = text.index("### The Plan Store")
    commands = text.index("### Package Commands")
    first_mutation = text.index("On confirmation, create exactly these records")
    prerequisite_check = text.index("Before the first mutation, verify")

    assert flow < reference < prerequisites < store < commands
    assert prerequisite_check < first_mutation
    assert len(lines) <= 450
