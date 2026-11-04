"""Whether a dispatcher configuration declares factories by name."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from livespec_orchestrator_beads_fabro.commands._config import dispatcher_block

__all__: list[str] = ["has_fabro_factories", "has_fabro_factory"]


def has_fabro_factory(*, cwd: Path, factory: str) -> bool:
    """Return whether the current dispatcher config defines a named factory."""
    factories_raw = dispatcher_block(cwd=cwd).get("factories")
    return isinstance(factories_raw, dict) and factory in cast("dict[str, Any]", factories_raw)


def has_fabro_factories(*, cwd: Path) -> bool:
    """Return whether dispatcher config constrains factory names."""
    return isinstance(dispatcher_block(cwd=cwd).get("factories"), dict)
