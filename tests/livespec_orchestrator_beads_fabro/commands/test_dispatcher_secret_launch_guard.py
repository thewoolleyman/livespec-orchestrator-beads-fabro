"""Failure and cleanup coverage for the native-secret launch transaction."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_io_fabro_launcher as launcher_module,
)
from livespec_orchestrator_beads_fabro.commands import _dispatcher_secret_vault as vault_module
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_io_fabro_launcher import (
    WatchedFabroLauncher,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import build_plan
from livespec_orchestrator_beads_fabro.commands._dispatcher_secret_channel import (
    VaultSecret,
    vault_secret_name,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_secret_vault import FabroVaultSink
from livespec_orchestrator_beads_fabro.commands._dispatcher_watchdog import LivenessSample
from livespec_orchestrator_beads_fabro.commands._fabro_port import FabroRunSummary

_SECRET = VaultSecret(
    env_name="GITHUB_TOKEN",
    secret_name=vault_secret_name(env_name="GITHUB_TOKEN"),
    value="launch-guard-value-canary",
)


@dataclass(kw_only=True)
class _Runner:
    calls: int = 0

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        _ = argv, cwd, timeout_seconds, env, stdin
        self.calls += 1
        return CommandResult(exit_code=0, stdout="", stderr="")


@dataclass(kw_only=True)
class _Journal:
    records: list[dict[str, object]] = field(default_factory=list)

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


@dataclass(kw_only=True)
class _LaunchThread:
    target: Callable[[], None]
    name: str
    alive: list[bool]
    daemon: bool = False

    def start(self) -> None:
        pass

    def is_alive(self) -> bool:
        return self.alive.pop(0)

    def join(self, timeout: float | None = None) -> None:
        _ = timeout
        self.target()


def _sink(*, runner: _Runner, journal: _Journal | None = None) -> FabroVaultSink:
    return FabroVaultSink(
        fabro_bin="fabro",
        server_url="https://factory.example.invalid:32278/lock-failure-tests",
        runner=runner,
        cwd=Path("/workspace/repo"),
        journal=journal,
    )


def test_a_flock_failure_refuses_before_the_value_reaches_fabro(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A host that cannot serialize launches fails closed with a names-only row."""

    def fail_lock(_descriptor: int, _operation: int) -> None:
        raise OSError("lock service unavailable")

    runner = _Runner()
    journal = _Journal()
    monkeypatch.setattr(vault_module.fcntl, "flock", fail_lock)
    message = _sink(runner=runner, journal=journal).set(secret=_SECRET)

    assert message is not None
    assert "launch lock could not be acquired" in message
    assert _SECRET.value not in message
    assert runner.calls == 0
    assert [record["outcome"] for record in journal.records] == ["refused"]


def test_a_pre_handle_failure_closes_the_raw_descriptor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Failure between open and fdopen does not strand a descriptor or run Fabro."""
    runner = _Runner()

    def fail_mode(_descriptor: int, _mode: int) -> None:
        raise OSError("mode could not be set")

    monkeypatch.setattr(vault_module.os, "fchmod", fail_mode)
    message = _sink(runner=runner).set(secret=_SECRET)

    assert message is not None
    assert "launch lock could not be acquired" in message
    assert runner.calls == 0


def test_launch_guard_release_is_idempotent_before_and_after_a_store() -> None:
    """Every fallback may release without knowing whether the native path stored."""
    runner = _Runner()
    sink = _sink(runner=runner)

    sink.release_launch_guard()
    sink.release_launch_guard()
    assert sink.set(secret=_SECRET) is None
    sink.release_launch_guard()
    sink.release_launch_guard()

    assert runner.calls == 1


def test_default_launcher_observes_repeated_running_without_a_release_callback(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Non-native launches keep watching and notify nothing across running polls."""
    discoveries = iter(
        (
            FabroRunSummary(
                run_id="01RUNNING",
                status_kind="running",
                goal=None,
                work_item_id="bd-ib-review",
                total_usd_micros=None,
            ),
            FabroRunSummary(
                run_id="01RUNNING",
                status_kind="running",
                goal=None,
                work_item_id="bd-ib-review",
                total_usd_micros=None,
            ),
        )
    )

    def discover(_self: WatchedFabroLauncher, **_: object) -> FabroRunSummary:
        return next(discoveries)

    def thread(*, target: Callable[[], None], name: str) -> _LaunchThread:
        return _LaunchThread(
            target=target,
            name=name,
            alive=[True, True, True, True, False],
        )

    monkeypatch.setattr(launcher_module.threading, "Thread", thread)
    monkeypatch.setattr(WatchedFabroLauncher, "_discover_run", discover)
    monkeypatch.setattr(
        launcher_module,
        "stamped_attribution",
        lambda **kwargs: kwargs["attribution"],
    )
    monkeypatch.setattr(
        launcher_module,
        "liveness_sample",
        lambda **_: LivenessSample(last_event_epoch=None, observed_at=0.0),
    )
    result = WatchedFabroLauncher(sleep=lambda _seconds: None).launch(
        plan=build_plan(
            repo=tmp_path,
            work_item_id="bd-ib-review",
            workflow_toml=tmp_path / "workflow.toml",
            goal_file=tmp_path / "goal.md",
            fabro_bin="fabro",
            janitor=None,
            janitor_checkout=tmp_path / "janitor",
        ),
        runner=_Runner(),
        journal=_Journal(),
    )

    assert result.command.exit_code == 0
