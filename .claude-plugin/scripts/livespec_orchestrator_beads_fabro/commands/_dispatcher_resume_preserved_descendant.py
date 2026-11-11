"""The refusal text for a preservation that contains unpublished work."""

from __future__ import annotations

__all__: list[str] = ["descending_preservation_refusal"]


def descending_preservation_refusal(
    *, preservation_ref: str, preservation_tip: str, published_head: str
) -> str:
    """Name the preserved descendant a resume would otherwise discard."""
    return (
        f"preserved ref {preservation_ref} at {preservation_tip} descends from the"
        f" published head {published_head} with a different tree, so a resume would"
        " discard preserved work; dispatch it plainly instead"
    )
