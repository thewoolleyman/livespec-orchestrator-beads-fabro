"""Prior janitor evidence that constrains an explicit reconcile PR selection."""

from __future__ import annotations

from typing import cast

__all__: list[str] = ["selected_pr_janitor_evidence_refusal"]


def selected_pr_janitor_evidence_refusal(
    *,
    item_id: str,
    selected_pr: int | None,
    selected_pr_number: int,
    records: tuple[dict[str, object], ...],
) -> str | None:
    """Refuse a selected PR that differs from the parked item's green janitor evidence."""
    if selected_pr is None:
        return None
    for record in reversed(records):
        raw_outcome = record.get("outcome")
        if not isinstance(raw_outcome, dict):
            continue
        outcome = cast("dict[str, object]", raw_outcome)
        if outcome.get("work_item_id") != item_id:
            continue
        if (
            outcome.get("status") != "green"
            or outcome.get("stage") != "done"
            or outcome.get("detail") != "merged, post-merge janitor green"
        ):
            continue
        evidence_pr = outcome.get("pr_number")
        evidence_sha = outcome.get("merge_sha")
        if (
            not isinstance(evidence_pr, int)
            or isinstance(evidence_pr, bool)
            or not isinstance(evidence_sha, str)
            or evidence_pr == selected_pr_number
        ):
            continue
        return (
            f"ERROR: reconcile-merged --pr refused before acceptance: selected merged PR "
            f"#{selected_pr_number} conflicts with journaled green post-merge janitor evidence "
            f"for PR #{evidence_pr} ({evidence_sha}) on work-item {item_id}; its status "
            f"remains acceptance.\n"
        )
    return None
