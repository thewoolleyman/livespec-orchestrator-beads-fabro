"""Scenario 201 — the committed clock-fired work-supply units, launcher and installer.

Governed by the clock-fired work-supply clause of `SPECIFICATION/contracts.md`
and by Scenario 201 of `SPECIFICATION/scenarios.md` — cited at FILE level,
because a heading-level citation rots the moment the heading is reworded; the
exact heading each surface binds to is recorded once, in
`tests/heading-coverage.json`.

Integration tier, as a `scenarios.md` binding requires. The seam exercised here
is not the ledger's: it is the SHIPPED ARTIFACTS an operator installs — the real
`install.sh` renders real units into a fixture unit directory, and the real
`work-supply-pass.sh` resolves a real plugin registry and assembles a real
drain argv. Nothing under test is mocked; what stands in are the host's two
outside edges, a stub credential wrapper and a recording runner.

`systemd-analyze verify` is deliberately NOT used, for the reason the
`reconcile-runs` sibling records: the committed units are TEXT templates
carrying `@PLACEHOLDER@` tokens, so they are not valid units until `install.sh`
renders them, and a verifier run against the template would report the
placeholders rather than anything about the unit's meaning.

The launcher is exercised through a RECORDING RUNNER rather than through real
`systemd-run`: the thing under test is the argv a firing assembles — which
build it resolves, which verb it runs, and what it deliberately omits — and a
stub records that argv exactly while a real transient unit would not be
readable from a test at all.

One sub-scenario is NOT here. "A firing starts one unattended drain pass for
its tenant" has a live half — a firing that actually dispatches on a host with
free slots and a usable credential — which is the item's `host_captured`
assertion and is proved on the dispatching host, not from this suite.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SERVICES_DIR = _REPO_ROOT / "orchestrator-image" / "services"
_SERVICE_DIR = _SERVICES_DIR / "work-supply"
_SERVICE = _SERVICE_DIR / "work-supply@.service"
_TIMER = _SERVICE_DIR / "work-supply@.timer"
_LAUNCHER = _SERVICE_DIR / "work-supply-pass.sh"
_INSTALL = _SERVICE_DIR / "install.sh"
_README = _SERVICE_DIR / "README.md"

_ENV_WRAPPER = "/usr/local/bin/with-livespec-env.sh"
_PLUGIN_NAME = "livespec-orchestrator-beads-fabro"
_DEFAULT_INTERVAL = "30min"
_MINIMUM_INTERVAL = "10min"

# Every environment name the committed service hands its launcher through the
# per-instance `EnvironmentFile`. Named here so a rename cannot pass by leaving
# one surface reading a variable the other stopped writing.
_REPO_ENV = "LIVESPEC_WORK_SUPPLY_REPO"
_BUDGET_ENV = "LIVESPEC_WORK_SUPPLY_BUDGET"
_WRAPPER_ENV = "LIVESPEC_WORK_SUPPLY_ENV_WRAPPER"

# Every setting with which systemd will accept a `[Timer]`. The committed timer
# template must declare NONE of them, so that an instance whose per-instance
# drop-in never landed fails loudly at load time.
_TIMER_VALUE_SETTINGS = frozenset(
    {
        "OnActiveSec",
        "OnBootSec",
        "OnStartupSec",
        "OnUnitActiveSec",
        "OnUnitInactiveSec",
        "OnCalendar",
    }
)


# ---------------------------------------------------------------------------
# Assertion 1 — the units ship beside `reconcile-runs`, and a firing runs the
# unattended drain: `loop --repo <tenant> --budget <n>` with NO `--item`.
# ---------------------------------------------------------------------------


def test_the_work_supply_units_ship_beside_the_reconcile_runs_units() -> None:
    """One services tree holds both host timers, so an operator finds them together."""
    assert (_SERVICES_DIR / "reconcile-runs" / "reconcile-runs.service").is_file()
    assert _SERVICE.is_file()
    assert _TIMER.is_file()
    assert _LAUNCHER.is_file()
    assert _INSTALL.is_file()
    assert _README.is_file()
    assert os.access(_LAUNCHER, os.X_OK)
    assert os.access(_INSTALL, os.X_OK)


def test_the_service_is_a_short_lived_oneshot_whose_exec_start_is_the_launcher() -> None:
    """The unit must not run the drain itself — see the overlap case below.

    A `Type=oneshot` whose ExecStart BLOCKS for the whole pass is never
    restarted while it is still active, so the timer would skip every firing
    for hours. The unit therefore runs the launcher, which detaches the pass.
    """
    service = _SERVICE.read_text(encoding="utf-8")

    assert "Type=oneshot" in service
    assert "EnvironmentFile=@INSTANCE_ENV_DIR@/%i.env" in service
    exec_start = _exec_start(unit=_SERVICE)
    assert exec_start == "ExecStart=@LAUNCHER@ --instance %i"
    # The wrapper is invoked by the DETACHED pass, never by this unit: a
    # wrapped launcher would make the pass's own wrapper call a NESTED one,
    # which is the credential-cache poisoning trap recorded in AGENTS.md.
    assert _ENV_WRAPPER not in service


def test_a_firing_runs_the_unattended_drain_for_its_tenant_with_a_budget(tmp_path: Path) -> None:
    """`loop --repo <tenant> --budget <n>`, through the wrapper, with NO `--item`."""
    fixture = _fixture(tmp_path=tmp_path)

    completed = _fire(fixture=fixture)

    assert completed.returncode == 0, completed.stderr
    argv = _recorded_argv(fixture=fixture)
    assert fixture["wrapper"] in argv
    assert argv[argv.index(fixture["wrapper"]) + 1] == "--"
    dispatcher = str(Path(fixture["build_a"]) / "scripts" / "bin" / "dispatcher.py")
    assert dispatcher in argv
    assert argv[argv.index(dispatcher) + 1] == "loop"
    assert argv[argv.index("--repo") + 1] == fixture["repo"]
    assert argv[argv.index("--budget") + 1] == "3"
    # The selection flag the clause forbids: with `--item` the pass would be a
    # hand-picked dispatch rather than a drain of the ranked queue.
    assert "--item" not in argv
    # Nothing in the firing relaxes an admission condition: the pass carries
    # only the governed drain flags plus attribution and reporting.
    assert "--dry-run" not in argv
    assert argv[argv.index("--invoker") + 1] == "timer:work-supply"


# ---------------------------------------------------------------------------
# Assertion 2 — one timer instance per tenant, the operator's interval, and
# the two installer refusals.
# ---------------------------------------------------------------------------


def test_the_installer_installs_one_timer_instance_per_tenant_repository(tmp_path: Path) -> None:
    """Two tenants share the template units and get their own instance artifacts."""
    first = _install(tmp_path=tmp_path, tenant="alpha", interval="30min")
    second = _install(tmp_path=tmp_path, tenant="beta", interval="45min")

    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
    units = tmp_path / "units"
    assert (units / "work-supply@.service").is_file()
    assert (units / "work-supply@.timer").is_file()
    assert _interval_of(tmp_path=tmp_path, tenant="alpha") == "30min"
    assert _interval_of(tmp_path=tmp_path, tenant="beta") == "45min"
    alpha = _instance_env(tmp_path=tmp_path, tenant="alpha")
    beta = _instance_env(tmp_path=tmp_path, tenant="beta")
    assert alpha[_REPO_ENV] == str(tmp_path / "alpha")
    assert beta[_REPO_ENV] == str(tmp_path / "beta")
    assert alpha[_BUDGET_ENV] == beta[_BUDGET_ENV]


def test_the_installer_renders_every_placeholder_and_enables_the_named_instance(
    tmp_path: Path,
) -> None:
    completed = _install(tmp_path=tmp_path, tenant="alpha", interval="30min")

    assert completed.returncode == 0, completed.stderr
    rendered = tmp_path / "units" / "work-supply@.service"
    text = rendered.read_text(encoding="utf-8")
    # An unrendered token makes systemd refuse the unit at load time, long
    # after the operator has walked away.
    assert "@" not in _exec_start(unit=rendered)
    assert "@INSTANCE_ENV_DIR@" not in text
    assert str(_LAUNCHER) in text
    assert "work-supply@alpha.timer" in completed.stdout


def test_the_installer_takes_each_instances_firing_interval_from_the_operator(
    tmp_path: Path,
) -> None:
    completed = _install(tmp_path=tmp_path, tenant="alpha", interval="2h")

    assert completed.returncode == 0, completed.stderr
    assert _interval_of(tmp_path=tmp_path, tenant="alpha") == "2h"
    # The template declares no timer VALUE setting of its own, so an instance
    # installed without its drop-in is REFUSED by systemd ("Timer unit lacks
    # value setting") rather than silently firing once after boot and never
    # again.
    declared = set(_settings(text=_TIMER.read_text(encoding="utf-8")))
    assert declared.isdisjoint(_TIMER_VALUE_SETTINGS)


def test_the_installer_refuses_an_instance_whose_env_wrapper_is_not_executable(
    tmp_path: Path,
) -> None:
    absent = tmp_path / "absent-wrapper.sh"

    completed = _install(
        tmp_path=tmp_path, tenant="alpha", interval="30min", env_wrapper=str(absent)
    )

    assert completed.returncode == 78
    assert "alpha" in completed.stderr
    assert str(absent) in completed.stderr
    assert "BEADS_DOLT_PASSWORD" in completed.stderr
    assert not (tmp_path / "units" / "work-supply@.service").exists()
    assert not _drop_in(tmp_path=tmp_path, tenant="alpha").exists()


def test_the_installer_refuses_an_interval_below_the_documented_minimum(tmp_path: Path) -> None:
    completed = _install(tmp_path=tmp_path, tenant="alpha", interval="90s")

    assert completed.returncode == 78
    assert "alpha" in completed.stderr
    assert "90s" in completed.stderr
    assert _MINIMUM_INTERVAL in completed.stderr
    assert not _drop_in(tmp_path=tmp_path, tenant="alpha").exists()


def test_the_installer_refuses_an_interval_it_cannot_measure(tmp_path: Path) -> None:
    """An unparseable span must refuse, never pass the minimum by being unreadable."""
    completed = _install(tmp_path=tmp_path, tenant="alpha", interval="soon")

    assert completed.returncode == 78
    assert "soon" in completed.stderr
    assert _MINIMUM_INTERVAL in completed.stderr


def test_the_installer_and_the_readme_state_the_default_interval() -> None:
    assert _DEFAULT_INTERVAL in _INSTALL.read_text(encoding="utf-8")
    readme = _README.read_text(encoding="utf-8")
    assert _DEFAULT_INTERVAL in readme
    assert _MINIMUM_INTERVAL in readme


def test_the_installer_refuses_without_a_repo(tmp_path: Path) -> None:
    completed = _run(argv=[str(_INSTALL)], tmp_path=tmp_path, env_wrapper=str(tmp_path))

    assert completed.returncode == 64
    assert "--repo <tenant-checkout> is required" in completed.stderr


def test_the_installer_refuses_a_repo_path_that_is_not_a_directory(tmp_path: Path) -> None:
    completed = _run(
        argv=[str(_INSTALL), "--repo", str(tmp_path / "nope"), "--interval", "30min"],
        tmp_path=tmp_path,
        env_wrapper=str(tmp_path),
    )

    assert completed.returncode == 78
    assert "is not a directory" in completed.stderr


# ---------------------------------------------------------------------------
# Assertion 3 — the build is resolved from the tenant's registered install AT
# THE MOMENT OF FIRING, and a tenant with no registered install refuses.
# ---------------------------------------------------------------------------


def test_a_newly_registered_build_is_executed_by_the_next_firing(tmp_path: Path) -> None:
    """The release moves the registry; the unit is never reinstalled."""
    fixture = _fixture(tmp_path=tmp_path)

    first = _fire(fixture=fixture)
    _write_registry(fixture=fixture, install_path=fixture["build_b"])
    second = _fire(fixture=fixture)

    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
    recorded = _recorded_lines(fixture=fixture)
    assert str(Path(fixture["build_a"]) / "scripts" / "bin" / "dispatcher.py") in recorded[0]
    assert str(Path(fixture["build_b"]) / "scripts" / "bin" / "dispatcher.py") in recorded[1]


def test_a_firing_with_no_registered_install_refuses_naming_the_tenant(tmp_path: Path) -> None:
    """Refuse loudly rather than guess: a guessed path is the stale-build trap."""
    fixture = _fixture(tmp_path=tmp_path)
    _write_registry(fixture=fixture, install_path=None)

    completed = _fire(fixture=fixture)

    assert completed.returncode == 78
    assert fixture["repo"] in completed.stderr
    assert "no registered" in completed.stderr.lower()
    assert not Path(fixture["record"]).exists()


def test_a_firing_whose_registry_cannot_be_read_refuses(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path=tmp_path)
    Path(fixture["registry"]).unlink()

    completed = _fire(fixture=fixture)

    assert completed.returncode == 78
    assert fixture["repo"] in completed.stderr
    assert not Path(fixture["record"]).exists()


def test_a_firing_whose_registered_build_has_no_dispatcher_refuses(tmp_path: Path) -> None:
    """A registered install missing its entry point is named, never executed."""
    fixture = _fixture(tmp_path=tmp_path)
    (Path(fixture["build_a"]) / "scripts" / "bin" / "dispatcher.py").unlink()

    completed = _fire(fixture=fixture)

    assert completed.returncode == 78
    assert fixture["build_a"] in completed.stderr
    assert not Path(fixture["record"]).exists()


def test_a_firing_with_no_tenant_or_budget_in_its_environment_refuses(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path=tmp_path)

    missing_repo = _fire(fixture=fixture, overrides={_REPO_ENV: ""})
    missing_budget = _fire(fixture=fixture, overrides={_BUDGET_ENV: ""})
    missing_wrapper = _fire(fixture=fixture, overrides={_WRAPPER_ENV: ""})

    assert missing_repo.returncode == 78
    assert _REPO_ENV in missing_repo.stderr
    assert missing_budget.returncode == 78
    assert _BUDGET_ENV in missing_budget.stderr
    assert missing_wrapper.returncode == 78
    assert _WRAPPER_ENV in missing_wrapper.stderr
    assert not Path(fixture["record"]).exists()


# ---------------------------------------------------------------------------
# Assertion 4 — a pass still in progress does not stop the next firing.
# ---------------------------------------------------------------------------


def test_a_pass_in_progress_does_not_stop_the_next_firing(tmp_path: Path) -> None:
    """The launcher hands the pass to its OWN transient unit and returns.

    Three things together are what make the next tick land: the pass runs in
    an independently-named transient unit (so two passes can be alive at
    once), the launcher does NOT wait on it, and the timer measures its
    interval from the service's last activation — which, because the service
    is the launcher rather than the drain, is seconds after each firing.
    """
    fixture = _fixture(tmp_path=tmp_path)

    first = _fire(fixture=fixture)
    second = _fire(fixture=fixture)

    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
    recorded = _recorded_lines(fixture=fixture)
    units = [_flag_value(line=line, flag="--unit") for line in recorded]
    assert units[0] != units[1]
    assert all(unit.startswith("work-supply-pass-") for unit in units)
    # `--wait` would block the oneshot for the whole pass, which is exactly
    # the overlap this assertion forbids; `--collect` reaps the finished unit
    # so a long-running host does not accumulate transient unit state.
    assert all("--wait" not in line.split("\t") for line in recorded)
    assert all("--collect" in line.split("\t") for line in recorded)
    timer = _settings(text=_TIMER.read_text(encoding="utf-8"))
    assert timer["Unit"] == "work-supply@%i.service"
    assert timer["WantedBy"] == "timers.target"
    # `OnUnitActiveSec` and not `OnCalendar`: the interval that matters is the
    # gap since the LAST firing, so a firing delayed by anything still leaves
    # a full interval before the next, rather than two landing back to back.
    installed = _install(tmp_path=tmp_path, tenant="alpha", interval="30min")
    assert installed.returncode == 0, installed.stderr
    drop_in = _settings(
        text=_drop_in(tmp_path=tmp_path, tenant="alpha").read_text(encoding="utf-8")
    )
    assert drop_in["OnUnitActiveSec"] == "30min"
    assert "OnCalendar" not in drop_in


# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------


def _fixture(*, tmp_path: Path) -> dict[str, str]:
    """A tenant checkout, two plugin builds, a registry naming the first, a runner."""
    repo = tmp_path / "tenant"
    repo.mkdir()
    wrapper = tmp_path / "with-livespec-env.sh"
    _ = wrapper.write_text('#!/bin/sh\nexec "$@"\n', encoding="utf-8")
    wrapper.chmod(0o755)
    record = tmp_path / "runner-argv.tsv"
    runner = tmp_path / "recording-runner.sh"
    _ = runner.write_text(
        '#!/bin/sh\nprintf "%s\\n" "$(printf "%s\\t" "$@")" >>"' + str(record) + '"\nexit 0\n',
        encoding="utf-8",
    )
    runner.chmod(0o755)
    fixture = {
        "repo": str(repo),
        "wrapper": str(wrapper),
        "runner": str(runner),
        "record": str(record),
        "registry": str(tmp_path / "installed_plugins.json"),
        "build_a": str(_build(root=tmp_path, name="build-a")),
        "build_b": str(_build(root=tmp_path, name="build-b")),
    }
    _write_registry(fixture=fixture, install_path=fixture["build_a"])
    return fixture


def _build(*, root: Path, name: str) -> Path:
    build = root / "cache" / name
    (build / "scripts" / "bin").mkdir(parents=True)
    _ = (build / "plugin.json").write_text('{"name": "x", "version": "0.0.0"}\n', encoding="utf-8")
    _ = (build / "scripts" / "bin" / "dispatcher.py").write_text("", encoding="utf-8")
    return build


def _write_registry(*, fixture: dict[str, str], install_path: str | None) -> None:
    entries = (
        f'[{{"projectPath": "{fixture["repo"]}", "installPath": "{install_path}"}}]'
        if install_path is not None
        else '[{"projectPath": "/somewhere/else", "installPath": "/nowhere"}]'
    )
    _ = Path(fixture["registry"]).write_text(
        '{"plugins": {"' + _PLUGIN_NAME + '@marketplace": ' + entries + "}}\n",
        encoding="utf-8",
    )


def _fire(
    *, fixture: dict[str, str], overrides: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    env = {
        **_child_env(),
        _REPO_ENV: fixture["repo"],
        _BUDGET_ENV: "3",
        _WRAPPER_ENV: fixture["wrapper"],
        "LIVESPEC_WORK_SUPPLY_PLUGIN_REGISTRY": fixture["registry"],
        "LIVESPEC_WORK_SUPPLY_RUNNER": fixture["runner"],
    }
    env.update(overrides or {})
    return subprocess.run(
        [str(_LAUNCHER), "--instance", "tenant"],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )


def _recorded_lines(*, fixture: dict[str, str]) -> list[str]:
    text = Path(fixture["record"]).read_text(encoding="utf-8")
    return [line for line in text.splitlines() if line]


def _recorded_argv(*, fixture: dict[str, str]) -> list[str]:
    lines = _recorded_lines(fixture=fixture)
    assert len(lines) == 1
    return [word for word in lines[0].split("\t") if word]


def _flag_value(*, line: str, flag: str) -> str:
    words = [word for word in line.split("\t") if word]
    return words[words.index(flag) + 1]


def _exec_start(*, unit: Path) -> str:
    lines = [
        line
        for line in unit.read_text(encoding="utf-8").splitlines()
        if line.startswith("ExecStart=")
    ]
    assert len(lines) == 1
    return lines[0]


def _drop_in(*, tmp_path: Path, tenant: str) -> Path:
    return tmp_path / "units" / f"work-supply@{tenant}.timer.d" / "interval.conf"


def _settings(*, text: str) -> dict[str, str]:
    """Every `Key=Value` SETTING line of a unit or environment file.

    Comments are excluded by POSITION rather than by content, so a template's
    own prose about `OnUnitActiveSec` is never mistaken for a declaration of
    one — which is the whole of the no-interval-in-the-template reading below.
    A key declared twice answers the last, as systemd itself does.
    """
    fields: dict[str, str] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if "=" in stripped and not stripped.startswith("#"):
            name, value = stripped.split("=", 1)
            fields[name] = value
    return fields


def _interval_of(*, tmp_path: Path, tenant: str) -> str:
    body = _drop_in(tmp_path=tmp_path, tenant=tenant).read_text(encoding="utf-8")
    return _settings(text=body)["OnUnitActiveSec"]


def _instance_env(*, tmp_path: Path, tenant: str) -> dict[str, str]:
    path = tmp_path / "instance-env" / f"{tenant}.env"
    return _settings(text=path.read_text(encoding="utf-8"))


def _install(
    *,
    tmp_path: Path,
    tenant: str,
    interval: str,
    env_wrapper: str | None = None,
) -> subprocess.CompletedProcess[str]:
    repo = tmp_path / tenant
    repo.mkdir(exist_ok=True)
    wrapper = env_wrapper
    if wrapper is None:
        resolved = tmp_path / "with-livespec-env.sh"
        _ = resolved.write_text('#!/bin/sh\nexec "$@"\n', encoding="utf-8")
        resolved.chmod(0o755)
        wrapper = str(resolved)
    return _run(
        argv=[str(_INSTALL), "--repo", str(repo), "--interval", interval],
        tmp_path=tmp_path,
        env_wrapper=wrapper,
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
            **_child_env(),
            "LIVESPEC_ENV_WRAPPER": env_wrapper,
            "UNIT_DIR": str(tmp_path / "units"),
            "INSTANCE_ENV_DIR": str(tmp_path / "instance-env"),
            "DRY_RUN": "1",
        },
    )


def _child_env() -> dict[str, str]:
    """`os.environ` with coverage's subprocess hooks scrubbed.

    These helpers spawn shell, and the launcher spawns a `python3` grandchild
    to read the plugin registry. A self-instrumenting grandchild writes
    `.coverage.*` files that race the concurrent coverage runs of the parallel
    check dispatcher, which is the flake the shared no-subprocess-spawn gate
    exists to prevent.
    """
    scrubbed = {
        name: value
        for name, value in os.environ.items()
        if not name.startswith("COV_CORE_") and name != "COVERAGE_PROCESS_START"
    }
    return scrubbed
