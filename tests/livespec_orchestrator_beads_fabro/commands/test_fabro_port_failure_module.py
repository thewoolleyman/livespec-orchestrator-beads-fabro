"""The failure-block reader is its own module, split from `_fabro_port_records`.

`_fabro_port_records` had accreted two concerns: normalizing a run LISTING or
an `inspect` record into the shape livespec reads, and CLASSIFYING a failed
run's failure block (the provider spend-ceiling detection, the cause chain, the
permanent-category rewrite). The second is the larger of the two and is the one
the Petri-era payload rebase extends, so it moves to `_fabro_port_failure`
along with the private helpers that only it uses.

The split is checked structurally rather than by behaviour: the behaviour tests
live beside the moved code and would pass either way, so they cannot say WHERE
the code lives. These assertions can.
"""

from __future__ import annotations

import importlib
from pathlib import Path

_COMMANDS = (
    Path(__file__).resolve().parents[3]
    / ".claude-plugin"
    / "scripts"
    / "livespec_orchestrator_beads_fabro"
    / "commands"
)


def test_failure_reader_lives_in_its_own_module() -> None:
    module_path = _COMMANDS / "_fabro_port_failure.py"

    assert module_path.is_file()

    module = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._fabro_port_failure"
    )

    assert module.__all__ == [
        "FabroFailureDetail",
        "fabro_failure_detail_from_payload",
    ]


def test_records_module_no_longer_carries_the_failure_machinery() -> None:
    records = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._fabro_port_records"
    )

    assert "FabroFailureDetail" not in records.__all__
    assert "fabro_failure_detail_from_payload" not in records.__all__
    assert not hasattr(records, "_failure_blocks")
    assert not hasattr(records, "_usage_limit_provider")
