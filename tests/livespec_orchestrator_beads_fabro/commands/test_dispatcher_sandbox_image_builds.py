"""The executing-build set is the host-wide, deduplicated union of three routes.

`bd-ib-nqmltq`'s executing-builds assertion, proved over REAL host state rather
than a double: a real plugin-cache tree, real `.in_use` lease files, and real
processes this module spawns — one holding a live lease, two impersonating a
running Dispatcher, and two whose process has already exited and been reaped.
The liveness reading is taken against the real `/proc`, which is the only way a
live lease and a stale one can differ for the right reason: a fake proc tree
would make the case pass against an implementation that never asked whether the
recorded process exists.

A pid is made STALE by waiting on the child, not merely by killing it. An
unreaped child is a zombie and `/proc/<pid>` still exists, so a fixture that
only signalled would report every stale lease as live.

EVERY COMPARISON IS SCOPED TO THIS CASE'S OWN SCRATCH TREE, through `_own`. The
payload route is HOST-WIDE by design -- it scans the real `/proc` for any argv
naming a `scripts/bin/dispatcher.py` -- so an exact-equality assertion over the
raw union is partly an assertion about what else the host happens to be running.
Measured 2026-10-21 under `pytest -n 18`: a sibling worker's
`tests/bin/test_payload*` fixture, which spawns a real `dispatcher.py` child out
of a full copy of the plugin root, contributed foreign `BuildRoot`s such as
`/tmp/livespec-public-route-exact-*/install-True`, and the case reds although the
reading is correct. Scoping drops nothing these cases claim: the registered
build, the live lease, the stale lease and the two payload processes are all real
and all under this root, so the live-versus-stale discrimination stays the real
`/proc` one the module exists to take.
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Iterator
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_sandbox_image_builds import (
    BuildDiscoveryRoots,
    executing_builds,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_sandbox_images import BuildRoot

from tests.livespec_orchestrator_beads_fabro.commands import _dispatcher_sandbox_image_readiness
from tests.livespec_orchestrator_beads_fabro.commands._dispatcher_sandbox_image_readiness import (
    start_dispatcher_process,
    wait_for_dispatcher_exec,
)

_PROC = Path("/proc")
_LEASE_DIRECTORY = ".in_use"
_SLEEP_SECONDS = "600"


def _roots(*, plugin_cache: Path, proc: Path = _PROC) -> BuildDiscoveryRoots:
    return BuildDiscoveryRoots(plugin_cache=plugin_cache, proc=proc)


def _lease(*, build: Path, pid: int) -> None:
    lease_directory = build / _LEASE_DIRECTORY
    lease_directory.mkdir(parents=True, exist_ok=True)
    _ = (lease_directory / str(pid)).write_text(f"{pid}\n", encoding="utf-8")


def _sleeper() -> subprocess.Popen[bytes]:
    return subprocess.Popen(["sleep", _SLEEP_SECONDS])


def _reaped_pid() -> int:
    """A pid whose process has exited AND been waited on, so `/proc/<pid>` is gone."""
    finished = subprocess.Popen(["true"])
    _ = finished.wait()
    return finished.pid


def _stopped(*, processes: Iterator[subprocess.Popen[bytes]]) -> None:
    for process in processes:
        process.kill()
        _ = process.wait()


def _own(*, builds: tuple[BuildRoot, ...], root: Path) -> tuple[BuildRoot, ...]:
    """Only the builds under this case's own scratch tree, in the union's own order."""
    return tuple(build for build in builds if build.root.is_relative_to(root))


def test_executing_builds_are_the_host_wide_deduplicated_union(tmp_path: Path) -> None:
    """Registered install, live lease and running payload all contribute; a stale lease does not."""
    cache = tmp_path / "cache"
    registered, leased, executed, abandoned = (
        cache / name for name in ("registered", "leased", "executed", "abandoned")
    )
    for build in (registered, leased, executed, abandoned):
        build.mkdir(parents=True)
    live = _sleeper()
    payloads = (start_dispatcher_process(build=executed), start_dispatcher_process(build=leased))
    try:
        _lease(build=registered, pid=_reaped_pid())
        _lease(build=leased, pid=live.pid)
        _lease(build=abandoned, pid=_reaped_pid())

        builds = executing_builds(install_paths=(registered,), roots=_roots(plugin_cache=cache))
    finally:
        _stopped(processes=iter((live, *payloads)))

    assert _own(builds=builds, root=cache) == (
        BuildRoot(identity="registered", root=registered),
        BuildRoot(identity="leased", root=leased),
        BuildRoot(identity="executed", root=executed),
    )


def test_dispatcher_fixture_reaps_a_child_when_readiness_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A readiness failure does not leak the fixture child process."""

    def _fail_readiness(**_: object) -> None:
        raise AssertionError("fixture never became ready")

    monkeypatch.setattr(
        _dispatcher_sandbox_image_readiness, "wait_for_dispatcher_exec", _fail_readiness
    )

    with pytest.raises(AssertionError, match="fixture never became ready"):
        start_dispatcher_process(build=tmp_path / "build")


