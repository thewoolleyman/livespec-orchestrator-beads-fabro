"""An unreadable source is reported as one, and never truncates the enumeration.

The other half of `bd-ib-nqmltq`'s unreadable-source assertion — the resolver's
half. The command's non-zero exit is asserted where the exit code is decided,
one layer up; what is asserted here is that the entry whose dependency failed
says so, names the path that failed, and leaves every sibling entry standing.

A read failure is produced by INVALID UTF-8 rather than by a mode bit, because
this suite runs as root in the factory sandbox and root bypasses permission
bits — a `chmod 000` fixture would read successfully and the case would pass
against an implementation with no read-failure arm at all.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands import _dispatcher_sandbox_images
from livespec_orchestrator_beads_fabro.commands._dispatcher_sandbox_image_source import (
    COMMITTED_RUN_CONFIG_SOURCE,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_sandbox_images import (
    BUNDLED_RUN_CONFIG_SOURCE,
    NAMED_VARIANT_SOURCE,
    BuildRoot,
    SandboxImageEntry,
    sandbox_images,
)

# Spelled as a LITERAL and bound to the exported name by the test below, because
# this module's Red predates the constant: a top-level import of a name that does
# not exist yet dies at collection, which proves only that the name is absent.
UNREADABLE_SOURCE = "unreadable"

_FACTORY = "hp"
_SANDBOX_IMAGE_ENV = "LIVESPEC_FABRO_SANDBOX_IMAGE"
_CONFIG = ".livespec.jsonc"
_RESERVED = (".fabro", "workflows", "implement-work-item", "workflow.toml")
_NOT_UTF8 = b"\xff\xfe[run.environment]\n"
_NOT_TOML = "[run.environment\nid = broken\n"


def _write_workflow(*, path: Path, image: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(
        '[run.environment]\nid = "livespec-ci"\n'
        '\n[environments.livespec-ci]\nprovider = "docker"\n'
        f'\n[environments.livespec-ci.image]\ndocker = "{image}"\n',
        encoding="utf-8",
    )


def _write_raw(*, path: Path, text: str | None = None, data: bytes | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if data is not None:
        _ = path.write_bytes(data)
        return
    _ = path.write_text(text if text is not None else "", encoding="utf-8")


def _write_config(*, repo: Path, dispatcher: dict[str, object]) -> None:
    _ = (repo / _CONFIG).write_text(
        json.dumps({"livespec-orchestrator-beads-fabro": {"dispatcher": dispatcher}}),
        encoding="utf-8",
    )


def _repo(*, tmp_path: Path, name: str) -> Path:
    repo = tmp_path / name
    repo.mkdir(parents=True, exist_ok=True)
    return repo


def test_the_unreadable_source_is_exported_under_the_name_this_module_asserts() -> None:
    """The literal above IS the module's exported constant, not a private spelling."""
    exported = getattr(_dispatcher_sandbox_images, "UNREADABLE_SOURCE", None)
    assert exported == UNREADABLE_SOURCE


def test_a_repository_config_that_cannot_be_parsed_is_one_unreadable_entry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A `.livespec.jsonc` that does not parse names itself and resolves nothing else."""
    monkeypatch.delenv(_SANDBOX_IMAGE_ENV, raising=False)
    repo = _repo(tmp_path=tmp_path, name="unparseable-config")
    _write_raw(path=repo / _CONFIG, text='{"livespec-orchestrator-beads-fabro": ')

    entries = sandbox_images(factory=_FACTORY, repo=repo, builds=())

    assert entries == (
        SandboxImageEntry(repository=repo, source=UNREADABLE_SOURCE, path=repo / _CONFIG),
    )


def test_a_repository_config_that_cannot_be_read_is_one_unreadable_entry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Bytes that are not UTF-8 are a read failure, not an absent configuration."""
    monkeypatch.delenv(_SANDBOX_IMAGE_ENV, raising=False)
    repo = _repo(tmp_path=tmp_path, name="unreadable-config")
    _write_raw(path=repo / _CONFIG, data=_NOT_UTF8)

    entries = sandbox_images(factory=_FACTORY, repo=repo, builds=())

    assert entries == (
        SandboxImageEntry(repository=repo, source=UNREADABLE_SOURCE, path=repo / _CONFIG),
    )


