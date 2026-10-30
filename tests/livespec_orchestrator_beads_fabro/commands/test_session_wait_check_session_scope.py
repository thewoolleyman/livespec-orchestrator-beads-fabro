"""The host `check` command can be scoped to one owning session.

Scenario 158 requires the turn-end check to run before the OWNING session
finishes its turn. The Stop hook therefore passes the stopping session's id, and
a wait or launch obligation owned by a different session must not block it,
while the unscoped `check --repo <repo>` stays the repository-wide audit.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands import session_wait
from livespec_orchestrator_beads_fabro.commands._session_wait_routing import (
    default_wait_launcher,
)
from livespec_orchestrator_beads_fabro.commands._session_wait_types import (
    GateObservation,
    WaitTarget,
)

_GENERATION = "generation-live"

_SOUND_DECLARATION: dict[str, object] = {
    "max_observation_interval_seconds": 15.0,
    "proof_artifact": "livespec-overseer-consumer@0.1.0",
    "recovery_route": "overseer-supervised-service",
    "runtime": "codex",
    "runtime_version": "0.60.0",
    "service_generation": "7",
    "service_identity": "livespec-overseer-consumer.service",
    "takeover_budget_seconds": 20.0,
    "terminal_backend": "herdr",
    "terminal_instance": "w1:pF",
    "terminal_version": "0.9.3",
}


def _seams() -> session_wait.SessionWaitCliSeams:
    def observe(*, target: WaitTarget, observed_at: float) -> GateObservation:
        return GateObservation.finished(
            target=target, state="FAILED", exit_code=23, observed_at=observed_at
        )

    def generation(*, pid: int) -> str | None:
        return None if pid == 0 else _GENERATION

    return session_wait.SessionWaitCliSeams(
        primary_repository=lambda *, repository: repository,
        launcher=default_wait_launcher,
        observe_target=observe,
        process_generation=generation,
        wall_clock=lambda: 500.0,
        use_tmp_directory=True,
    )


def _write_wait(*, primary: Path, wait_id: str, session_id: str) -> None:
    wait_root = primary / "tmp" / "session-waits"
    wait_root.mkdir(parents=True, exist_ok=True)
    payload: dict[str, object] = {
        "acknowledgement": {
            "acknowledged": False,
            "acknowledged_at": None,
            "kind": None,
            "session_id": None,
        },
        "armed_at": 10.0,
        "deadline_at": 1000.0,
        "deadline_seconds": 990.0,
        "observation_sequence": 0,
        "observations": [],
        "repository": str(primary),
        "return_ready": False,
        "return_reason": None,
        "schema_version": 1,
        "session_id": session_id,
        "targets": [
            {
                "kind": "gate",
                "gate_store_root": str(primary / "tmp" / "gate-runs"),
                "run_id": f"run-{wait_id}",
                "generation": "generation-run",
            }
        ],
        "wait_id": wait_id,
        "waiter": {"generation": _GENERATION, "pid": 4242},
    }
    _ = (wait_root / f"{wait_id}.json").write_text(json.dumps(payload), encoding="utf-8")


def _launch(*, primary: Path, session_id: str, operation_id: str) -> None:
    declaration = primary / "tmp" / "session-coverage.json"
    declaration.parent.mkdir(parents=True, exist_ok=True)
    _ = declaration.write_text(json.dumps(_SOUND_DECLARATION), encoding="utf-8")
    run_dir = primary / "tmp" / "gate-runs" / f"g-{operation_id}"
    run_dir.mkdir(parents=True, exist_ok=True)
    _ = (run_dir / "started_at").write_text("20261015T090000Z\n", encoding="utf-8")
    argv = [
        "launch",
        "--repo",
        str(primary),
        "--session-id",
        session_id,
        "--invoker",
        "role:coordinator",
        "--scope",
        "plan:scoped-stop",
        "--operation-id",
        operation_id,
        "--required-result",
        "item_status bd-ib-4b23u6 status closed",
        "--result-epoch",
        "1",
        "--original-deadline",
        "2026-10-15T12:00:00Z",
        "--gate",
        f"g-{operation_id}",
    ]
    assert session_wait.main(argv=argv, seams=_seams()) == 0
    declaration.unlink()


def _check_ids(
    *, primary: Path, session_id: str | None, capsys: pytest.CaptureFixture[str]
) -> tuple[int, list[str]]:
    _ = capsys.readouterr()
    argv = ["check", "--repo", str(primary)]
    if session_id is not None:
        argv += ["--session-id", session_id]
    code = session_wait.main(argv=argv, seams=_seams())
    payload = json.loads(capsys.readouterr().out)
    return code, [str(entry["id"]) for entry in payload["summary"]["findings"]]


def test_a_wait_owned_by_another_session_does_not_block_the_stopping_session(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_wait(primary=tmp_path, wait_id="wait-other", session_id="session-other")

    code, ids = _check_ids(primary=tmp_path, session_id="session-mine", capsys=capsys)

    assert (code, ids) == (0, [])


def test_a_wait_owned_by_the_stopping_session_still_blocks_its_stop(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_wait(primary=tmp_path, wait_id="wait-other", session_id="session-other")
    _write_wait(primary=tmp_path, wait_id="wait-mine", session_id="session-mine")

    code, ids = _check_ids(primary=tmp_path, session_id="session-mine", capsys=capsys)

    assert (code, ids) == (1, ["wait-mine"])


def test_check_without_a_session_reports_every_sessions_findings(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_wait(primary=tmp_path, wait_id="wait-other", session_id="session-other")
    _write_wait(primary=tmp_path, wait_id="wait-mine", session_id="session-mine")

    code, ids = _check_ids(primary=tmp_path, session_id=None, capsys=capsys)

    assert (code, sorted(ids)) == (1, ["wait-mine", "wait-other"])


def test_a_launch_obligation_is_reported_only_to_its_owning_session(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _launch(primary=tmp_path, session_id="session-other", operation_id="op-other")

    other_code, other_ids = _check_ids(primary=tmp_path, session_id="session-mine", capsys=capsys)
    owner_code, owner_ids = _check_ids(primary=tmp_path, session_id="session-other", capsys=capsys)
    audit_code, audit_ids = _check_ids(primary=tmp_path, session_id=None, capsys=capsys)

    assert (other_code, other_ids) == (0, [])
    assert (owner_code, owner_ids) == (1, ["op-other"])
    assert (audit_code, audit_ids) == (1, ["op-other"])
