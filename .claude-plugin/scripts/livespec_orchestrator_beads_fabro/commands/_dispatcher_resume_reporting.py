"""Operator-facing rendering for resume refusals."""

from __future__ import annotations

from collections.abc import Sequence

__all__: list[str] = [
    "resume_refusal_report",
]


def resume_refusal_report(*, work_item_id: str, refusals: Sequence[str]) -> str:
    """Render every applicable resume refusal in the clause's order."""
    lines = "".join(f"  - {refusal}\n" for refusal in refusals)
    return f"ERROR: resume refused for {work_item_id}:\n{lines}"
