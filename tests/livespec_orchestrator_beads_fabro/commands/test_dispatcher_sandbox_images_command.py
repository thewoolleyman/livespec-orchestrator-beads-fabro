"""The `sandbox-images` subcommand: what it enumerates, prints and exits.

`bd-ib-nqmltq`'s command-level assertions — the one JSON array whose every
entry names its repository and its source, the two repository-discovery modes,
the successful undeclared-factory report, and the non-zero exit an unreadable
source earns while every other entry is still printed.

Nearly every repository fixture here resolves its image through the CATALOG or
the CONFIGURED arm, so none of those depends on the host's executing-build set.
That matters because build discovery reads the real `/proc`, which is host-wide
by design: any process whose argv names a `scripts/bin/dispatcher.py` is a build
a dispatch could execute from, so a factory host running a Dispatcher — or, under
`pytest -n 18`, a sibling worker's `tests/bin/test_payload*` fixture, which
spawns exactly such a child — contributes a perfectly valid foreign build.

THE ONE CASE THAT DOES REACH THE BUNDLED ARM therefore asserts its registered
build's entry is PRESENT rather than that it is the only entry, because
"`--repo` scopes repositories, not builds" is a claim about that entry and never
a claim about how many builds the host is executing. Measured 2026-10-21 under
`pytest -n 18`, the exact-array form reds on a correct reading, while the
`--repo` scope it exists to establish is still asserted exactly: every reported
entry belongs to the named repository, and the registered project is absent.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands import _dispatcher_sandbox_images, dispatcher
from livespec_orchestrator_beads_fabro.commands._dispatcher_sandbox_image_source import (
    CATALOG_ENVIRONMENT_SOURCE,
    SandboxImageSource,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_sandbox_images import (
    FACTORY_UNDECLARED_SOURCE,
    UNREADABLE_SOURCE,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_sandbox_images_command import (
    run_sandbox_images_command,
)

_FACTORY = "hp"
_SANDBOX_IMAGE_ENV = "LIVESPEC_FABRO_SANDBOX_IMAGE"
_CONFIG = ".livespec.jsonc"
_PLUGIN_KEY = "livespec-orchestrator-beads-fabro@livespec-orchestrator-beads-fabro"
_OTHER_PLUGIN_KEY = "some-other-plugin@its-own-marketplace"
_REGISTRY = (".claude", "plugins", "installed_plugins.json")


def _args(*, repos: list[str] | None, as_json: bool) -> argparse.Namespace:
    return argparse.Namespace(factory=_FACTORY, repos=repos, as_json=as_json)


def _catalog_repo(*, tmp_path: Path, name: str) -> Path:
    repo = tmp_path / name
    repo.mkdir(parents=True, exist_ok=True)
    _ = (repo / _CONFIG).write_text(
        json.dumps(
            {
                "livespec-orchestrator-beads-fabro": {
                    "dispatcher": {"factories": {_FACTORY: {"environment": f"env-{name}"}}}
                }
            }
        ),
        encoding="utf-8",
    )
    return repo


def _unreadable_repo(*, tmp_path: Path, name: str) -> Path:
    repo = tmp_path / name
    repo.mkdir(parents=True, exist_ok=True)
    _ = (repo / _CONFIG).write_text('{"livespec-orchestrator-beads-fabro": ', encoding="utf-8")
    return repo


def _undeclared_repo(*, tmp_path: Path, name: str) -> Path:
    repo = tmp_path / name
    repo.mkdir(parents=True, exist_ok=True)
    _ = (repo / _CONFIG).write_text(
        json.dumps(
            {"livespec-orchestrator-beads-fabro": {"dispatcher": {"factories": {"petri": {}}}}}
        ),
        encoding="utf-8",
    )
    return repo


def _home_with_registry(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, plugins: dict[str, object]
) -> Path:
    home = tmp_path / "home"
    registry = home.joinpath(*_REGISTRY)
    registry.parent.mkdir(parents=True, exist_ok=True)
    _ = registry.write_text(json.dumps({"plugins": plugins}), encoding="utf-8")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv(_SANDBOX_IMAGE_ENV, raising=False)
    return home


def _records(*, repos: tuple[Path, ...], install: Path) -> list[dict[str, str]]:
    return [{"projectPath": str(repo), "installPath": str(install)} for repo in repos]


def _unreadable_exit(*, payload: list[dict[str, str | None]]) -> int:
    """The exit code the reported array implies — the clause's own rule, as read.

    Asserted in this form on the one case whose array is host-wide (see the
    module docstring): the rule is that an unreadable source moves the exit code
    and nothing else, and a build that exited zero regardless, or non-zero
    regardless, fails it. The concrete 0-and-non-zero readings are asserted by
    the sibling cases, whose arrays are the fixture's alone.
    """
    return 1 if any(entry["source"] == UNREADABLE_SOURCE for entry in payload) else 0


def test_the_json_output_is_one_array_whose_every_entry_names_repository_and_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """One array, every object labelled, even when one of the entries is unreadable."""
    sound = _catalog_repo(tmp_path=tmp_path, name="sound")
    broken = _unreadable_repo(tmp_path=tmp_path, name="broken")
    _ = _home_with_registry(tmp_path=tmp_path, monkeypatch=monkeypatch, plugins={})

    exit_code = dispatcher.main(
        argv=[
            "sandbox-images",
            "--factory",
            _FACTORY,
            "--repo",
            str(sound),
            "--repo",
            str(broken),
            "--json",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert exit_code != 0
    assert [(entry["repository"], entry["source"]) for entry in payload] == [
        (str(sound), CATALOG_ENVIRONMENT_SOURCE),
        (str(broken), UNREADABLE_SOURCE),
    ]
    assert payload[1]["path"] == str(broken / _CONFIG)


def test_without_repo_the_command_enumerates_this_plugins_registered_projects(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Default discovery is this plugin's own install records, not another plugin's."""
    first = _catalog_repo(tmp_path=tmp_path, name="first")
    second = _catalog_repo(tmp_path=tmp_path, name="second")
    third = _catalog_repo(tmp_path=tmp_path, name="third")
    install = tmp_path / "build"
    install.mkdir()
    _ = _home_with_registry(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        plugins={
            _PLUGIN_KEY: _records(repos=(first, second), install=install),
            _OTHER_PLUGIN_KEY: _records(repos=(third,), install=install),
        },
    )

    exit_code = run_sandbox_images_command(args=_args(repos=None, as_json=True))
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert [entry["repository"] for entry in payload] == [str(first), str(second)]


