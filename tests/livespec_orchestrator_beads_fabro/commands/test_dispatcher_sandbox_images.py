"""One repository's sandbox-image entries, resolved through dispatch's own seams.

Each test here is one assertion of `bd-ib-nqmltq`'s Definition of Done over the
per-repository resolver: the undeclared-factory report, the catalog arm, the
configured-image arm and its environment-override precedence, the named-variant
entries, the committed reserved workflow, the per-build bundled pins, and the
requirement that the source is decided by the dispatch's own
`sandbox_image_source` rather than by a copy of its ladder.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands import _dispatcher_sandbox_images
from livespec_orchestrator_beads_fabro.commands._dispatcher_sandbox_image_source import (
    CATALOG_ENVIRONMENT_SOURCE,
    COMMITTED_RUN_CONFIG_SOURCE,
    CONFIGURED_IMAGE_SOURCE,
    SandboxImageSource,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_sandbox_images import (
    BUNDLED_RUN_CONFIG_SOURCE,
    FACTORY_UNDECLARED_SOURCE,
    NAMED_VARIANT_SOURCE,
    BuildRoot,
    SandboxImageEntry,
    sandbox_images,
)

_FACTORY = "hp"
_SANDBOX_IMAGE_ENV = "LIVESPEC_FABRO_SANDBOX_IMAGE"
_RESERVED = (".fabro", "workflows", "implement-work-item", "workflow.toml")


def _write_workflow(*, path: Path, image: str) -> None:
    """A minimal run config carrying the two tables the docker pin is read through."""
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(
        '[run.environment]\nid = "livespec-ci"\n'
        '\n[environments.livespec-ci]\nprovider = "docker"\n'
        f'\n[environments.livespec-ci.image]\ndocker = "{image}"\n',
        encoding="utf-8",
    )


def _write_config(*, repo: Path, dispatcher: dict[str, object]) -> None:
    _ = (repo / ".livespec.jsonc").write_text(
        json.dumps({"livespec-orchestrator-beads-fabro": {"dispatcher": dispatcher}}),
        encoding="utf-8",
    )


def _repo(*, tmp_path: Path, name: str) -> Path:
    repo = tmp_path / name
    repo.mkdir(parents=True, exist_ok=True)
    return repo


def _build(*, tmp_path: Path, name: str, image: str) -> BuildRoot:
    root = tmp_path / name
    _write_workflow(path=root.joinpath(*_RESERVED), image=image)
    return BuildRoot(identity=name, root=root)


def test_a_repository_not_declaring_the_factory_is_reported_undeclared(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An undeclared factory yields one `factory_undeclared` entry and no image."""
    monkeypatch.delenv(_SANDBOX_IMAGE_ENV, raising=False)
    repo = _repo(tmp_path=tmp_path, name="undeclared")
    _write_config(repo=repo, dispatcher={"factories": {"petri": {}}})

    entries = sandbox_images(factory=_FACTORY, repo=repo, builds=())

    assert entries == (SandboxImageEntry(repository=repo, source=FACTORY_UNDECLARED_SOURCE),)


