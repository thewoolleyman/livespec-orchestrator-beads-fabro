"""Scenario 212 — the read-only sandbox-image enumeration, end to end.

Binds `SPECIFICATION/scenarios.md` "Scenario 212 — The sandbox-images command
reports the sandbox image sources a dispatch without an explicit workflow path
resolves, through dispatch resolution, and changes nothing", and the
`contracts.md` section "Sandbox image enumeration" it exercises.

Driven through the PRODUCTION `dispatcher.py` argument parser and handler table,
over real host state in a scratch HOME: a real `installed_plugins.json`, real
repository checkouts with their own `.livespec.jsonc` and run configs, real
plugin-cache builds carrying real `.in_use` lease files, and real processes —
one holding a live lease, two carrying a running Dispatcher's own argv, and two
already exited and reaped. Nothing is stood in, because every claim the clause
makes is about what the command READS off a host.

TWO CLAIMS CANNOT BE OBSERVED AT THE UNIT TIER AND ARE WHY THIS MODULE EXISTS.
The first is the join between the three layers: the repositories come from the
registry, the builds from the lease and process scan, and the entries from the
per-repository resolver, so a respelling at any seam leaves each unit module
self-consistent while the command reports the wrong array. The second is that
the command CHANGES NOTHING — a claim about the whole host tree before and
after, which no single function's return value can carry, so it is measured as
a recursive snapshot of every path under the scratch HOME and both repository
checkouts.

THE STALE-LEASE CASE IS THE SHARPEST SUB-SCENARIO. A pid is made stale by
WAITING on the child and not merely by signalling it: an unreaped child is a
zombie whose `/proc/<pid>` entry still exists, so a fixture that only killed it
would report every stale lease as live and the case would pass against an
implementation that never asked.
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Iterator
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands import dispatcher

_FACTORY = "hp"
_PLUGIN_KEY = "livespec-orchestrator-beads-fabro@livespec-orchestrator-beads-fabro"
_OTHER_PLUGIN_KEY = "some-other-plugin@its-own-marketplace"
_REGISTRY = (".claude", "plugins", "installed_plugins.json")
_CACHE = (".claude", "plugins", "cache")
_RESERVED = (".fabro", "workflows", "implement-work-item", "workflow.toml")
_LEASE_DIRECTORY = ".in_use"
_SLEEP_SECONDS = "600"
_CONFIG = ".livespec.jsonc"


def _write_workflow(*, path: Path, image: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(
        '[run.environment]\nid = "livespec-ci"\n'
        '\n[environments.livespec-ci]\nprovider = "docker"\n'
        f'\n[environments.livespec-ci.image]\ndocker = "{image}"\n',
        encoding="utf-8",
    )


def _write_config(*, repo: Path, dispatcher_block: dict[str, object]) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    _ = (repo / _CONFIG).write_text(
        json.dumps({"livespec-orchestrator-beads-fabro": {"dispatcher": dispatcher_block}}),
        encoding="utf-8",
    )


def _lease(*, build: Path, pid: int) -> None:
    lease = build / _LEASE_DIRECTORY
    lease.mkdir(parents=True, exist_ok=True)
    _ = (lease / str(pid)).write_text(f"{pid}\n", encoding="utf-8")


def _sleeper() -> subprocess.Popen[bytes]:
    return subprocess.Popen(["sleep", _SLEEP_SECONDS])


def _dispatcher_process(*, build: Path) -> subprocess.Popen[bytes]:
    """A real live process whose own argv names `<build>/scripts/bin/dispatcher.py`."""
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


def _snapshot(*, roots: tuple[Path, ...]) -> dict[str, bytes | None]:
    """Every path under `roots`, with each file's bytes — the change-nothing instrument."""
    seen: dict[str, bytes | None] = {}
    for root in roots:
        for path in sorted(root.rglob("*")):
            seen[str(path)] = path.read_bytes() if path.is_file() else None
    return seen


