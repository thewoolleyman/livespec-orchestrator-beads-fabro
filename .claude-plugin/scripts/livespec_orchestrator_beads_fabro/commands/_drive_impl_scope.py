"""The host dispatch memory slice an `impl:` dispatch launches its loop inside.

Per-run Dispatcher loops were one of the uncapped Python consumers when the dev
host ran out of memory (13 loops measured 0.23-1.69G steady, 2.53G peak). The
host provisions a user-manager `factory-dispatch.slice` and publishes a per-loop
bound at `/etc/livespec/factory-dispatch-loop-memory-max`; a slice bounds only
what is LAUNCHED INTO it, so this module is the launch half of that contract.

PURE DECISIONS AROUND ONE IMPURE READ. `scope_plan` answers whether the host
provides the slice, from the four facts the clause names, each read through the
`ScopeHost` seam so a test never needs a systemd user manager. `SystemScopeHost`
is the one real implementation; `default_scope_host` is the one function the
launch reads it through.

THE FOUR FACTS ARE READ CHEAPEST FIRST and any one failing answers `None`: the
published bound file, the scope launcher on PATH, the memory controller offered
to the user manager, and last the one subprocess (`systemctl --user show`) that
asks whether the slice loads. A host missing any of them launches exactly as
before, and none of the reads can fail the launch: an unreadable file, a missing
binary and a timed-out `systemctl` are each the answer "not provided".

THE SCOPE CARRIES `OOMPolicy=continue` BECAUSE SYSTEMD 257 DEFAULTS TO
`DefaultOOMPolicy=stop`, under which one OOM-killed child would stop the whole
scope and strand the run. The scope is named by this launch (`--unit`), so the
name is known before the loop starts and can be recorded without parsing the
launcher's output.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

__all__: list[str] = [
    "LAUNCH_SCOPED",
    "LAUNCH_UNSCOPED",
    "MEMORY_MAX_PATH",
    "SCOPE_STAGE",
    "SLICE_NAME",
    "ScopeHost",
    "ScopePlan",
    "SystemScopeHost",
    "default_scope_host",
    "launch_record",
    "scope_launch_failure",
    "scope_plan",
    "scope_unit_name",
    "scoped_argv",
]

SLICE_NAME = "factory-dispatch.slice"
SCOPE_STAGE = "dispatch-launch-scope"
LAUNCH_SCOPED = "scoped"
LAUNCH_UNSCOPED = "unscoped"
MEMORY_MAX_PATH = Path("/etc/livespec/factory-dispatch-loop-memory-max")
CGROUP_ROOT = Path("/sys/fs/cgroup")
_SYSTEMCTL_TIMEOUT_SECONDS = 10
# A systemd memory size: digits, an optional fraction, an optional unit suffix.
_MEMORY_SIZE = re.compile(r"\d+(?:\.\d+)?[BKMGTPE]?")
_UNIT_UNSAFE = re.compile(r"[^A-Za-z0-9:_.\-]")
_FAILURE_DETAIL_LIMIT = 500


class ScopeHost(Protocol):
    """What the launching user's service manager and the host provision."""

    def memory_max(self) -> str | None:
        """The published per-loop memory bound, or None when it holds no size."""
        ...

    def launcher(self) -> str | None:
        """The scope launcher's path, or None when it is not installed."""
        ...

    def slice_loaded(self) -> bool:
        """Whether the user's service manager loads the dispatch slice."""
        ...

    def memory_delegated(self) -> bool:
        """Whether the user's service manager is offered the memory controller."""
        ...


@dataclass(frozen=True, kw_only=True)
class ScopePlan:
    launcher: str
    memory_max: str