def test_an_unreadable_named_variant_keeps_every_other_entry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One variant's failed read is one unreadable entry beside intact siblings.

    The reserved workflow this fixture also commits is one of those siblings,
    and it stands with no build executing: the committed answer is the
    target's own file, so it does not depend on the build set.
    """
    monkeypatch.delenv(_SANDBOX_IMAGE_ENV, raising=False)
    repo = _repo(tmp_path=tmp_path, name="variant-unreadable")
    _write_config(
        repo=repo,
        dispatcher={
            "factories": {_FACTORY: {}},
            "workflows": {"broken": ".fabro/workflows/broken", "sound": ".fabro/workflows/sound"},
        },
    )
    broken = repo / ".fabro" / "workflows" / "broken" / "workflow.toml"
    sound = repo / ".fabro" / "workflows" / "sound" / "workflow.toml"
    _write_raw(path=broken, data=_NOT_UTF8)
    _write_workflow(path=sound, image="ghcr.io/example/sandbox:sound")
    _write_workflow(path=repo.joinpath(*_RESERVED), image="ghcr.io/example/sandbox:reserved")

    entries = sandbox_images(factory=_FACTORY, repo=repo, builds=())

    assert entries == (
        SandboxImageEntry(repository=repo, source=UNREADABLE_SOURCE, variant="broken", path=broken),
        SandboxImageEntry(
            repository=repo,
            source=NAMED_VARIANT_SOURCE,
            variant="sound",
            image="ghcr.io/example/sandbox:sound",
            path=sound,
        ),
        SandboxImageEntry(
            repository=repo,
            source=COMMITTED_RUN_CONFIG_SOURCE,
            image="ghcr.io/example/sandbox:reserved",
            path=repo.joinpath(*_RESERVED),
        ),
    )


def test_a_committed_workflow_that_cannot_be_parsed_is_reported_unreadable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A target-local run config that is not TOML is unreadable, not image-less."""
    monkeypatch.delenv(_SANDBOX_IMAGE_ENV, raising=False)
    repo = _repo(tmp_path=tmp_path, name="committed-unparseable")
    _write_config(repo=repo, dispatcher={"factories": {_FACTORY: {}}})
    reserved = repo.joinpath(*_RESERVED)
    _write_raw(path=reserved, text=_NOT_TOML)
    build_root = tmp_path / "build-one"
    _write_workflow(path=build_root.joinpath(*_RESERVED), image="ghcr.io/example/sandbox:bundled")

    entries = sandbox_images(
        factory=_FACTORY,
        repo=repo,
        builds=(BuildRoot(identity="build-one", root=build_root),),
    )

    assert entries == (SandboxImageEntry(repository=repo, source=UNREADABLE_SOURCE, path=reserved),)


def test_an_unparseable_bundled_workflow_keeps_the_other_builds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One build's broken bundle is one unreadable entry naming that build's path."""
    monkeypatch.delenv(_SANDBOX_IMAGE_ENV, raising=False)
    repo = _repo(tmp_path=tmp_path, name="bundled-unparseable")
    _write_config(repo=repo, dispatcher={"factories": {_FACTORY: {}}})
    broken_root = tmp_path / "broken-build"
    sound_root = tmp_path / "sound-build"
    _write_raw(path=broken_root.joinpath(*_RESERVED), text=_NOT_TOML)
    _write_workflow(path=sound_root.joinpath(*_RESERVED), image="ghcr.io/example/sandbox:sound")

    entries = sandbox_images(
        factory=_FACTORY,
        repo=repo,
        builds=(
            BuildRoot(identity="broken-build", root=broken_root),
            BuildRoot(identity="sound-build", root=sound_root),
        ),
    )

    assert entries == (
        SandboxImageEntry(
            repository=repo,
            source=UNREADABLE_SOURCE,
            build="broken-build",
            path=broken_root.joinpath(*_RESERVED),
        ),
        SandboxImageEntry(
            repository=repo,
            source=BUNDLED_RUN_CONFIG_SOURCE,
            build="sound-build",
            image="ghcr.io/example/sandbox:sound",
            path=sound_root.joinpath(*_RESERVED),
        ),
    )


def test_a_readable_workflow_declaring_no_environment_reports_no_image(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A parseable run config that pins nothing is image-less, never unreadable."""
    monkeypatch.delenv(_SANDBOX_IMAGE_ENV, raising=False)
    repo = _repo(tmp_path=tmp_path, name="no-environment")
    _write_config(repo=repo, dispatcher={"factories": {_FACTORY: {}}})
    reserved = repo.joinpath(*_RESERVED)
    _write_raw(path=reserved, text='[workflow]\ngraph = "workflow.fabro"\n')

    entries = sandbox_images(
        factory=_FACTORY,
        repo=repo,
        builds=(BuildRoot(identity="any-build", root=tmp_path / "any-build"),),
    )

    assert entries == (
        SandboxImageEntry(
            repository=repo, source=COMMITTED_RUN_CONFIG_SOURCE, image=None, path=reserved
        ),
    )
