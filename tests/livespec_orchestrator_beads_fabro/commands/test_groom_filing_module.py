"""Pin the cohesive filing helper extracted from the groom front-end.

`groom.py` owns approving, planning and closing a cut.  Filing each local
slice and finding the original item's plan parent are one lower-level ledger
concern, so they live together in `_groom_filing` rather than pushing the
front-end past the file-size ceiling.
"""

from __future__ import annotations

import importlib
from pathlib import Path


def test_groom_filing_helpers_live_in_their_own_cohesive_module() -> None:
    module_path = (
        Path(__file__).parents[3]
        / ".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/_groom_filing.py"
    )
    assert module_path.is_file()

    module = importlib.import_module("livespec_orchestrator_beads_fabro.commands._groom_filing")
    assert callable(module.file_local_slice)
    assert callable(module.plan_parent_id)