def test_explicit_repositories_replace_registry_discovery(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Named repositories are enumerated INSTEAD of the registered ones, not beside them."""
    registered = _catalog_repo(tmp_path=tmp_path, name="registered")
    named = _catalog_repo(tmp_path=tmp_path, name="named")
    install = tmp_path / "build"
    install.mkdir()
    _ = _home_with_registry(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        plugins={_PLUGIN_KEY: _records(repos=(registered,), install=install)},
    )

    exit_code = run_sandbox_images_command(args=_args(repos=[str(named)], as_json=True))
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert [entry["repository"] for entry in payload] == [str(named)]


def test_explicit_repositories_still_use_every_host_registered_build(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`--repo` scopes repositories, not the builds a dispatch can execute from."""
    named = tmp_path / "named"
    named.mkdir()
    _ = (named / _CONFIG).write_text(
        json.dumps(
            {"livespec-orchestrator-beads-fabro": {"dispatcher": {"factories": {_FACTORY: {}}}}}
        ),
        encoding="utf-8",
    )
    registered = _catalog_repo(tmp_path=tmp_path, name="registered")
    install = tmp_path / "build"
    workflow = install / ".fabro" / "workflows" / "implement-work-item" / "workflow.toml"
    workflow.parent.mkdir(parents=True)
    _ = workflow.write_text(
        "[run.environment]\n"
        'id = "livespec-ci"\n\n'
        "[environments.livespec-ci]\n"
        'provider = "docker"\n\n'
        "[environments.livespec-ci.image]\n"
        'docker = "ghcr.io/example/sandbox:registered"\n',
        encoding="utf-8",
    )
    _ = _home_with_registry(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        plugins={_PLUGIN_KEY: _records(repos=(registered,), install=install)},
    )

    exit_code = run_sandbox_images_command(args=_args(repos=[str(named)], as_json=True))
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == _unreadable_exit(payload=payload)
    assert {entry["repository"] for entry in payload} == {str(named)}
    assert {
        "repository": str(named),
        "source": "bundled_run_config",
        "environment_id": None,
        "image": "ghcr.io/example/sandbox:registered",
        "path": str(workflow),
        "build": "build",
        "variant": None,
    } in payload


def test_an_undeclared_factory_is_reported_and_exits_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`factory_undeclared` is a successful report, never a refusal."""
    repo = _undeclared_repo(tmp_path=tmp_path, name="undeclared")
    _ = _home_with_registry(tmp_path=tmp_path, monkeypatch=monkeypatch, plugins={})

    exit_code = run_sandbox_images_command(args=_args(repos=[str(repo)], as_json=True))
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert [entry["source"] for entry in payload] == [FACTORY_UNDECLARED_SOURCE]
    assert payload[0]["image"] is None


def test_the_commands_output_follows_the_dispatch_image_source_function(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Changing what `sandbox_image_source` returns changes THIS command's output identically.

    The resolver's own module asserts the same seam one layer down. This case is
    the clause's literal claim — that the COMMAND's output follows that function
    — and it is the one a parallel copy of the source ladder would defeat while
    leaving the resolver's unit assertion green.
    """
    repo = _catalog_repo(tmp_path=tmp_path, name="seam")
    _ = _home_with_registry(tmp_path=tmp_path, monkeypatch=monkeypatch, plugins={})

    def patched(
        *, factory_environment: str | None, configured_image: str | None
    ) -> SandboxImageSource:
        _ = (factory_environment, configured_image)
        return SandboxImageSource(
            source="patched_source",
            environment_id="patched-env",
            overlay_image="patched-image",
        )

    monkeypatch.setattr(_dispatcher_sandbox_images, "sandbox_image_source", patched)

    exit_code = run_sandbox_images_command(args=_args(repos=[str(repo)], as_json=True))
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload == [
        {
            "repository": str(repo),
            "source": "patched_source",
            "environment_id": "patched-env",
            "image": "patched-image",
            "path": None,
            "build": None,
            "variant": None,
        }
    ]


def test_the_human_rendering_names_every_entrys_repository_and_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Without `--json` each entry is one line carrying its source, repository and evidence."""
    repo = _catalog_repo(tmp_path=tmp_path, name="human")
    _ = _home_with_registry(tmp_path=tmp_path, monkeypatch=monkeypatch, plugins={})

    exit_code = run_sandbox_images_command(args=_args(repos=[str(repo)], as_json=False))
    printed = capsys.readouterr().out

    assert exit_code == 0
    assert printed.splitlines() == [f"{CATALOG_ENVIRONMENT_SOURCE}  {repo}  environment=env-human"]


def test_no_enumerated_repository_prints_an_empty_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """An empty registry enumerates nothing and says so in both renderings."""
    _ = _home_with_registry(tmp_path=tmp_path, monkeypatch=monkeypatch, plugins={})

    human = run_sandbox_images_command(args=_args(repos=None, as_json=False))
    human_output = capsys.readouterr().out
    as_json = run_sandbox_images_command(args=_args(repos=None, as_json=True))
    json_output = capsys.readouterr().out

    assert (human, as_json) == (0, 0)
    assert human_output == "(no sandbox-image entries)\n"
    assert json.loads(json_output) == []
