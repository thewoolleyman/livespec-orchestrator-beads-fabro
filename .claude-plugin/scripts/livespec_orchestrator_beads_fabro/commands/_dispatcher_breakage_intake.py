"""Ledger intake shaping and deduplication for scheduled-workflow breakage."""

from __future__ import annotations

from typing import cast

from livespec_runtime.work_items.rank import key_between

from livespec_orchestrator_beads_fabro.commands._dispatcher_breakage_forge import (
    FailedJob,
    ScheduledRun,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_goal import minijinja_openers_in_text
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = ["build_breakage_item", "known_breakage_keys", "template_refusal"]


def known_breakage_keys(*, records: list[dict[str, object]]) -> dict[str, str]:
    """Return every persisted breakage key, including keys on closed work items."""
    known: dict[str, str] = {}
    for record in records:
        metadata = record.get("metadata")
        identifier = record.get("id")
        if not isinstance(metadata, dict) or not isinstance(identifier, str):
            continue
        key = cast("dict[str, object]", metadata).get("breakage_key")
        if isinstance(key, str):
            known[key] = identifier
    return known


def build_breakage_item(
    *,
    item_id: str,
    workflow: str,
    job: FailedJob,
    run: ScheduledRun,
    tests: tuple[str, ...],
    captured_at: str,
) -> WorkItem:
    """Build the intake-compatible work item for one failed scheduled job."""
    evidence = (
        "\n".join(f"- {test}" for test in tests)
        if tests
        else (f"No failing test named; failing step: {job.failing_step}")
    )
    return WorkItem(
        id=item_id,
        type="bug",
        status="backlog",
        title=f"CI breakage: {workflow} — {job.name}",
        description=(
            f"Scheduled workflow failure for `{workflow}` job `{job.name}`.\n\n"
            f"Run URL: {run.url}\nHead commit: {run.head_sha}\n{evidence}\n\n"
            "## Definition of Done\n\n"
            "References: ## Scheduled-workflow breakage pass\n\n"
            f"- The failing `{workflow}` job `{job.name}` is investigated and its failure is "
            "resolved.\n"
        ),
        origin="freeform",
        gap_id=None,
        rank=key_between(a=None, b=None),
        assignee=None,
        depends_on=(),
        captured_at=captured_at,
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        spec_commitment_hint=None,
        admission_policy="auto",
    )


def template_refusal(*, description: str) -> str | None:
    """Reject description text that the shared template-opener detector finds unsafe."""
    findings = minijinja_openers_in_text(source="breakage-pass", text=description)
    if not findings:
        return None
    return f"template opener present: {', '.join(finding.opener for finding in findings)}"
