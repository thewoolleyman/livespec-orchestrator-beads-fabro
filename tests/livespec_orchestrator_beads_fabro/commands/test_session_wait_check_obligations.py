"""The host `check` command verifies launch obligations even when no wait exists.

Scenario 158: an owning session finishing a turn with unresolved authorized
work must be covered "with no wait", so the installed `check` has to read the
OBLIGATION store and the declared independent recovery coverage, not only wait
rows. Every case here arms nothing: the wait store stays empty throughout, which
is the incident's own shape and the only fixture under which a `check` that read
wait rows alone could pass.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands import session_wait
from livespec_orchestrator_beads_fabro.commands._session_telemetry_events import SessionEvent
from livespec_orchestrator_beads_fabro.commands._session_wait_records import (
    process_generation_token,
)
from livespec_orchestrator_beads_fabro.commands._session_wait_routing import (
    default_wait_launcher,
    observe_wait_target,
)

_OPERATION = "op-check-1"

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


def _declare_coverage(*, primary: Path) -> Path:
    path = primary / "tmp" / "session-coverage.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(json.dumps(_SOUND_DECLARATION), encoding="utf-8")
    return path


def _launch_unfinished_work(*, primary: Path) -> None:
    run_dir = primary / "tmp" / "gate-runs" / "g-1"
    run_dir.mkdir(parents=True, exist_ok=True)
    _ = (run_dir / "started_at").write_text("20261015T090000Z\n", encoding="utf-8")
    argv = [
        "launch",
        "--repo",
        str(primary),
        "--session-id",
        "session-c",
        "--invoker",
        "role:coordinator",
        "--scope",
        "plan:agent-session-stall-prevention",
        "--operation-id",
        _OPERATION,
        "--required-result",
        "item_status bd-ib-zejlae status closed",
        "--result-epoch",
        "4",
        "--original-deadline",
        "2026-10-15T12:00:00Z",
        "--gate",
        "g-1",
    ]
    assert session_wait.main(argv=argv, seams=_seams()) == 0


def _check(*, primary: Path, capsys: pytest.CaptureFixture[str]) -> tuple[int, dict[str, object]]:
    _ = capsys.readouterr()
    code = session_wait.main(argv=["check", "--repo", str(primary)], seams=_seams())
    return code, json.loads(capsys.readouterr().out)


def _findings(*, payload: dict[str, object]) -> list[dict[str, object]]:
    assert "summary" in payload
    summary = payload["summary"]
    assert isinstance(summary, dict)
    findings = summary["findings"]
    assert isinstance(findings, list)
    return findings


def _completion(*, payload: dict[str, object]) -> dict[str, object]:
    assert "completion" in payload
    completion = payload["completion"]
    assert isinstance(completion, dict)
    return completion


def test_check_flags_unfinished_work_whose_independent_owner_is_gone(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    declaration = _declare_coverage(primary=tmp_path)
    _launch_unfinished_work(primary=tmp_path)
    declaration.unlink()

    code, payload = _check(primary=tmp_path, capsys=capsys)

    assert not list((tmp_path / "tmp" / "session-waits").glob("*.json"))
    assert code == 1
    assert _findings(payload=payload) == [
        {
            "finding": "unmonitored",
            "id": _OPERATION,
            "record_state": "available",
            "source": "obligation",
        }
    ]
    completion = _completion(payload=payload)
    assert completion["state"] == "unmonitored"
    assert completion["outstanding_operation_ids"] == [_OPERATION]


def test_check_accepts_unfinished_work_that_an_independent_owner_covers(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _ = _declare_coverage(primary=tmp_path)
    _launch_unfinished_work(primary=tmp_path)

    code, payload = _check(primary=tmp_path, capsys=capsys)

    assert code == 0
    assert _findings(payload=payload) == []
    completion = _completion(payload=payload)
    assert completion["state"] == "protected"
    assert completion["outstanding_operation_ids"] == [_OPERATION]


def test_check_has_no_finding_for_an_undeclared_host_with_nothing_unfinished(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, payload = _check(primary=tmp_path, capsys=capsys)

    assert code == 0
    assert _findings(payload=payload) == []
    completion = _completion(payload=payload)
    assert completion["outstanding_operation_ids"] == []


def test_check_reports_an_unreadable_obligation_store_as_unobservable(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    store = tmp_path / "tmp" / "session-obligations"
    store.mkdir(parents=True)
    _ = (store / "op-corrupt.json").write_text("{not json", encoding="utf-8")

    code, payload = _check(primary=tmp_path, capsys=capsys)

    assert code == 1
    assert _findings(payload=payload) == [
        {
            "finding": "unobservable",
            "id": "obligation-store",
            "record_state": "unavailable",
            "source": "obligation",
        }
    ]


@dataclass(kw_only=True)
class _Sink:
    events: list[SessionEvent] = field(default_factory=list)
    exporting: bool = True

    def emit(self, *, event: SessionEvent) -> None:
        self.events.append(event)


def test_check_publishes_the_coverage_grade_it_reads_at_the_seam_clock(tmp_path: Path) -> None:
    from livespec_orchestrator_beads_fabro.commands._session_obligation_cli import (
        completion_check,
    )

    sink = _Sink()

    _ = completion_check(primary=tmp_path, telemetry=sink, wall_clock=lambda: 100.0)

    assert [(event.name, event.at) for event in sink.events] == [
        ("session.recovery.coverage", 100.0)
    ]
