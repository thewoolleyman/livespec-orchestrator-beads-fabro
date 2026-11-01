"""The explicitly invoked Dispatcher drift job.

The cleanup-oriented ``reconcile-runs`` command deliberately does not enter
the drift lane or spend model tokens.  This command is the separate operator
surface that does: an operator-enabled schedule may invoke it, while the
repository ships no such schedule or installer.

Its JSON output is the old reconcile projection's ``drift`` value, rather than
the anchor records themselves.  The anchor remains authoritative for those
records; this command reports the lane's outcome without duplicating them.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_invoker import invoker_from_args
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import ShellCommandRunner
from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_drift_lane import (
    DriftLaneOutcome,
    run_drift_lane,
)
from livespec_orchestrator_beads_fabro.commands._drift_run import DriftRunSeams
from livespec_orchestrator_beads_fabro.commands._drift_run_judge import drift_judge
from livespec_orchestrator_beads_fabro.io import write_stdout

__all__: list[str] = ["run_drift_run_command"]

_UNNAMED = "(none)"
_DRY_RUN_OUTCOME = DriftLaneOutcome(
    scope="",
    merges=(),
    frontier=None,
    filed=(),
    held=(),
    advanced=False,
    withheld_reason="dry-run",
    records=None,
)


def run_drift_run_command(*, args: argparse.Namespace) -> int:
    """Run the drift lane, or project that a dry run deliberately ran none."""
    repo = Path(args.repo) if args.repo is not None else Path.cwd()
    outcome = _DRY_RUN_OUTCOME if args.dry_run else _run_lane(repo=repo, args=args)
    _emit(outcome=outcome, as_json=args.as_json)
    return 0


def _run_lane(*, repo: Path, args: argparse.Namespace) -> DriftLaneOutcome:
    """Build the production seams once and hand them to the existing lane."""
    identity = invoker_from_args(args=args)
    runner = ShellCommandRunner()
    return run_drift_lane(
        repo=repo,
        invoker=identity.invoker,
        seams=DriftRunSeams(
            runner=runner,
            judge=drift_judge(
                project_root=repo,
                runner=runner,
                caller=identity.invoker,
            ),
        ),
    )


def _emit(*, outcome: DriftLaneOutcome, as_json: bool) -> None:
    """Render the lane's old reconcile projection on the selected surface."""
    if as_json:
        _ = write_stdout(text=json.dumps(_projection(outcome=outcome), sort_keys=True) + "\n")
        return
    _ = write_stdout(text=_line(outcome=outcome))


def _projection(*, outcome: DriftLaneOutcome) -> dict[str, object] | None:
    """The former ``reconcile-runs --json`` drift value, without anchor bodies."""
    if outcome is _DRY_RUN_OUTCOME:
        return None
    projected = asdict(outcome)
    del projected["records"]
    return projected


def _line(*, outcome: DriftLaneOutcome) -> str:
    """One human line, distinguishing dry execution from a withheld frontier."""
    advanced = str(outcome.advanced).lower()
    frontier = str(outcome.frontier).replace("None", _UNNAMED)
    return f"DRIFT   advanced={advanced} frontier={frontier} reason={outcome.withheld_reason}\n"
