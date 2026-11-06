"""The durable receipt for a non-merged run's newest WIP capture."""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._dispatcher_wip_capture_receipt import (
    WipCapture,
    latest_wip_capture,
)


def test_the_highest_numeric_wip_ref_is_the_run_s_latest_capture() -> None:
    capture = latest_wip_capture(
        work_item_id="bd-ib-xdhe5z",
        run_id="01RUN",
        refs={
            "refs/livespec/wip/bd-ib-xdhe5z/01RUN/2": "b" * 40,
            "refs/livespec/wip/bd-ib-xdhe5z/01RUN/11": "c" * 40,
            "refs/livespec/wip/bd-ib-xdhe5z/01RUN/3": "d" * 40,
            "refs/livespec/wip/other/01RUN/99": "e" * 40,
        },
    )

    assert capture == WipCapture(ref="refs/livespec/wip/bd-ib-xdhe5z/01RUN/11", commit="c" * 40)
