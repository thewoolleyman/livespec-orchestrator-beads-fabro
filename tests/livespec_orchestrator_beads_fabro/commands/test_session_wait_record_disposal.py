"""Recording onto a record disposed mid-wait reports rather than raising.

The sibling of the no-resurrection case in `test_session_wait_record_safety`,
from the other end: there an INVENTORY pass races a disposal, here the WAIT's
own return does. Both re-read under the lock and both have to tell "the record
is gone" apart from "the write succeeded", which is what the `is True` read of
the lock helper's result buys — an unacquired lock reports None and a disposed
record reports False, and a None-only test would call the disposal a success.
"""

from __future__ import annotations

from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._session_wait_records import (
    REGISTRATION_REGISTERED,
    WaiterIdentity,
    record_observations,
    record_return_ready,
    register_wait,
    wait_record_path,
)
from livespec_orchestrator_beads_fabro.commands._session_wait_types import (
    GateObservation,
    GateTarget,
    WaitRequest,
)


def _target(*, gate_store_root: Path, run_id: str) -> GateTarget:
    run_dir = gate_store_root / run_id
    run_dir.mkdir(parents=True)
    _ = (run_dir / "started_at").write_text(f"generation-{run_id}\n", encoding="utf-8")
    return GateTarget.freeze(gate_store_root=gate_store_root, run_id=run_id)


def test_recording_onto_a_disposed_record_reports_instead_of_raising(*, tmp_path: Path) -> None:
    target = _target(gate_store_root=tmp_path / "gate-runs", run_id="only")
    wait_store_root = tmp_path / "session-waits"
    assert (
        register_wait(
            request=WaitRequest(
                wait_id="disposed",
                session_id="session-disposed",
                repository=tmp_path,
                deadline_seconds=30.0,
                targets=(target,),
            ),
            wait_store_root=wait_store_root,
            waiter=WaiterIdentity(pid=111, generation="waiter-original"),
            armed_at=1.0,
        )
        == REGISTRATION_REGISTERED
    )
    observation = GateObservation.running(target=target, observed_at=2.0)
    record = wait_record_path(wait_store_root=wait_store_root, wait_id="disposed")

    assert (
        record_observations(
            wait_store_root=wait_store_root,
            wait_id="disposed",
            observations=(observation,),
        )
        is True
    )
    assert (
        record_return_ready(
            wait_store_root=wait_store_root,
            wait_id="disposed",
            return_reason="target-ended",
        )
        is True
    )

    record.unlink()

    assert (
        record_observations(
            wait_store_root=wait_store_root,
            wait_id="disposed",
            observations=(observation,),
        )
        is False
    )
    assert (
        record_return_ready(
            wait_store_root=wait_store_root,
            wait_id="disposed",
            return_reason="target-ended",
        )
        is False
    )
    assert not record.exists()
