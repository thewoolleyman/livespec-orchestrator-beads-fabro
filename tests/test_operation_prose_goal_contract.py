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
