"""Tests for pure spec-next candidate adaptation."""

import json
import shlex

import pytest
from livespec_orchestrator_beads_fabro.commands._needs_attention_spec_next_adapt import (
    adapt_top_candidate,
    candidate_urgency,
    spec_output_from_candidate,
)


@pytest.mark.parametrize(
    ("value", "expected"),
    [("high", "high"), ("low", "low"), ("medium", "medium"), ("bogus", "medium"), (None, "medium")],
)
def test_candidate_urgency(value: object, expected: str) -> None:
    assert candidate_urgency(value=value) == expected


def test_spec_output_from_candidate_non_dict_returns_none(tmp_path) -> None:
    assert spec_output_from_candidate(candidate="x", project_root=tmp_path) is None


def test_spec_output_from_candidate_missing_action_returns_none(tmp_path) -> None:
    assert spec_output_from_candidate(candidate={"reason": "r"}, project_root=tmp_path) is None


def test_spec_output_from_candidate_defaults_summary_and_target(tmp_path) -> None:
    output = spec_output_from_candidate(candidate={"action": "critique"}, project_root=tmp_path)
    assert output is not None
    assert output.summary == "Spec-side critique is ready."
    assert output.spec_target == "SPECIFICATION"
    assert output.urgency == "medium"
    assert output.command == (
        f"codex exec livespec:critique --project-root {shlex.quote(str(tmp_path))}"
    )


def test_spec_output_from_candidate_empty_reason_and_target_default(tmp_path) -> None:
    output = spec_output_from_candidate(
        candidate={"action": "revise", "reason": "", "target": ""}, project_root=tmp_path
    )
    assert output is not None
    assert output.summary == "Spec-side revise is ready."
    assert output.spec_target == "SPECIFICATION"


def test_adapt_top_candidate_non_object_payload_returns_none(tmp_path) -> None:
    assert adapt_top_candidate(stdout='"a string"', project_root=tmp_path) is None


def test_adapt_top_candidate_candidates_not_list_returns_none(tmp_path) -> None:
    assert adapt_top_candidate(stdout='{"candidates": {}}', project_root=tmp_path) is None


def test_adapt_top_candidate_skips_inert_then_selects_actionable(tmp_path) -> None:
    stdout = json.dumps(
        {
            "candidates": [
                "not-a-dict",
                {"action": "none", "reason": "nothing"},
                {"action": "propose-change", "reason": "gap found", "urgency": "medium"},
            ]
        }
    )
    output = adapt_top_candidate(stdout=stdout, project_root=tmp_path)
    assert output is not None
    assert output.op == "propose-change"
