"""The host dispatch memory slice decisions of `_drive_impl_scope`.

The launch itself is bound at the integration tier by
`tests/integration/test_impl_dispatch_memory_slice_scenario371.py`; these cover
what that tier stands in for: each of the four host facts read for real, and the
decision that refuses a scoped launch when any one of them fails.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands import _drive_impl_scope as scope

_UID = 4242


@dataclass(kw_only=True)
class _Host:
    memory_max_value: str | None = "3500M"
    launcher_path: str | None = "/usr/bin/systemd-run"
    slice_is_loaded: bool = True
    memory_is_delegated: bool = True
    asked_for_slice: bool = False

    def memory_max(self) -> str | None:
        return self.memory_max_value

    def launcher(self) -> str | None:
        return self.launcher_path

    def slice_loaded(self) -> bool:
        self.asked_for_slice = True
        return self.slice_is_loaded

    def memory_delegated(self) -> bool:
        return self.memory_is_delegated


def test_a_host_providing_every_condition_plans_a_scoped_launch() -> None:
    assert scope.scope_plan(host=_Host()) == scope.ScopePlan(
        launcher="/usr/bin/systemd-run", memory_max="3500M"
    )


@pytest.mark.parametrize(
    "missing",
    [
        _Host(memory_max_value=None),
        _Host(launcher_path=None),
        _Host(memory_is_delegated=False),
        _Host(slice_is_loaded=False),
    ],
)
def test_a_host_missing_any_condition_plans_no_scope(missing: _Host) -> None:
    assert scope.scope_plan(host=missing) is None


def test_the_slice_is_only_asked_after_the_cheaper_facts_hold() -> None:
    host = _Host(memory_max_value=None)

    assert scope.scope_plan(host=host) is None
    assert host.asked_for_slice is False


def test_scoped_argv_wraps_the_loop_argv_without_changing_it() -> None:
    plan = scope.ScopePlan(launcher="/usr/bin/systemd-run", memory_max="3500M")

    assert scope.scoped_argv(plan=plan, unit="u.scope", argv=("python3", "loop", "--json")) == (
        "/usr/bin/systemd-run",
        "--user",
        "--scope",
        "--unit=u.scope",
        "--slice=factory-dispatch.slice",
        "-p",
        "OOMPolicy=continue",
        "-p",
        "MemoryMax=3500M",
        "--",
        "python3",
        "loop",
        "--json",
    )


def test_the_unit_name_is_unique_per_launch_and_safe_for_a_unit_file_name() -> None:
    first = scope.scope_unit_name(work_item_ref="bd-ib-1")
    second = scope.scope_unit_name(work_item_ref="bd-ib-1")
    hostile = scope.scope_unit_name(work_item_ref="a b/c")

    assert first != second
    assert first.startswith("livespec-dispatch-bd-ib-1-")
    assert first.endswith(".scope")
    assert hostile.startswith("livespec-dispatch-a_b_c-")


def test_the_launch_record_names_the_scope_only_for_a_scoped_launch() -> None:
    assert scope.launch_record(work_item_id="i", launch="scoped", scope_unit="u.scope") == {
        "stage": "dispatch-launch-scope",
        "work_item_id": "i",
        "launch": "scoped",
        "scope_unit": "u.scope",
    }
    assert scope.launch_record(work_item_id="i", launch="unscoped", scope_unit=None) == {
        "stage": "dispatch-launch-scope",
        "work_item_id": "i",
        "launch": "unscoped",
    }


@pytest.mark.parametrize(
    ("content", "expected"),
    [("3500M\n", "3500M"), ("  4G ", "4G"), ("2.5G", "2.5G"), ("1048576", "1048576")],
)
def test_the_published_bound_is_read_when_it_holds_a_memory_size(
    tmp_path: Path, content: str, expected: str
) -> None:
    bound = tmp_path / "bound"
    _ = bound.write_text(content, encoding="utf-8")

    assert scope.SystemScopeHost(memory_max_path=bound).memory_max() == expected


@pytest.mark.parametrize("content", ["", "\n", "lots", "3500 M", "-1G", "infinity"])
def test_a_published_bound_that_is_not_a_memory_size_is_not_a_bound(
    tmp_path: Path, content: str
) -> None:
    bound = tmp_path / "bound"
    _ = bound.write_text(content, encoding="utf-8")

    assert scope.SystemScopeHost(memory_max_path=bound).memory_max() is None


def test_an_absent_published_bound_is_not_a_bound(tmp_path: Path) -> None:
    assert scope.SystemScopeHost(memory_max_path=tmp_path / "absent").memory_max() is None


def test_the_launcher_is_whatever_path_resolution_finds(monkeypatch: pytest.MonkeyPatch) -> None:
    host = scope.SystemScopeHost(memory_max_path=Path("unused"))

    def _found(name: str) -> str | None:
        return f"/opt/{name}"

    def _missing(name: str) -> str | None:
        del name
        return None

    monkeypatch.setattr(scope.shutil, "which", _found)
    assert host.launcher() == "/opt/systemd-run"
    monkeypatch.setattr(scope.shutil, "which", _missing)
    assert host.launcher() is None


def _manager_controllers(*, root: Path, text: str) -> None:
    manager = root / "user.slice" / f"user-{_UID}.slice" / f"user@{_UID}.service"
    manager.mkdir(parents=True)
    _ = (manager / "cgroup.controllers").write_text(text, encoding="utf-8")


def test_the_memory_controller_is_delegated_when_the_user_manager_is_offered_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(os, "getuid", lambda: _UID)
    _manager_controllers(root=tmp_path, text="cpu memory pids\n")

    host = scope.SystemScopeHost(memory_max_path=Path("unused"), cgroup_root=tmp_path)

    assert host.memory_delegated() is True


def test_the_memory_controller_is_not_delegated_when_the_manager_lacks_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(os, "getuid", lambda: _UID)
    _manager_controllers(root=tmp_path, text="cpu pids\n")

    host = scope.SystemScopeHost(memory_max_path=Path("unused"), cgroup_root=tmp_path)

    assert host.memory_delegated() is False


def test_the_memory_controller_is_not_delegated_without_a_user_manager_cgroup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(os, "getuid", lambda: _UID)

    host = scope.SystemScopeHost(memory_max_path=Path("unused"), cgroup_root=tmp_path)

    assert host.memory_delegated() is False


def _completed(*, returncode: int, stdout: str) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=(), returncode=returncode, stdout=stdout, stderr="")


def test_the_slice_is_loaded_when_the_user_manager_reports_it_loaded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asked: list[tuple[str, ...]] = []

    def _run(argv: tuple[str, ...], **_: object) -> subprocess.CompletedProcess[str]:
        asked.append(argv)
        return _completed(returncode=0, stdout="loaded\n")

    monkeypatch.setattr(scope.subprocess, "run", _run)

    assert scope.SystemScopeHost(memory_max_path=Path("unused")).slice_loaded() is True
    assert asked == [
        ("systemctl", "--user", "show", "factory-dispatch.slice", "--property=LoadState", "--value")
    ]


@pytest.mark.parametrize(
    ("returncode", "stdout"), [(0, "not-found\n"), (1, "loaded\n"), (0, ""), (0, "masked\n")]
)
def test_the_slice_is_not_loaded_for_any_other_report(
    monkeypatch: pytest.MonkeyPatch, returncode: int, stdout: str
) -> None:
    def _run(*_: object, **__: object) -> subprocess.CompletedProcess[str]:
        return _completed(returncode=returncode, stdout=stdout)

    monkeypatch.setattr(scope.subprocess, "run", _run)

    assert scope.SystemScopeHost(memory_max_path=Path("unused")).slice_loaded() is False


@pytest.mark.parametrize(
    "fault",
    [FileNotFoundError("no systemctl"), subprocess.TimeoutExpired(cmd="systemctl", timeout=1)],
)
def test_an_unaskable_service_manager_does_not_load_the_slice(
    monkeypatch: pytest.MonkeyPatch, fault: Exception
) -> None:
    def _run(*_: object, **__: object) -> subprocess.CompletedProcess[str]:
        raise fault

    monkeypatch.setattr(scope.subprocess, "run", _run)

    assert scope.SystemScopeHost(memory_max_path=Path("unused")).slice_loaded() is False


def test_the_default_host_reads_the_published_bound_path_at_call_time(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bound = tmp_path / "bound"
    _ = bound.write_text("2G", encoding="utf-8")
    monkeypatch.setattr(scope, "MEMORY_MAX_PATH", bound)

    assert scope.default_scope_host().memory_max() == "2G"
