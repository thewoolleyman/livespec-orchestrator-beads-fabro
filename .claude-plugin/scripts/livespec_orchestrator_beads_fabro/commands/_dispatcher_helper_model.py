"""The value object each Dispatcher-materialized helper registry entry carries."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

__all__: list[str] = ["Helper"]


@dataclass(frozen=True, kw_only=True)
class Helper:
    """One helper program: its name, where it lands, its mode, and what composes its bytes."""

    name: str
    root: str
    path: str
    mode: int
    compose: Callable[[], bytes]
