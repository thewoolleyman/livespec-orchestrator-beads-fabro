"""The run-from clones program rides packed like every other helper (bd-ib-p5e32s).

It landed beside the payload compression as a plain-text env value, about 8.3 KB
escaped into the collected `workflow.toml` that Fabro caps at 524,288 bytes. It is
packed now, and its step lands exactly the program the module renders.
"""

from __future__ import annotations

import re

from livespec_orchestrator_beads_fabro.commands._dispatcher_overlay_siblings import SiblingClones
from livespec_orchestrator_beads_fabro.commands._dispatcher_run_from_clones import (
    RUN_FROM_CLONES_ROOT,
    RUN_FROM_REPOS,
    run_from_clone_steps_block,
    run_from_program_source,
)

from tests.prepare_step_support import steps_in, unpacked

_BASE64_LINE = re.compile(r"[A-Za-z0-9+/]+={0,2}")


def test_the_run_from_program_rides_packed_and_unpacks_to_its_source() -> None:
    siblings = SiblingClones(owner="fixture-owner", repos=RUN_FROM_REPOS, clones_root="/x")
    [step] = steps_in(block=run_from_clone_steps_block(siblings=siblings))
    [value] = step.env.values()
    expected = run_from_program_source(
        url_base="https://github.com/fixture-owner", root=RUN_FROM_CLONES_ROOT, repos=RUN_FROM_REPOS
    )

    facts = [
        _BASE64_LINE.fullmatch(value) is not None,
        _BASE64_LINE.fullmatch(value) is not None and unpacked(value=value) == expected,
    ]
    assert all(facts), facts
