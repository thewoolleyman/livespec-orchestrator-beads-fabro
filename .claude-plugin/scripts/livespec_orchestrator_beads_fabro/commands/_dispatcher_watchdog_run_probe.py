"""One cancelled run's own record, read once while the run still exists.

Extracted from `_dispatcher_stall_cancel` when the whole-run wall budget became
the second cancel class needing the same reading. That module owns the STALL
cancel and this owns the reading both cancels take, because the reading is
where the ORDERING guarantee lives and a second copy of it is a second place
for that ordering to be got wrong.

`fabro rm -f` is what makes these two surfaces unavailable, so a reading taken
afterwards is a reading of nothing -- and it would still SUCCEED, reporting an
unobservable run as a run with no publication. That is a confident negative
earned from a read that saw nothing, and it reads exactly like a correct record
of an unpublished run.

TWO SURFACES ARE READ AND CONCATENATED because the publication marker travels
on the node's stderr and WHICH surface carries that stderr depends on the
engine build -- the event stream on one, the inspect record on another.
Concatenating is correct rather than lazy: the marker reader takes the LAST
marker in the text, and both surfaces describe the same run, so a marker found
twice is the same marker.
"""

from __future__ import annotations

from dataclasses import dataclass

from livespec_orchestrator_beads_fabro.commands._dispatcher_io_liveness_probe import (
    FABRO_PROBE_TIMEOUT_SECONDS,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port import FabroPort

__all__: list[str] = [
    "WatchdogRunReading",
    "watchdog_run_reading",
]


@dataclass(frozen=True, kw_only=True)
class WatchdogRunReading:
    """One cancelled run's own record, as the two probes returned it.

    `events_json` is the lifecycle stream the stage reading needs as JSON;
    `record_text` is the same stream plus the inspect record as flat text, which
    is where the publication marker is matched. Two fields rather than one
    because the stage reading must PARSE and the marker reading must not: a
    marker reader handed only the parsed stream would miss a build that carries
    node stderr on the inspect record alone.
    """

    events_json: str
    record_text: str


def watchdog_run_reading(*, port: FabroPort, run_id: str) -> WatchdogRunReading:
    """Read one run's events and inspect record, BEFORE anything terminates it.

    A failed probe contributes the empty string, which names no stage and no
    publication. That is the honest reading: the record says nothing, which is
    what `executing_stage` returning `None` means.
    """
    events = port.events(run_id=run_id, timeout_seconds=FABRO_PROBE_TIMEOUT_SECONDS)
    events_json = events.command.stdout if events.command.exit_code == 0 else ""
    inspect = port.inspect(run_id=run_id, timeout_seconds=FABRO_PROBE_TIMEOUT_SECONDS)
    inspect_text = (
        f"{inspect.command.stdout}\n{inspect.command.stderr}"
        if inspect.command.exit_code == 0
        else ""
    )
    return WatchdogRunReading(
        events_json=events_json,
        record_text=f"{events_json}\n{inspect_text}",
    )
