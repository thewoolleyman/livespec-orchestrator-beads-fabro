"""The `sandbox-images` subcommand: what it enumerates, prints and exits.

`bd-ib-nqmltq`'s command-level assertions — the one JSON array whose every
entry names its repository and its source, the two repository-discovery modes,
the successful undeclared-factory report, and the non-zero exit an unreadable
source earns while every other entry is still printed.

Every repository fixture here resolves its image through the CATALOG or the
CONFIGURED arm, so none of them depends on the host's executing-build set. The
real `/proc` is read for build discovery, so a factory host that happened to be
running a Dispatcher would otherwise change how many entries a workflow-arm
repository contributes and the assertion would be about this host rather than
about the command.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands import dispatcher
from livespec_orchestrator_beads_fabro.commands._dispatcher_sandbox_image_source import (
    CATALOG_ENVIRONMENT_SOURCE,
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