@dataclass(frozen=True, kw_only=True)
class SystemScopeHost:
    """The real host: the published file, PATH, the cgroup tree and `systemctl`."""

    memory_max_path: Path
    cgroup_root: Path = CGROUP_ROOT

    def memory_max(self) -> str | None:
        try:
            value = self.memory_max_path.read_text(encoding="utf-8").strip()
        except OSError:
            return None
        return value if _MEMORY_SIZE.fullmatch(value) else None

    def launcher(self) -> str | None:
        return shutil.which("systemd-run")

    def slice_loaded(self) -> bool:
        argv = ("systemctl", "--user", "show", SLICE_NAME, "--property=LoadState", "--value")
        try:
            completed = subprocess.run(  # noqa: S603 - argv is constructed without shell.
                argv,
                check=False,
                capture_output=True,
                text=True,
                timeout=_SYSTEMCTL_TIMEOUT_SECONDS,
            )
        except (OSError, subprocess.SubprocessError):
            return False
        return completed.returncode == 0 and completed.stdout.strip() == "loaded"

    def memory_delegated(self) -> bool:
        uid = os.getuid()
        manager = self.cgroup_root / "user.slice" / f"user-{uid}.slice" / f"user@{uid}.service"
        try:
            controllers = (manager / "cgroup.controllers").read_text(encoding="utf-8")
        except OSError:
            return False
        return "memory" in controllers.split()


def default_scope_host() -> ScopeHost:
    """The host an `impl:` dispatch reads; the one seam a test replaces.

    The bound file's path is read from the module global at call time, so a
    suite that must not see the machine it runs on redirects `MEMORY_MAX_PATH`
    and leaves this function itself exercisable.
    """
    return SystemScopeHost(memory_max_path=MEMORY_MAX_PATH)


def scope_plan(*, host: ScopeHost) -> ScopePlan | None:
    """The scoped launch the host supports, or None when any condition fails."""
    memory_max = host.memory_max()
    if memory_max is None:
        return None
    launcher = host.launcher()
    if launcher is None or not host.memory_delegated() or not host.slice_loaded():
        return None
    return ScopePlan(launcher=launcher, memory_max=memory_max)


def scope_unit_name(*, work_item_ref: str) -> str:
    """A transient scope name unique to this launch, carrying the item it serves."""
    safe = _UNIT_UNSAFE.sub("_", work_item_ref)
    return f"livespec-dispatch-{safe}-{uuid.uuid4().hex[:8]}.scope"


def scoped_argv(*, plan: ScopePlan, unit: str, argv: tuple[str, ...]) -> tuple[str, ...]:
    """The loop's own argv, wrapped to run in a transient scope of the slice."""
    return (
        plan.launcher,
        "--user",
        "--scope",
        f"--unit={unit}",
        f"--slice={SLICE_NAME}",
        "-p",
        "OOMPolicy=continue",
        "-p",
        f"MemoryMax={plan.memory_max}",
        "--",
        *argv,
    )


def scope_launch_failure(*, unit: str, returncode: int, stderr: str) -> str | None:
    """Why the scoped launch failed before the loop ran, or None when the loop ran.

    The launcher returns the loop's own exit status, so a non-zero exit alone is
    NOT a failed launch: a loop that started in its scope and exited non-zero has
    run, and its exit is the loop's result. The launcher announces the scope it
    created (`Running scope as unit: <unit>`) before it runs the command, which
    is what tells the two apart without parsing anything the loop prints.
    """
    if returncode == 0 or f"Running scope as unit: {unit}" in stderr:
        return None
    return stderr.strip()[:_FAILURE_DETAIL_LIMIT] or f"scope launcher exited {returncode}"


def launch_record(
    *, work_item_id: str, launch: str, scope_unit: str | None, detail: str | None = None
) -> dict[str, object]:
    """The one dispatch-journal record a launch leaves, naming which launch it used."""
    record: dict[str, object] = {
        "stage": SCOPE_STAGE,
        "work_item_id": work_item_id,
        "launch": launch,
    }
    if scope_unit is not None:
        record["scope_unit"] = scope_unit
    if detail is not None:
        record["detail"] = detail
    return record
