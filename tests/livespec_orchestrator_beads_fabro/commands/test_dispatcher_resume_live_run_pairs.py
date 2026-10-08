"""Building the live-run tuple from what a factory answered with.

A builder rather than a comprehension at the call site, because the ORDER of the
pair is what a caller gets wrong, and a swapped pair produces a refusal that reads
as a status named where a run id belongs — plausible, actionable-looking, and
pointing at nothing an operator can look up. This file is the binding that keeps
the two fields the right way round.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

_MODULE_NAME = "livespec_orchestrator_beads_fabro.commands._dispatcher_resume_refusals"
_MODULE_PATH = Path(
    ".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/"
    "_dispatcher_resume_refusals.py"
)


def _refusals_module() -> Any:
    assert _MODULE_PATH.is_file()
    return importlib.import_module(_MODULE_NAME)


def test_each_pair_becomes_a_live_run_with_its_id_and_status_in_order() -> None:
    """The first element is the run id and the second is its status, never the reverse."""
    module = _refusals_module()
    built = module.live_runs_from_pairs(pairs=(("01M4ONE", "running"), ("01M4TWO", "blocked")))
    assert built == (
        module.LiveRun(run_id="01M4ONE", status="running"),
        module.LiveRun(run_id="01M4TWO", status="blocked"),
    )


def test_no_pairs_build_no_live_runs() -> None:
    """An answering factory with nothing alive is the empty tuple, not a refusal."""
    module = _refusals_module()
    assert module.live_runs_from_pairs(pairs=()) == ()