def test_a_catalog_environment_entry_names_the_environment_and_no_image(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The catalog arm reports its environment id and withholds every image."""
    monkeypatch.delenv(_SANDBOX_IMAGE_ENV, raising=False)
    repo = _repo(tmp_path=tmp_path, name="catalog")
    _write_config(
        repo=repo,
        dispatcher={
            "factories": {_FACTORY: {"environment": "livespec-ci-hp"}},
            "fabro_sandbox_image": "ghcr.io/example/sandbox:configured",
        },
    )

    entries = sandbox_images(factory=_FACTORY, repo=repo, builds=())

    assert entries == (
        SandboxImageEntry(
            repository=repo,
            source=CATALOG_ENVIRONMENT_SOURCE,
            environment_id="livespec-ci-hp",
        ),
    )


def test_the_configured_image_resolver_applies_the_environment_override_first(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`LIVESPEC_FABRO_SANDBOX_IMAGE` outranks the committed key, as a dispatch resolves it."""
    repo = _repo(tmp_path=tmp_path, name="configured")
    _write_config(
        repo=repo,
        dispatcher={
            "factories": {_FACTORY: {}},
            "fabro_sandbox_image": "ghcr.io/example/sandbox:committed-key",
        },
    )
    _write_workflow(path=repo.joinpath(*_RESERVED), image="ghcr.io/example/sandbox:workflow")
    monkeypatch.setenv(_SANDBOX_IMAGE_ENV, "ghcr.io/example/sandbox:from-env")

    entries = sandbox_images(factory=_FACTORY, repo=repo, builds=())

    assert entries == (
        SandboxImageEntry(
            repository=repo,
            source=CONFIGURED_IMAGE_SOURCE,
            image="ghcr.io/example/sandbox:from-env",
        ),
    )


def test_each_declared_named_variant_reports_its_own_workflow_pin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every `dispatcher.workflows` entry contributes its own pin and path."""
    monkeypatch.delenv(_SANDBOX_IMAGE_ENV, raising=False)
    repo = _repo(tmp_path=tmp_path, name="variants")
    _write_config(
        repo=repo,
        dispatcher={
            "factories": {_FACTORY: {}},
            "workflows": {"fast": ".fabro/workflows/fast", "slow": ".fabro/workflows/slow"},
        },
    )
    fast = repo / ".fabro" / "workflows" / "fast" / "workflow.toml"
    slow = repo / ".fabro" / "workflows" / "slow" / "workflow.toml"
    _write_workflow(path=fast, image="ghcr.io/example/sandbox:fast")
    _write_workflow(path=slow, image="ghcr.io/example/sandbox:slow")
    _write_workflow(path=repo.joinpath(*_RESERVED), image="ghcr.io/example/sandbox:reserved")

    entries = sandbox_images(
        factory=_FACTORY,
        repo=repo,
        builds=(_build(tmp_path=tmp_path, name="v1", image="ghcr.io/example/sandbox:bundled"),),
    )

    assert entries[:2] == (
        SandboxImageEntry(
            repository=repo,
            source=NAMED_VARIANT_SOURCE,
            variant="fast",
            image="ghcr.io/example/sandbox:fast",
            path=fast,
        ),
        SandboxImageEntry(
            repository=repo,
            source=NAMED_VARIANT_SOURCE,
            variant="slow",
            image="ghcr.io/example/sandbox:slow",
            path=slow,
        ),
    )


def test_a_committed_reserved_workflow_reports_its_own_pin_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A target-local reserved workflow is one entry, whatever the build count."""
    monkeypatch.delenv(_SANDBOX_IMAGE_ENV, raising=False)
    repo = _repo(tmp_path=tmp_path, name="committed")
    _write_config(repo=repo, dispatcher={"factories": {_FACTORY: {}}})
    _write_workflow(path=repo.joinpath(*_RESERVED), image="ghcr.io/example/sandbox:committed")
    builds = (
        _build(tmp_path=tmp_path, name="c1", image="ghcr.io/example/sandbox:b-one"),
        _build(tmp_path=tmp_path, name="c2", image="ghcr.io/example/sandbox:b-two"),
    )

    entries = sandbox_images(factory=_FACTORY, repo=repo, builds=builds)

    assert entries == (
        SandboxImageEntry(
            repository=repo,
            source=COMMITTED_RUN_CONFIG_SOURCE,
            image="ghcr.io/example/sandbox:committed",
            path=repo.joinpath(*_RESERVED),
        ),
    )


def test_each_executing_build_reports_its_bundled_pin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With no target-local workflow, every executing build contributes its bundled pin."""
    monkeypatch.delenv(_SANDBOX_IMAGE_ENV, raising=False)
    repo = _repo(tmp_path=tmp_path, name="bundled")
    _write_config(repo=repo, dispatcher={"factories": {_FACTORY: {}}})
    builds = (
        _build(tmp_path=tmp_path, name="d1", image="ghcr.io/example/sandbox:one"),
        _build(tmp_path=tmp_path, name="d2", image="ghcr.io/example/sandbox:two"),
    )

    entries = sandbox_images(factory=_FACTORY, repo=repo, builds=builds)

    assert entries == (
        SandboxImageEntry(
            repository=repo,
            source=BUNDLED_RUN_CONFIG_SOURCE,
            build="d1",
            image="ghcr.io/example/sandbox:one",
            path=builds[0].root.joinpath(*_RESERVED),
        ),
        SandboxImageEntry(
            repository=repo,
            source=BUNDLED_RUN_CONFIG_SOURCE,
            build="d2",
            image="ghcr.io/example/sandbox:two",
            path=builds[1].root.joinpath(*_RESERVED),
        ),
    )


def test_the_entry_source_comes_from_the_dispatch_image_source_function(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Changing what `sandbox_image_source` returns changes this output identically."""
    monkeypatch.delenv(_SANDBOX_IMAGE_ENV, raising=False)
    repo = _repo(tmp_path=tmp_path, name="seam")
    _write_config(repo=repo, dispatcher={"factories": {_FACTORY: {}}})

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

    entries = sandbox_images(factory=_FACTORY, repo=repo, builds=())

    assert entries == (
        SandboxImageEntry(
            repository=repo,
            source="patched_source",
            environment_id="patched-env",
            image="patched-image",
        ),
    )
