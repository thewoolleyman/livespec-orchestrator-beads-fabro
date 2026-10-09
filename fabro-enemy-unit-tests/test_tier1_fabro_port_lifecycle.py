"""Tier 1 Enemy Unit Test for the server-API cancel the reconciler depends on.

`cancel` is the ONLY lifecycle verb the pinned CLI exposes nowhere, so the run
reconciler reaches it over the server's HTTP API. Nothing had ever run it
against a live factory, which made the reconciler's whole terminate leg an
assumption: an engine that answered 2xx without stopping the run, or that
stopped it without removing it from the scheduler, would leave a held slot
behind and look perfectly healthy doing it.

This suite launches a real run and spends real runtime, so it is excluded from
`just fabro-enemy-tier0` and from `just check`. Invoke it explicitly:

    just fabro-enemy-tier1

THE ASSERTION IS ON THE RUN'S OWN STATE, not on the response. A 2xx from the
cancel route says the server ACCEPTED the request; only `inspect` afterwards
says the run actually stopped, and those are the two readings a held-slot
incident cannot tell apart from its own record.
"""

from __future__ import annotations

import time
from pathlib import Path

from _tier0_support import (
    TERMINAL_STATUS_KINDS,
    TIMEOUT_SECONDS,
    _assert_success,
    _FabroTier0Config,
)
from _tier1_support import _write_goal, _write_workflow
from livespec_orchestrator_beads_fabro.commands._fabro_port import FabroPort

__all__: list[str] = []

_POLL_TIMEOUT_SECONDS = 180.0
_POLL_INTERVAL_SECONDS = 2.0
_SLEEPING_WORKFLOW = """
digraph FabroEnemyCancelable {
    start [shape=Mdiamond, label="Start"]
    sleep [shape=parallelogram, label="Sleep", timeout="600s", script="sleep 600"]
    exit [shape=Msquare, label="Exit"]
    start -> sleep
    sleep -> exit
}
"""


def _await_terminal_status(*, port: FabroPort, run_id: str) -> str | None:
    """Poll `inspect` until the run reports a terminal kind, or time out."""
    deadline = time.monotonic() + _POLL_TIMEOUT_SECONDS
    last: str | None = None
    while time.monotonic() < deadline:
        inspect = port.inspect(run_id=run_id, timeout_seconds=TIMEOUT_SECONDS)
        last = inspect.status_kind
        if last in TERMINAL_STATUS_KINDS:
            return last
        time.sleep(_POLL_INTERVAL_SECONDS)
    return last


def test_cancel_stops_an_in_flight_run_and_not_merely_accepts_the_request(
    *,
    config: _FabroTier0Config,
    port: FabroPort,
    tmp_path: Path,
) -> None:
    workflow = _write_workflow(tmp_path=tmp_path, name="cancelable", body=_SLEEPING_WORKFLOW)
    goal = _write_goal(tmp_path=tmp_path, title="cancel")

    # The sleeping workflow never completes inside the budget, so `run` returns
    # when the CLI is killed at the timeout while the server keeps the run in
    # flight — which is the state the reconciler finds a stranded run in.
    launched = port.run(
        workflow_toml=workflow,
        goal_file=goal,
        inputs=(),
        timeout_seconds=TIMEOUT_SECONDS,
    )
    assert launched.run_id is not None
    face = port.server_api()
    # Recorded BEFORE the cancel: with no credential the route answers 401 and
    # the case below would read as an engine that declined to cancel.
    assert face.bearer_token() is not None, (
        f"no bearer credential resolved for {config.server_url}; "
        f"the cancel route cannot be exercised unauthenticated"
    )

    cancelled = face.cancel(run_id=launched.run_id, timeout_seconds=TIMEOUT_SECONDS)

    assert cancelled.succeeded, f"status {cancelled.status}: {cancelled.error or cancelled.body}"
    # The load-bearing half: acceptance is not cessation.
    status_kind = _await_terminal_status(port=port, run_id=launched.run_id)
    assert (
        status_kind in TERMINAL_STATUS_KINDS
    ), f"run {launched.run_id} was accepted for cancellation but reports {status_kind!r}"
    removed = port.rm(run_id=launched.run_id, timeout_seconds=TIMEOUT_SECONDS)
    _assert_success(command=removed.command)
