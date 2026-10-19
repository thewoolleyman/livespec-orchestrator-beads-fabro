"""Production reader for factory-native ACP run records."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from livespec_orchestrator_beads_fabro.commands._config import resolve_fabro_factory
from livespec_orchestrator_beads_fabro.commands._fabro_port_records import (
    FabroRunSummary,
    fabro_inspect_record,
    fabro_run_summaries_from_payload,
)

__all__: list[str] = ["FactoryRunReader"]
_FABRO_TIMEOUT_SECONDS = 60


@dataclass(frozen=True, kw_only=True)
class FactoryRunReader:
    """Read each declared factory through explicitly targeted Fabro commands."""

    repo: Path

    def list_runs(self, *, factory: str) -> tuple[FabroRunSummary, ...] | None:
        payload = self._read(factory=factory, args=["ps", "-a", "--json"])
        if not isinstance(payload, list):
            return None
        return fabro_run_summaries_from_payload(payload=cast("list[object]", payload))

    def inspect_payload(self, *, factory: str, run_id: str) -> object | None:
        payload = self._read(factory=factory, args=["inspect", "--json"], run_id=run_id)
        return payload if fabro_inspect_record(payload=payload) is not None else None

    def _read(self, *, factory: str, args: list[str], run_id: str | None = None) -> object | None:
        target = resolve_fabro_factory(cwd=self.repo, factory=factory)
        if target.server is None:
            return None
        suffix = [] if run_id is None else [run_id]
        try:
            completed = subprocess.run(  # noqa: S603
                ["fabro", *args, "--server", target.server, *suffix],  # noqa: S607
                capture_output=True,
                text=True,
                check=False,
                timeout=_FABRO_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired:
            return None
        if completed.returncode != 0:
            return None
        try:
            return json.loads(completed.stdout)
        except json.JSONDecodeError:
            return None
