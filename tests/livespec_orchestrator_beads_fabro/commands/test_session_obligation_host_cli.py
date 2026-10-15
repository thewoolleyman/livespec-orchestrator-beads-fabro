"""The two host commands a coordinator registers and completes obligations through.

Scenario 160 requires a dispatch whose obligation is recorded "before the
effect" even though the coordinator "completes its actual turn including FINAL
without ever invoking wait", and Scenario 161 requires an absent recovery owner
to produce "an explicit unmonitored refusal or finding" at launch OR completion.
Both are driven here through `session_wait.main` — the installed host CLI — so
what is measured is the surface an operator actually runs, with no in-process
driver standing in for it.

`complete` is checked against the OBLIGATION store rather than the wait store on
purpose: the whole incident is an obligation whose coordinator armed no wait, so
a completion gate reading wait rows would report a clean turn over outstanding
work.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands import session_wait
from livespec_orchestrator_beads_fabro.commands._session_obligation_coverage import (
    COVERAGE_UNMONITORED,
    COVERAGE_VERIFIED,
    DIAGNOSTIC_OWNER_ABSENT,
)
from livespec_orchestrator_beads_fabro.commands._session_obligation_launch import (
    COMPLETION_PROTECTED,
    COMPLETION_UNMONITORED,
    LAUNCH_ATTACHMENT_PENDING,
    LAUNCH_PROTECTED,
    LAUNCH_UNMONITORED,
)
from livespec_orchestrator_beads_fabro.commands._session_wait_records import (
    process_generation_token,
)
from livespec_orchestrator_beads_fabro.commands._session_wait_routing import (
    default_wait_launcher,
    observe_wait_target,
)
from livespec_orchestrator_beads_fabro.commands._session_wait_types import GATE_TARGET_KIND

_OPERATION = "op-host-1"

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
    return session_wait.SessionWaitCliSeams(
        primary_repository=lambda *, repository: repository,
        launcher=default_wait_launcher,
        observe_target=observe_wait_target,
        process_generation=process_generation_token,
        wall_clock=lambda: 100.0,
        use_tmp_directory=True,
    )


def _declare_coverage(*, primary: Path) -> None:
    path = primary / "tmp" / "session-coverage.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(json.dumps(_SOUND_DECLARATION), encoding="utf-8")


def _start_gate(*, primary: Path, run_id: str) -> None:
    run_dir = primary / "tmp" / "gate-runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    _ = (run_dir / "started_at").write_text("20261015T090000Z\n", encoding="utf-8")


def _launch_argv(*, primary: Path, target: list[str], operation_id: str = _OPERATION) -> list[str]:
    return [
        "launch",
        "--repo",
        str(primary),
        "--session-id",
        "session-h",
        "--invoker",
        "role:coordinator",
        "--scope",
        "plan:agent-session-stall-prevention",
        "--operation-id",
        operation_id,
        "--required-result",
        "item_status bd-ib-zejlae status closed",
        "--result-epoch",
        "4",
        "--original-deadline",
        "2026-10-15T12:00:00Z",
        *target,
    ]


def _payload(*, capsys: pytest.CaptureFixture[str]) -> dict[str, object]:
    return json.loads(capsys.readouterr().out)


def test_launch_registers_a_dispatched_gate_as_a_protected_obligation(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _declare_coverage(primary=tmp_path)
    _start_gate(primary=tmp_path, run_id="g-1")

    code = session_wait.main(
        argv=_launch_argv(primary=tmp_path, target=["--gate", "g-1"]), seams=_seams()
    )

    payload = _payload(capsys=capsys)
    assert code == 0
    assert payload["state"] == LAUNCH_PROTECTED
    assert payload["coverage_state"] == COVERAGE_VERIFIED
    assert payload["protected"] is True
    target = payload["target"]
    assert isinstance(target, dict)
    assert target["kind"] == GATE_TARGET_KIND
    stored = tmp_path / "tmp" / "session-obligations" / f"{_OPERATION}.json"
    assert json.loads(stored.read_text(encoding="utf-8"))["result_epoch"] == 4


def test_launch_on_an_undeclared_host_refuses_as_unmonitored(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _start_gate(primary=tmp_path, run_id="g-1")

    code = session_wait.main(
        argv=_launch_argv(primary=tmp_path, target=["--gate", "g-1"]), seams=_seams()
    )

    payload = _payload(capsys=capsys)
    assert code == 1
    assert payload["state"] == LAUNCH_UNMONITORED
    assert payload["diagnostic"] == DIAGNOSTIC_OWNER_ABSENT
    assert not (tmp_path / "tmp" / "session-obligations").exists()


def test_launch_names_a_delegated_pane_and_rests_pending_when_it_cannot_be_seen(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _declare_coverage(primary=tmp_path)

    code = session_wait.main(
        argv=_launch_argv(
            primary=tmp_path, target=["--pane", str(tmp_path / "absent.sock"), "w1:pF"]
        ),
        seams=_seams(),
    )

    payload = _payload(capsys=capsys)
    assert code == 1
    assert payload["state"] == LAUNCH_ATTACHMENT_PENDING
    assert payload["target"] is None
    stored = tmp_path / "tmp" / "session-obligations" / f"{_OPERATION}.json"
    assert json.loads(stored.read_text(encoding="utf-8"))["target"] is None


def test_launch_refuses_a_request_naming_neither_target(tmp_path: Path) -> None:
    with pytest.raises(SystemExit) as refusal:
        _ = session_wait.main(argv=_launch_argv(primary=tmp_path, target=[]), seams=_seams())

    assert refusal.value.code == 2


def test_complete_reports_the_obligations_a_turn_would_leave_behind(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """An armed wait is never involved; the census reads the obligation store."""
    _declare_coverage(primary=tmp_path)
    _start_gate(primary=tmp_path, run_id="g-1")
    _ = session_wait.main(
        argv=_launch_argv(primary=tmp_path, target=["--gate", "g-1"]), seams=_seams()
    )
    _ = capsys.readouterr()

    code = session_wait.main(argv=["complete", "--repo", str(tmp_path)], seams=_seams())

    payload = _payload(capsys=capsys)
    assert code == 0
    assert payload["state"] == COMPLETION_PROTECTED
    assert payload["outstanding_operation_ids"] == [_OPERATION]


def test_complete_on_an_undeclared_host_is_an_unmonitored_finding(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = session_wait.main(argv=["complete", "--repo", str(tmp_path)], seams=_seams())

    payload = _payload(capsys=capsys)
    assert code == 1
    assert payload["state"] == COMPLETION_UNMONITORED
    assert payload["coverage_state"] == COVERAGE_UNMONITORED
    assert payload["outstanding_operation_ids"] == []