def test_scenario212_sandbox_images_enumerates_every_source_and_changes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Catalog, configured, variants, committed, bundled, undeclared and unreadable, in one array."""
    home = tmp_path / "home"
    cache = home.joinpath(*_CACHE)
    registered, leased, executed, abandoned = (
        cache / name for name in ("registered", "leased", "executed", "abandoned")
    )
    for build, image in (
        (registered, "ghcr.io/example/sandbox:registered"),
        (leased, "ghcr.io/example/sandbox:leased"),
        (executed, "ghcr.io/example/sandbox:executed"),
        (abandoned, "ghcr.io/example/sandbox:abandoned"),
    ):
        _write_workflow(path=build.joinpath(*_RESERVED), image=image)

    catalog = tmp_path / "catalog-repo"
    _write_config(
        repo=catalog,
        dispatcher_block={"factories": {_FACTORY: {"environment": "livespec-ci-hp"}}},
    )
    bundled = tmp_path / "bundled-repo"
    _write_config(
        repo=bundled,
        dispatcher_block={
            "factories": {_FACTORY: {}},
            "workflows": {"fast": ".fabro/workflows/fast"},
        },
    )
    _write_workflow(
        path=bundled / ".fabro" / "workflows" / "fast" / "workflow.toml",
        image="ghcr.io/example/sandbox:fast",
    )
    registry = home.joinpath(*_REGISTRY)
    registry.parent.mkdir(parents=True, exist_ok=True)
    _ = registry.write_text(
        json.dumps(
            {
                "plugins": {
                    _PLUGIN_KEY: [
                        {"projectPath": str(catalog), "installPath": str(registered)},
                        {"projectPath": str(bundled), "installPath": str(registered)},
                    ],
                    _OTHER_PLUGIN_KEY: [
                        {"projectPath": str(tmp_path / "theirs"), "installPath": str(leased)}
                    ],
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("LIVESPEC_FABRO_SANDBOX_IMAGE", raising=False)

    live = _sleeper()
    payloads = (_dispatcher_process(build=executed), _dispatcher_process(build=leased))
    try:
        _lease(build=leased, pid=live.pid)
        _lease(build=abandoned, pid=_reaped_pid())
        before = _snapshot(roots=(home, catalog, bundled))

        exit_code = dispatcher.main(argv=["sandbox-images", "--factory", _FACTORY, "--json"])
        payload = json.loads(capsys.readouterr().out)
        after = _snapshot(roots=(home, catalog, bundled))
    finally:
        _stopped(processes=iter((live, *payloads)))

    assert exit_code == 0
    assert after == before
    assert payload == [
        {
            "repository": str(catalog),
            "source": "catalog_environment",
            "environment_id": "livespec-ci-hp",
            "image": None,
            "path": None,
            "build": None,
            "variant": None,
        },
        {
            "repository": str(bundled),
            "source": "named_variant",
            "environment_id": None,
            "image": "ghcr.io/example/sandbox:fast",
            "path": str(bundled / ".fabro" / "workflows" / "fast" / "workflow.toml"),
            "build": None,
            "variant": "fast",
        },
        {
            "repository": str(bundled),
            "source": "bundled_run_config",
            "environment_id": None,
            "image": "ghcr.io/example/sandbox:registered",
            "path": str(registered.joinpath(*_RESERVED)),
            "build": "registered",
            "variant": None,
        },
        {
            "repository": str(bundled),
            "source": "bundled_run_config",
            "environment_id": None,
            "image": "ghcr.io/example/sandbox:leased",
            "path": str(leased.joinpath(*_RESERVED)),
            "build": "leased",
            "variant": None,
        },
        {
            "repository": str(bundled),
            "source": "bundled_run_config",
            "environment_id": None,
            "image": "ghcr.io/example/sandbox:executed",
            "path": str(executed.joinpath(*_RESERVED)),
            "build": "executed",
            "variant": None,
        },
    ]


def test_scenario212_an_undeclared_factory_and_an_unreadable_source_report_together(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The undeclared report alone exits zero; one unreadable source makes it non-zero."""
    home = tmp_path / "home"
    (home / ".claude" / "plugins").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("LIVESPEC_FABRO_SANDBOX_IMAGE", raising=False)
    undeclared = tmp_path / "undeclared-repo"
    _write_config(repo=undeclared, dispatcher_block={"factories": {"petri": {}}})
    unreadable = tmp_path / "unreadable-repo"
    unreadable.mkdir()
    _ = (unreadable / _CONFIG).write_text(
        '{"livespec-orchestrator-beads-fabro": ', encoding="utf-8"
    )

    undeclared_only = dispatcher.main(
        argv=["sandbox-images", "--factory", _FACTORY, "--repo", str(undeclared), "--json"]
    )
    undeclared_payload = json.loads(capsys.readouterr().out)
    with_unreadable = dispatcher.main(
        argv=[
            "sandbox-images",
            "--factory",
            _FACTORY,
            "--repo",
            str(undeclared),
            "--repo",
            str(unreadable),
            "--json",
        ]
    )
    both_payload = json.loads(capsys.readouterr().out)

    assert (undeclared_only, with_unreadable) == (0, 1)
    assert [entry["source"] for entry in undeclared_payload] == ["factory_undeclared"]
    assert [entry["source"] for entry in both_payload] == ["factory_undeclared", "unreadable"]
    assert both_payload[1]["path"] == str(unreadable / _CONFIG)
