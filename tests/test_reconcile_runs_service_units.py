"""Contracts for the committed `reconcile-runs` systemd units and their installer.

`systemd-analyze verify` is deliberately NOT used: the committed service is a
TEMPLATE carrying `@PLACEHOLDER@` tokens, so it is not a valid unit until
`install.sh` renders it, and a verifier run against the template would report
the placeholders rather than anything about the unit's meaning.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._config import dispatcher_block
from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_runs_factories import (
    declared_factory_names,
)

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SERVICE_DIR = _REPO_ROOT / "orchestrator-image" / "services" / "reconcile-runs"
_SERVICE = _SERVICE_DIR / "reconcile-runs.service"
_TIMER = _SERVICE_DIR / "reconcile-runs.timer"
_INSTALL = _SERVICE_DIR / "install.sh"

_ENV_WRAPPER = "/usr/local/bin/with-livespec-env.sh"


def _exec_start(*, unit: Path) -> str:
    lines = [
        line
        for line in unit.read_text(encoding="utf-8").splitlines()
        if line.startswith("ExecStart=")
    ]
    assert len(lines) == 1
    return lines[0]


def test_the_committed_exec_start_names_the_env_wrapper_and_the_reconcile_runs_verb() -> None:
    """Without the wrapper the timer runs `bd` with no tenant password."""
    exec_start = _exec_start(unit=_SERVICE)

    assert _ENV_WRAPPER in exec_start
    # The wrapper is the COMMAND, not an argument buried later: it is the first
    # token after `ExecStart=` and it is followed by the `--` separator, which
    # is what makes it wrap the dispatcher rather than merely be mentioned.
    assert exec_start.startswith(f"ExecStart={_ENV_WRAPPER} -- ")
    assert "scripts/bin/dispatcher.py reconcile-runs" in exec_start
    assert "--repo @PRIMARY_REPO@" in exec_start


def test_the_host_timer_surveys_only_the_live_hp_factory() -> None:
    """A retired backend must not remain in the timer's active inventory."""
    configured = dispatcher_block(cwd=_REPO_ROOT)

    assert declared_factory_names(block=configured) == ("hp",)


def test_the_timer_fires_every_ten_minutes_and_catches_up_after_downtime() -> None:
    timer = _TIMER.read_text(encoding="utf-8")

    assert "OnUnitActiveSec=10min" in timer
    assert "Persistent=true" in timer
    assert "Unit=reconcile-runs.service" in timer
    assert "WantedBy=timers.target" in timer


def test_the_installer_refuses_without_the_project_env_wrapper(tmp_path: Path) -> None:
    completed = _install(
        tmp_path=tmp_path,
        env_wrapper=str(tmp_path / "absent-wrapper.sh"),
    )

    assert completed.returncode == 78
    assert "project env wrapper not executable" in completed.stderr
    assert "BEADS_DOLT_PASSWORD" in completed.stderr
    assert not (tmp_path / "units" / "reconcile-runs.service").exists()


def test_the_installer_renders_both_units_when_the_wrapper_resolves(tmp_path: Path) -> None:
    wrapper = tmp_path / "with-livespec-env.sh"
    _ = wrapper.write_text('#!/bin/sh\nexec "$@"\n', encoding="utf-8")
    wrapper.chmod(0o755)

    completed = _install(tmp_path=tmp_path, env_wrapper=str(wrapper))

    assert completed.returncode == 0, completed.stderr
    rendered = tmp_path / "units" / "reconcile-runs.service"
    exec_start = _exec_start(unit=rendered)
    assert exec_start.startswith(f"ExecStart={wrapper} -- ")
    assert "reconcile-runs" in exec_start
    # Every placeholder is substituted: an unrendered token would make systemd
    # refuse the unit at load time, long after the operator has walked away.
    assert "@" not in exec_start
    assert f"--repo {tmp_path / 'repo'}" in exec_start
    assert (tmp_path / "units" / "reconcile-runs.timer").exists()


def test_the_installer_refuses_a_repo_path_that_is_not_a_directory(tmp_path: Path) -> None:
    completed = _install(tmp_path=tmp_path, env_wrapper=str(tmp_path), repo=tmp_path / "nope")

    assert completed.returncode == 78
    assert "is not a directory" in completed.stderr


def test_the_installer_refuses_without_a_repo(tmp_path: Path) -> None:
    completed = _run(argv=[str(_INSTALL)], tmp_path=tmp_path, env_wrapper=str(tmp_path))

    assert completed.returncode == 64
    assert "--repo <primary-checkout> is required" in completed.stderr


def _install(
    *,
    tmp_path: Path,
    env_wrapper: str,
    repo: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    target = repo if repo is not None else tmp_path / "repo"
    if repo is None:
        target.mkdir(exist_ok=True)
    return _run(
        argv=[str(_INSTALL), "--repo", str(target), "--user", "fabro"],
        tmp_path=tmp_path,
        env_wrapper=env_wrapper,
    )


def _run(
    *,
    argv: list[str],
    tmp_path: Path,
    env_wrapper: str,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv,
        capture_output=True,
        text=True,
        check=False,
        env={
            **os.environ,
            "LIVESPEC_ENV_WRAPPER": env_wrapper,
            "UNIT_DIR": str(tmp_path / "units"),
            "DRY_RUN": "1",
        },
    )
