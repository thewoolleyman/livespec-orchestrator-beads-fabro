"""Rendered-length accounting for a specification tree prompt."""

from __future__ import annotations

from collections.abc import Mapping

__all__: list[str] = ["rendered_tree_length"]


def rendered_tree_length(*, tree: Mapping[str, str]) -> int:
    """Return the upstream renderer's character count for `tree`."""
    if not tree:
        return 0
    blocks = [len("--- ") + len(path) + len(" ---\n") + len(tree[path]) for path in tree]
    return sum(blocks) + len("\n\n") * (len(blocks) - 1)
