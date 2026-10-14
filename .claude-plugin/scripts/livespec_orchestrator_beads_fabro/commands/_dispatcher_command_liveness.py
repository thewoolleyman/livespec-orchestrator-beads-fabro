"""Bound quiet command nodes by the timeout recorded by the executing engine.

Fabro 0.254's `command.started` event carries `properties.timeout_ms`, read
from the node's resolved timeout by the command handler. Its matching
`command.completed` closes that execution. Read those facts from the run,
rather than guessing a budget from node names or re-reading repository config.

This is permission to remain quiet, NOT a synthetic progress timestamp.
Only a finite, positive recorded budget grants it. The comparison uses epoch
time; the watchdog's observation window uses a separate monotonic clock.
"""

from __future__ import annotations

import json
import math
from typing import Any, cast

from livespec_orchestrator_beads_fabro.commands._dispatcher_watchdog import parse_last_event_epoch
from livespec_orchestrator_beads_fabro.commands._fabro_port_events import (
    fabro_event_records_from_stdout,
)

__all__: list[str] = [
    "command_in_timeout",
]

_MILLISECONDS_PER_SECOND = 1000.0
_COMMAND_EVENTS = ("command.started", "command.completed")


def command_in_timeout(*, events_json: str, now_epoch: float) -> bool:
    """Whether an unfinished command still has time left in its own budget.

    Pair by node and stage visit; revisiting a node must not let an older
    completion close a new execution. Process in timestamp order, with a
    completion winning a tie, so reordered or duplicate records cannot reopen
    an already finished command. Old starts do not renew a deadline per poll.
    """
    active: dict[tuple[str, str], float] = {}
    for epoch, event in _command_events(events_json=events_json):
        node: object = event.get("node_id")
        if not isinstance(node, str) or not node:
            continue
        stage: object = event.get("stage_id")
        key = (node, stage if isinstance(stage, str) else "")
        deadline = _deadline(event=event, epoch=epoch)
        if deadline is None:
            _ = active.pop(key, None)
        else:
            active[key] = deadline
    return any(now_epoch < deadline for deadline in active.values())


def _command_events(*, events_json: str) -> list[tuple[float, dict[str, Any]]]:
    """Timestamped command lifecycle records, ordered by the recorded facts."""
    records = fabro_event_records_from_stdout(stdout=events_json)
    timed: list[tuple[float, dict[str, Any]]] = []
    for event in records or ():
        if event.get("event") not in _COMMAND_EVENTS:
            continue
        epoch = parse_last_event_epoch(events_json=json.dumps(event))
        if epoch is not None and math.isfinite(epoch):
            timed.append((epoch, event))
    return sorted(timed, key=lambda pair: (pair[0], pair[1].get("event") != "command.started"))


def _deadline(*, event: dict[str, Any], epoch: float) -> float | None:
    """A start with an explicit budget grants protection; completion removes it."""
    if event.get("event") != "command.started":
        return None
    properties: object = event.get("properties")
    if not isinstance(properties, dict):
        return None
    timeout: object = cast("dict[str, object]", properties).get("timeout_ms")
    if isinstance(timeout, bool) or not isinstance(timeout, int | float):
        return None
    if not math.isfinite(timeout) or timeout <= 0:
        return None
    return epoch + timeout / _MILLISECONDS_PER_SECOND
