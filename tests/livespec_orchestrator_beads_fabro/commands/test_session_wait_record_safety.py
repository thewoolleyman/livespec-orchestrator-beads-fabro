"""Fail-closed identities and concurrent disposal for session-wait records."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import Mock

from livespec_orchestrator_beads_fabro.commands._session_wait_records import (
    WaiterIdentity,
    read_wait_record,
    register_wait,
)
from livespec_orchestrator_beads_fabro.commands._session_wait_types import ProbeLauncher
from livespec_orchestrator_beads_fabro.commands.session_wait import (
    GateObservation,
    GateTarget,
    WaitRequest,
    ack_wait,
    inventory_waits,
    run_wait,
)
from livespec_orchestrator_beads_fabro.commands.session_wait_inventory import (
    ProcessGeneration,
    TargetObserver,
)


def _target(*, gate_store_root: Path, run_id: str) -> GateTarget:
    gate_dir = gate_store_root / run_id
    gate_dir.mkdir(parents=True)
    _ = (gate_dir / "started_at").write_text(f"generation-{run_id}\n", encoding="utf-8")
    return GateTarget.freeze(gate_store_root=gate_store_root, run_id=run_id)


def _request(*, repository: Path, wait_id: str, session_id: str, target: GateTarget) -> WaitRequest:
    return WaitRequest(
        wait_id=wait_id,
        session_id=session_id,
        repository=repository,
        deadline_seconds=30.0,
        targets=(target,),
    )


def test_malformed_records_are_unavailable_instead_of_raising(*, tmp_path: Path) -> None:
    wait_store_root = tmp_path / "session-waits"
    wait_store_root.mkdir()
    array_path = wait_store_root / "array.json"
    incomplete_path = wait_store_root / "incomplete.json"
    invalid_type_path = wait_store_root / "invalid-type.json"
    _ = array_path.write_text("[]\n", encoding="utf-8")
    _ = incomplete_path.write_text('{"schema_version": 1}\n', encoding="utf-8")
    invalid_type_payload = {
        "acknowledgement": {
            "acknowledged": False,
            "acknowledged_at": None,
            "kind": None,
            "session_id": None,
        },
        "armed_at": 1.0,
        "deadline_at": 31.0,
        "deadline_seconds": 30.0,
        "observation_sequence": 0,
        "observations": [],
        "repository": str(tmp_path),
        "return_ready": False,
        "return_reason": None,
        "schema_version": 1,
        "session_id": "owner",
        "targets": [],
        "wait_id": "invalid-type",
        "waiter": "not-an-object",
    }
    _ = invalid_type_path.write_text(
        json.dumps(invalid_type_payload) + "\n",
        encoding="utf-8",
    )

    with ThreadPoolExecutor(max_workers=4) as pool:
        reads = [
            pool.submit(read_wait_record, path=array_path),
            pool.submit(read_wait_record, path=incomplete_path),
            pool.submit(read_wait_record, path=invalid_type_path),
        ]
        acknowledged = pool.submit(
            ack_wait,
            wait_store_root=wait_store_root,
            wait_id="invalid-type",
            session_id="owner",
            acknowledged_at=1.0,
            retention_limit=10,
        )
    errors = [future.exception() for future in [*reads, acknowledged]]

    assert errors == [None, None, None, None]
    assert [future.result().diagnostic for future in reads] == [
        "invalid-record",
        "invalid-record",
        "invalid-record",
    ]
    assert acknowledged.result().status == "unavailable"
    snapshot = inventory_waits(
        wait_store_root=wait_store_root,
        observed_at=2.0,
        observe_target=Mock(spec=TargetObserver),
        process_generation=Mock(spec=ProcessGeneration),
    )
    assert {(row.wait_id, row.record_state, row.diagnostic) for row in snapshot.records} == {
        ("array", "unavailable", "invalid-record"),
        ("incomplete", "unavailable", "invalid-record"),
        ("invalid-type", "unavailable", "invalid-record"),
    }


def test_duplicate_wait_identity_refuses_before_probing(*, tmp_path: Path) -> None:
    gate_store_root = tmp_path / "gate-runs"
    original = _target(gate_store_root=gate_store_root, run_id="original")
    replacement = _target(gate_store_root=gate_store_root, run_id="replacement")
    wait_store_root = tmp_path / "session-waits"
    original_request = _request(
        repository=tmp_path,
        wait_id="same-wait",
        session_id="original-owner",
        target=original,
    )
    assert (
        register_wait(
            request=original_request,
            wait_store_root=wait_store_root,
            waiter=WaiterIdentity(pid=111, generation="waiter-original"),
            armed_at=1.0,
        )
        == "registered"
    )
    probe = Mock()
    probe.poll.return_value = GateObservation.finished(
        target=replacement,
        state="FAILED",
        exit_code=23,
        observed_at=2.0,
    )
    launcher = Mock(spec=ProbeLauncher)
    launcher.launch.return_value = probe

    result = run_wait(
        request=_request(
            repository=tmp_path,
            wait_id="same-wait",
            session_id="replacement-owner",
            target=replacement,
        ),
        launcher=launcher,
        wait_store_root=wait_store_root,
    )

    assert result.command_outcome == "registration-conflict"
    launcher.launch.assert_not_called()
    payload = json.loads((wait_store_root / "same-wait.json").read_text(encoding="utf-8"))
    assert payload["session_id"] == "original-owner"
    assert payload["targets"][0]["run_id"] == "original"


def test_inventory_does_not_resurrect_record_disposed_during_observation(*, tmp_path: Path) -> None:
    gate_store_root = tmp_path / "gate-runs"
    victim = _target(gate_store_root=gate_store_root, run_id="victim")
    other = _target(gate_store_root=gate_store_root, run_id="other")
    wait_store_root = tmp_path / "session-waits"
    waiters = {
        "wait-a-victim": WaiterIdentity(pid=111, generation="waiter-victim"),
        "wait-z-other": WaiterIdentity(pid=222, generation="waiter-other"),
    }
    for wait_id, session_id, target in (
        ("wait-a-victim", "session-victim", victim),
        ("wait-z-other", "session-other", other),
    ):
        assert (
            register_wait(
                request=_request(
                    repository=tmp_path,
                    wait_id=wait_id,
                    session_id=session_id,
                    target=target,
                ),
                wait_store_root=wait_store_root,
                waiter=waiters[wait_id],
                armed_at=1.0,
            )
            == "registered"
        )
    assert (
        ack_wait(
            wait_store_root=wait_store_root,
            wait_id="wait-z-other",
            session_id="session-other",
            acknowledged_at=20.0,
            retention_limit=2,
        ).status
        == "receipt-acknowledged"
    )

    def observe_target(*, target: GateTarget, observed_at: float) -> GateObservation:
        if target == victim:
            assert (
                ack_wait(
                    wait_store_root=wait_store_root,
                    wait_id="wait-a-victim",
                    session_id="session-victim",
                    acknowledged_at=10.0,
                    retention_limit=1,
                ).status
                == "receipt-acknowledged"
            )
        return GateObservation.running(target=target, observed_at=observed_at)

    with ThreadPoolExecutor(max_workers=1) as pool:
        reconciled = pool.submit(
            inventory_waits,
            wait_store_root=wait_store_root,
            observed_at=30.0,
            observe_target=observe_target,
            process_generation=lambda *, pid: waiters[
                "wait-a-victim" if pid == 111 else "wait-z-other"
            ].generation,
        )
    error = reconciled.exception()

    assert error is None
    snapshot = reconciled.result()
    rows = {row.wait_id: row for row in snapshot.records}
    assert rows["wait-a-victim"].record_state == "unavailable"
    assert rows["wait-a-victim"].diagnostic == "record-disposed"
    assert not (wait_store_root / "wait-a-victim.json").exists()
    assert rows["wait-z-other"].observation_sequence == 1
