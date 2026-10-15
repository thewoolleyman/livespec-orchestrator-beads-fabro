"""The changed files a factory server still holds for one run."""

from __future__ import annotations

from dataclasses import dataclass

__all__: list[str] = ["RunFile"]


@dataclass(frozen=True, kw_only=True)
class RunFile:
    """One file a run changed, as the factory reports it.

    `content` is `None` for a REMOVAL, which is a different fact from empty
    content: a run that truncated a file reports zero bytes, and a run that
    deleted it reports none at all.
    """

    path: str
    content: bytes | None
    mode: str
