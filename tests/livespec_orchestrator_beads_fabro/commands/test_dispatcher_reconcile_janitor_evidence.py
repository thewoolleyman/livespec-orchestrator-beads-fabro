"""Tests for explicit reconcile PR selections against prior janitor evidence."""

from __future__ import annotations

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_janitor_evidence import (
    selected_pr_janitor_evidence_refusal,
)


def _green(*, pr_number: object = 81, merge_sha: object = "janitor81") -> dict[str, object]:
    return {
        "stage": "outcome",
        "outcome": {
            "work_item_id": "bd-ib-ranking",
            "status": "green",
            "stage": "done",
            "detail": "merged, post-merge janitor green",
            "pr_number": pr_number,
            "merge_sha": merge_sha,
        },
    }


@pytest.mark.parametrize(
    ("selected_pr", "selected_pr_number", "records"),
    [
        (None, 82, (_green(),)),
        (82, 81, (_green(),)),
        (82, 82, ({"outcome": "malformed"}, _green(pr_number=True), _green(merge_sha=2))),
        (82, 82, ({"outcome": {"work_item_id": "other"}},)),
        (82, 82, ({"outcome": {**_green()["outcome"], "status": "red"}},)),
    ],
)
def test_no_refusal_without_distinct_well_formed_green_janitor_evidence(
    selected_pr: int | None, selected_pr_number: int, records: tuple[dict[str, object], ...]
) -> None:
    assert (
        selected_pr_janitor_evidence_refusal(
            item_id="bd-ib-ranking",
            selected_pr=selected_pr,
            selected_pr_number=selected_pr_number,
            records=records,
        )
        is None
    )


def test_refusal_names_the_selected_and_journaled_prs() -> None:
    refusal = selected_pr_janitor_evidence_refusal(
        item_id="bd-ib-ranking", selected_pr=82, selected_pr_number=82, records=(_green(),)
    )

    assert refusal is not None
    assert "#82" in refusal
    assert "#81" in refusal
