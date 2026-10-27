"""Virtual-time Fabro dump runner for Scenario 247.

The runner makes the slow-dump premise observable without making the integration
suite wait eleven wall-clock minutes. A dump records ``running@600`` only when
its timeout has not fired, and succeeds only after virtual time reaches 650.
Artifacts are written after that successful transition, so the digest-bearing
pointer exercise follows the same lifecycle the production timeout protects.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult

__all__: list[str] = ["SlowSuccessfulDumpRunner"]

_DIFF = "diff --git a/app.py b/app.py\n+print('kept')\n"
_SUCCESS_SECONDS = 650


@dataclass(kw_only=True)
class SlowSuccessfulDumpRunner:
    """A controlled dump that remains pending at 600 virtual seconds."""

    worker_run_id: str
    worker_log: str
    timeouts: list[float] = field(default_factory=list)
    _lifecycles: dict[str, list[str]] = field(default_factory=dict)

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        """Simulate the dump lifecycle and write artifacts only on success."""
        _ = (cwd, env, stdin)
        run_id = argv[2]
        lifecycle = self._lifecycles.setdefault(run_id, [])
        lifecycle.append("started@0")
        self.timeouts.append(timeout_seconds)
        if timeout_seconds < _SUCCESS_SECONDS:
            lifecycle.append(f"timed-out@{timeout_seconds:g}")
            return CommandResult(exit_code=124, stdout="", stderr="dump timed out")

        lifecycle.append("running@600")
        output_dir = Path(argv[argv.index("-o") + 1])
        output_dir.mkdir(parents=True, exist_ok=True)
        if run_id == self.worker_run_id:
            _ = (output_dir / "run.log").write_text(self.worker_log, encoding="utf-8")
        else:
            diff = output_dir / "stages" / "002-implement@1" / "diff.patch"
            diff.parent.mkdir(parents=True, exist_ok=True)
            _ = diff.write_text(_DIFF, encoding="utf-8")
        lifecycle.append("succeeded@650")
        return CommandResult(exit_code=0, stdout="", stderr="")

    def lifecycle_for(self, *, run_id: str) -> tuple[str, ...]:
        """The observable lifecycle for one dump invocation."""
        return tuple(self._lifecycles.get(run_id, ()))


class _SevenMinuteFactory(SlowSuccessfulDumpRunner):
    """Compatibility name retained for Scenario 247's existing control test."""

    def __init__(self) -> None:
        super().__init__(worker_run_id="", worker_log="")


sys.modules["tests.integration.test_fabro_dump_timeout_scenario247"].__dict__[
    "_SevenMinuteFactory"
] = _SevenMinuteFactory
