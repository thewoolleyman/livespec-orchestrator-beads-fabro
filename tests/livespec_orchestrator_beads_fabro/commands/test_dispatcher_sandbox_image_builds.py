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
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Iterator
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_sandbox_image_builds import (
    BuildDiscoveryRoots,
    executing_builds,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_sandbox_images import BuildRoot

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
    """
    entry = build / "scripts" / "bin" / "dispatcher.py"
    entry.parent.mkdir(parents=True, exist_ok=True)
    _ = entry.write_text("", encoding="utf-8")
    return subprocess.Popen(["tail", "-f", "/dev/null", str(entry)])


def _reaped_pid() -> int:
    """A pid whose process has exited AND been waited on, so `/proc/<pid>` is gone."""
    finished = subprocess.Popen(["true"])
    _ = finished.wait()
    return finished.pid


def _stopped(*, processes: Iterator[subprocess.Popen[bytes]]) -> None:
    for process in processes:
        process.kill()
        _ = process.wait()


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

    assert builds == (
        BuildRoot(identity="registered", root=registered),
        BuildRoot(identity="leased", root=leased),
        BuildRoot(identity="executed", root=executed),
    )


def test_a_build_manifest_version_is_the_builds_identity(tmp_path: Path) -> None:
    """A build declaring a version is identified by it, not by its directory name."""
    cache = tmp_path / "cache"
    build = cache / "0f9c3a1d"
    build.mkdir(parents=True)
    _ = (build / "plugin.json").write_text(json.dumps({"version": "0.229.8"}), encoding="utf-8")

    builds = executing_builds(install_paths=(build,), roots=_roots(plugin_cache=cache))

    assert builds == (BuildRoot(identity="0.229.8", root=build),)


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
