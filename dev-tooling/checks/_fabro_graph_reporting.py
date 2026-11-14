"""Formatting helpers for factory-graph gate findings and warnings."""

from __future__ import annotations

from _checked_workflow_payloads import CheckedPayload

__all__: list[str] = [
    "absence_records",
    "finding_kind",
]


def absence_records(
    *, graph_name: str, lever: str, fail_when_absent: str, payloads: list[CheckedPayload]
) -> list[str]:
    """Name each graph that could not be checked because no client resolved."""
    records = [
        f"{payload.where}: {graph_name} was NOT validated — no `fabro` binary resolved"
        for payload in payloads
    ]
    lead = "NO factory graph was validated in this environment: `fabro` did not resolve"
    said = "nothing here says the graphs are good — only that they were not looked at"
    remedy = f"Set {lever}={fail_when_absent} wherever the binary is expected"
    records.append(f"{lead}, so {said}. {remedy}")
    return records


def finding_kind(*, finding: str) -> str:
    """Whether a finding is about the instrument or about a graph."""
    return "control" if "control:" in finding else "graph"
