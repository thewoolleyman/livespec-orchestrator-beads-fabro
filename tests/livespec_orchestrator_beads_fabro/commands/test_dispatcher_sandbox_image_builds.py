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
    await_dispatcher_ready,
    start_dispatcher_fixture,
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


def _dispatcher_process(*, build: Path) -> subprocess.Popen[bytes]:
    """A real live process whose own argv names `<build>/scripts/bin/dispatcher.py`.

    That argv IS what identifies a running Dispatcher — every invocation of it
    goes through that one entry point — so the fixture only has to be a real
    process carrying it, and deliberately is NOT a Python child:
    `check-tests-no-subprocess-spawn` asks tests not to spawn one, and a real
    Dispatcher would need a factory and a tenant to get past its first argument.
    The fixture is a shell that announces itself once it is running, so this
    returns on an event rather than after a poll of `/proc`.
    """
    entry = build / "scripts" / "bin" / "dispatcher.py"
    entry.parent.mkdir(parents=True, exist_ok=True)
    _ = entry.write_text("", encoding="utf-8")
    return start_dispatcher_fixture(entry=entry)


def _reaped_pid() -> int:
    """A pid whose process has exited AND been waited on, so `/proc/<pid>` is gone."""
    finished = subprocess.Popen(["true"])
    _ = finished.wait()
    return finished.pid


def _stopped(*, processes: Iterator[subprocess.Popen[bytes]]) -> None:
    for process in processes:
        process.kill()
        _ = process.communicate()


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
    payloads = (_dispatcher_process(build=executed), _dispatcher_process(build=leased))
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
    spawned: list[subprocess.Popen[bytes]] = []

    def _fail_readiness(*, process: subprocess.Popen[bytes], entry: Path) -> None:
        _ = entry
        spawned.append(process)
        raise AssertionError("fixture never became ready")

    monkeypatch.setattr(
        _dispatcher_sandbox_image_readiness, "await_dispatcher_ready", _fail_readiness
    )

    with pytest.raises(AssertionError, match="fixture never became ready"):
        _dispatcher_process(build=tmp_path / "build")

    assert len(spawned) == 1
    assert spawned[0].poll() is not None


def test_dispatcher_fixture_readiness_fails_when_the_fixture_exits_unannounced(
    tmp_path: Path,
) -> None:
    """A fixture that dies before announcing itself fails readiness rather than hanging."""
    process = subprocess.Popen(["true"], stdout=subprocess.PIPE)
    try:
        with pytest.raises(AssertionError, match="never announced"):
            await_dispatcher_ready(
                process=process,
                entry=tmp_path / "build" / "scripts" / "bin" / "dispatcher.py",
            )
    finally:
        _stopped(processes=iter((process,)))


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
