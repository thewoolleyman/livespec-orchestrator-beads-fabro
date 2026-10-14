"""File-backed gate observations preserve verdicts and diagnostic uncertainty."""

import os
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._session_wait_gate import observe_gate_target
from livespec_orchestrator_beads_fabro.commands._session_wait_types import GateTarget


@pytest.fixture
def gate(*, tmp_path: Path) -> GateTarget:
    run_dir = tmp_path / "tmp/gate-runs/gate"
    run_dir.mkdir(parents=True)
    (run_dir / "started_at").write_text("generation\n", encoding="utf-8")
    return GateTarget.freeze(gate_store_root=run_dir.parent, run_id=run_dir.name)


@pytest.mark.parametrize(("code", "state"), [(0, "PASSED"), (23, "FAILED"), (127, "FAILED")])
def test_recorded_verdict_wins_over_missing_pid(*, gate: GateTarget, code: int, state: str) -> None:
    (gate.gate_store_root / gate.run_id / "exit_code").write_text(f"{code}\n", encoding="utf-8")
    observation = observe_gate_target(target=gate, observed_at=1.0)
    assert (observation.state, observation.exit_code) == (state, code)


@pytest.mark.parametrize("name", ["started_at", "exit_code", "pid"])
@pytest.mark.parametrize("content", [b"", b"not-a-number", b"\xff"])
def test_malformed_files_are_not_success(*, gate: GateTarget, name: str, content: bytes) -> None:
    (gate.gate_store_root / gate.run_id / name).write_bytes(content)
    observation = observe_gate_target(target=gate, observed_at=1.0)
    expected = "REPLACED" if name == "started_at" and content != b"\xff" else "UNAVAILABLE"
    assert observation.state == expected
    assert observation.exit_code is None


@pytest.mark.parametrize("name", ["started_at", "exit_code", "pid"])
def test_unreadable_file_is_unavailable(*, gate: GateTarget, name: str) -> None:
    path = gate.gate_store_root / gate.run_id / name
    path.unlink(missing_ok=True)
    path.mkdir()
    assert observe_gate_target(target=gate, observed_at=1.0).state == "UNAVAILABLE"


@pytest.mark.parametrize("pid", ["0", "-1", "999999999999999999999999999999999999"])
def test_invalid_pid_is_unavailable(*, gate: GateTarget, pid: str) -> None:
    (gate.gate_store_root / gate.run_id / "pid").write_text(pid, encoding="utf-8")
    assert observe_gate_target(target=gate, observed_at=1.0).state == "UNAVAILABLE"


def test_missing_pid_means_no_verdict(*, gate: GateTarget) -> None:
    observation = observe_gate_target(target=gate, observed_at=1.0)
    assert observation.state == "DIED_WITHOUT_VERDICT"
    assert observation.exit_code is None


@pytest.mark.parametrize(
    ("error", "state"),
    [(ProcessLookupError, "DIED_WITHOUT_VERDICT"), (PermissionError, "UNAVAILABLE")],
)
def test_liveness_failure_is_distinguished_from_death(
    *, gate: GateTarget, monkeypatch: pytest.MonkeyPatch, error: type[OSError], state: str
) -> None:
    (gate.gate_store_root / gate.run_id / "pid").write_text("123\n", encoding="utf-8")

    def kill(pid: int, signal: int) -> None:
        assert (pid, signal) == (123, 0)
        raise error

    monkeypatch.setattr(os, "kill", kill)
    observation = observe_gate_target(target=gate, observed_at=1.0)
    assert observation.state == state
    assert observation.exit_code is None


@pytest.mark.parametrize(
    ("stat", "state"),
    [
        (FileNotFoundError(), "DIED_WITHOUT_VERDICT"),
        (PermissionError(), "UNAVAILABLE"),
        (UnicodeError(), "UNAVAILABLE"),
        ("", "UNAVAILABLE"),
        ("123 (gate) ? 1", "UNAVAILABLE"),
        ("123 (gate) S 1", "RUNNING"),
    ],
)
def test_process_state_read_distinguishes_exit_from_uncertainty(
    *,
    gate: GateTarget,
    monkeypatch: pytest.MonkeyPatch,
    stat: str | OSError | UnicodeError,
    state: str,
) -> None:
    pid = os.getpid()
    (gate.gate_store_root / gate.run_id / "pid").write_text(f"{pid}\n", encoding="utf-8")
    read_text = Path.read_text

    def proc_text(path: Path, *, encoding: str | None = None, errors: str | None = None) -> str:
        if path == Path(f"/proc/{pid}/stat"):
            if isinstance(stat, OSError | UnicodeError):
                raise stat
            return stat
        return read_text(path, encoding=encoding, errors=errors)

    monkeypatch.setattr(Path, "read_text", proc_text)
    observation = observe_gate_target(target=gate, observed_at=1.0)
    assert observation.state == state
    assert observation.exit_code is None
