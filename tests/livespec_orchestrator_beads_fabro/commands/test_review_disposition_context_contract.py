"""Review-to-disposition context contract for the implement workflow prompts."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands import dispatcher

_PLUGIN_ROOT = Path(dispatcher.__file__).resolve().parents[3]
_PROMPTS_DIR = _PLUGIN_ROOT / ".fabro" / "workflows" / "implement-work-item" / "prompts"
_ROUND_KEY = re.compile(r"^review_findings_r(?P<round>[1-9][0-9]*)$")
_DISPOSITION_KEY = re.compile(r"^finding_dispositions_r(?P<round>[1-9][0-9]*)$")


class _MissingReviewFindingsError(ValueError):
    """The disposition stage has no current-round review findings context."""


class _MalformedReviewFindingsError(ValueError):
    """The disposition stage has review findings context that cannot be routed."""


def _prompt_text(*, name: str) -> str:
    return (_PROMPTS_DIR / name).read_text(encoding="utf-8")


def _round_numbers(*, context: dict[str, str], pattern: re.Pattern[str]) -> list[int]:
    rounds: list[int] = []
    for key in context:
        match = pattern.match(key)
        if match is not None:
            rounds.append(int(match.group("round")))
    return sorted(rounds)


def _current_review_findings(*, context: dict[str, str]) -> tuple[str, str]:
    review_rounds = _round_numbers(context=context, pattern=_ROUND_KEY)
    disposition_rounds = _round_numbers(context=context, pattern=_DISPOSITION_KEY)
    expected_round = max(disposition_rounds, default=0) + 1
    expected_key = f"review_findings_r{expected_round}"
    if expected_key not in context:
        raise _MissingReviewFindingsError(
            f"missing {expected_key} from the review stage context_updates"
        )
    if review_rounds[-1] != expected_round:
        raise _MissingReviewFindingsError(
            f"missing current review stage key {expected_key}; "
            f"highest visible review key is review_findings_r{review_rounds[-1]}"
        )
    findings = context[expected_key]
    if "[BLOCKING]" not in findings:
        raise _MalformedReviewFindingsError(
            f"malformed {expected_key}: review stage findings contain no [BLOCKING] line"
        )
    return expected_key, findings


def test_review_prompt_publishes_blocking_findings_under_round_indexed_context() -> None:
    text = _prompt_text(name="review.md")

    assert "context_updates" in text
    assert "review_findings_r<N>" in text
    assert "count prior visible `review_findings_r*`" in text
    assert "LAST `## Context` block of the preamble" in text
    assert "immediately before the stage prompt" in text
    assert "one `- <key>: <value>` line per key" in text
    assert "the exact finding lines" in text
    assert '{"preferred_next_label": "fix"' in text


def test_disposition_prompt_reads_current_review_findings_key_and_fails_closed() -> None:
    text = _prompt_text(name="disposition.md")

    assert "review_findings_r<N>" in text
    assert "highest-numbered" in text
    assert "current round" in text
    assert "review stage" in text
    assert "LAST `## Context` block of the preamble" in text
    assert "immediately before the stage prompt" in text
    assert "one `- <key>: <value>` line per key" in text
    assert "search your own prompt for the literal key `review_findings_r<N>:`" in text
    assert "missing `review_findings_r<N>`" in text
    assert '"outcome": "failed"' in text


def test_one_review_round_exposes_blocking_findings_to_disposition() -> None:
    key, findings = _current_review_findings(
        context={
            "review_findings_r1": "[BLOCKING] src/app.py:10 - first-round defect",
        },
    )

    assert key == "review_findings_r1"
    assert "first-round defect" in findings


def test_second_review_round_uses_latest_findings_after_review_fix() -> None:
    key, findings = _current_review_findings(
        context={
            "review_findings_r1": "[BLOCKING] src/app.py:10 - stale defect",
            "finding_dispositions_r1": "ACCEPTED src/app.py:10 - fix it",
            "review_findings_r2": "[BLOCKING] src/app.py:20 - round-two defect",
        },
    )

    assert key == "review_findings_r2"
    assert "round-two defect" in findings
    assert "stale defect" not in findings


def test_multiple_review_rounds_preserve_blocking_and_advisory_findings() -> None:
    key, findings = _current_review_findings(
        context={
            "review_findings_r1": "[BLOCKING] a.py:1 - first",
            "finding_dispositions_r1": "ACCEPTED a.py:1 - fix it",
            "review_findings_r2": "[BLOCKING] b.py:2 - second",
            "finding_dispositions_r2": "ACCEPTED b.py:2 - fix it",
            "review_findings_r3": (
                "[BLOCKING] c.py:3 - third\n" "[ADVISORY] c.py:4 - keep this non-gating note"
            ),
        },
    )

    assert key == "review_findings_r3"
    assert "[BLOCKING] c.py:3" in findings
    assert "[ADVISORY] c.py:4" in findings


def test_missing_current_round_findings_key_fails_closed_with_named_key() -> None:
    with pytest.raises(_MissingReviewFindingsError, match="review_findings_r2"):
        _current_review_findings(
            context={
                "review_findings_r1": "[BLOCKING] a.py:1 - first",
                "finding_dispositions_r1": "ACCEPTED a.py:1 - fix it",
            },
        )


def test_later_review_key_without_matching_disposition_fails_closed() -> None:
    with pytest.raises(_MissingReviewFindingsError, match="review_findings_r2"):
        _current_review_findings(
            context={
                "review_findings_r1": "[BLOCKING] a.py:1 - first",
                "finding_dispositions_r1": "ACCEPTED a.py:1 - fix it",
                "review_findings_r2": "[BLOCKING] b.py:2 - second",
                "review_findings_r3": "[BLOCKING] c.py:3 - unpaired later review",
            },
        )


def test_malformed_current_round_findings_fail_closed_with_named_key() -> None:
    with pytest.raises(_MalformedReviewFindingsError, match="review_findings_r2"):
        _current_review_findings(
            context={
                "review_findings_r1": "[BLOCKING] a.py:1 - first",
                "finding_dispositions_r1": "ACCEPTED a.py:1 - fix it",
                "review_findings_r2": "review completed but no machine-readable finding lines",
            },
        )