def test_only_the_shared_readiness_helper_spawns_the_dispatcher_argv_fixture() -> None:
    """A second `tail` fixture copy would skip the exec rendezvous, so none may exist."""
    needle = '"tail", "-f", ' + '"/dev/null"'
    tests_root = Path(__file__).resolve().parents[2]
    holders = sorted(
        path.name for path in tests_root.rglob("*.py") if needle in path.read_text(encoding="utf-8")
    )

    assert holders == ["_dispatcher_sandbox_image_readiness.py"]


def _readiness_entry(*, tmp_path: Path) -> Path:
    return tmp_path / "build" / "scripts" / "bin" / "dispatcher.py"


def test_dispatcher_fixture_readiness_returns_once_cmdline_names_the_entry(tmp_path: Path) -> None:
    """The sleep is skipped when the first poll already sees the payload argv."""
    process = _sleeper()
    try:
        entry = _readiness_entry(tmp_path=tmp_path)
        cmdline = tmp_path / "proc" / str(process.pid) / "cmdline"
        cmdline.parent.mkdir(parents=True)
        _ = cmdline.write_bytes(f"tail\0-f\0{entry}\0".encode())
        sleeps: list[float] = []

        wait_for_dispatcher_exec(
            process=process,
            entry=entry,
            proc=tmp_path / "proc",
            monotonic=lambda: 0.0,
            sleep=sleeps.append,
        )
    finally:
        _stopped(processes=iter((process,)))

    assert sleeps == []


def test_dispatcher_fixture_readiness_sleeps_until_cmdline_names_the_entry(tmp_path: Path) -> None:
    """An absent cmdline, then another argv, are each slept past until the entry appears."""
    process = _sleeper()
    try:
        entry = _readiness_entry(tmp_path=tmp_path)
        cmdline = tmp_path / "proc" / str(process.pid) / "cmdline"
        argvs = iter((b"", b"tail\0-f\0", f"tail\0-f\0{entry}\0".encode()))
        sleeps: list[float] = []

        def _sleep(seconds: float) -> None:
            sleeps.append(seconds)
            cmdline.parent.mkdir(parents=True, exist_ok=True)
            _ = cmdline.write_bytes(next(argvs))

        wait_for_dispatcher_exec(
            process=process,
            entry=entry,
            proc=tmp_path / "proc",
            poll_seconds=0.5,
            monotonic=lambda: 0.0,
            sleep=_sleep,
        )
    finally:
        _stopped(processes=iter((process,)))

    assert sleeps == [0.5, 0.5, 0.5]


def test_dispatcher_fixture_readiness_times_out_when_cmdline_is_unreadable(tmp_path: Path) -> None:
    """An unreadable cmdline past the injected deadline raises an error naming the pid."""
    process = _sleeper()
    try:
        ticks = iter((0.0, 31.0))
        sleeps: list[float] = []
        with pytest.raises(AssertionError, match=f"process {process.pid} did not exec"):
            wait_for_dispatcher_exec(
                process=process,
                entry=_readiness_entry(tmp_path=tmp_path),
                proc=tmp_path / "proc",
                timeout_seconds=30.0,
                monotonic=lambda: next(ticks),
                sleep=sleeps.append,
            )
    finally:
        _stopped(processes=iter((process,)))

    assert sleeps == []


def test_a_build_manifest_version_is_the_builds_identity(tmp_path: Path) -> None:
    """A build declaring a version is identified by it, not by its directory name."""
    cache = tmp_path / "cache"
    build = cache / "0f9c3a1d"
    build.mkdir(parents=True)
    _ = (build / "plugin.json").write_text(json.dumps({"version": "0.229.8"}), encoding="utf-8")

    builds = executing_builds(install_paths=(build,), roots=_roots(plugin_cache=cache))

    assert _own(builds=builds, root=cache) == (BuildRoot(identity="0.229.8", root=build),)


def test_an_absent_plugin_cache_and_proc_tree_contribute_no_build(tmp_path: Path) -> None:
    """Neither host tree existing is an empty union, never a refusal."""
    builds = executing_builds(
        install_paths=(),
        roots=_roots(plugin_cache=tmp_path / "absent-cache", proc=tmp_path / "absent-proc"),
    )

    assert builds == ()


def test_a_process_entry_with_no_readable_argv_contributes_no_build(tmp_path: Path) -> None:
    """A pid whose `cmdline` cannot be read is passed over, and its peers are not."""
    proc = tmp_path / "proc"
    (proc / "4242").mkdir(parents=True)
    (proc / "self").mkdir()
    build = tmp_path / "cache" / "payload"
    entry = build / "scripts" / "bin" / "dispatcher.py"
    entry.parent.mkdir(parents=True)
    _ = entry.write_text("", encoding="utf-8")
    named = proc / "4343"
    named.mkdir()
    _ = (named / "cmdline").write_bytes(f"python3\0{entry}\0".encode())

    builds = executing_builds(
        install_paths=(), roots=_roots(plugin_cache=tmp_path / "cache", proc=proc)
    )

    assert builds == (BuildRoot(identity="payload", root=build),)
