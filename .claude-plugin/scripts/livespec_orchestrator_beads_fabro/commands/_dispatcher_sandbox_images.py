"""Read-only inventory of the sandbox images dispatches can resolve."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

from returns.unsafe import unsafe_perform_io

from livespec_orchestrator_beads_fabro.commands._config import (
    resolve_fabro_factory,
    resolve_fabro_sandbox_image,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_factory_environment import (
    factory_environment_id,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import workflow_toml
from livespec_orchestrator_beads_fabro.commands._dispatcher_sandbox_image_source import (
    COMMITTED_RUN_CONFIG_SOURCE,
    SandboxImageSource,
    sandbox_image_source,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_toml_read import toml_section_string

__all__: list[str] = ["BuildRoot", "SandboxImageEntry", "sandbox_images"]

_WORKFLOW_SECTION = "run.environment"
_IMAGE_KEY = "docker"


@dataclass(frozen=True, kw_only=True)
class BuildRoot:
    """One executing dispatcher build awaiting image resolution."""

    repository: Path
    root: Path
    kind: str


@dataclass(frozen=True, kw_only=True)
class SandboxImageEntry:
    """One consumer/build pair and the source its dispatch would use."""

    repository: Path
    build: Path
    build_kind: str
    source: str
    environment_id: str | None
    image: str | None
    path: Path | None

    def record(self) -> dict[str, str | None]:
        """The stable JSON-ready form emitted by the command."""
        return {
            "repository": str(self.repository),
            "build": str(self.build),
            "build_kind": self.build_kind,
            "source": self.source,
            "environment_id": self.environment_id,
            "image": self.image,
            "path": None if self.path is None else str(self.path),
        }


def sandbox_images(*, factory: str, builds: tuple[BuildRoot, ...]) -> tuple[SandboxImageEntry, ...]:
    """Resolve every supplied consumer/build pair through dispatch's own seams."""
    return tuple(_image_for(build=build, factory=factory) for build in builds)


def _image_for(*, build: BuildRoot, factory: str) -> SandboxImageEntry:
    workflow = workflow_toml(
        args=argparse.Namespace(workflow=None, repo=str(build.repository)),
        payload_root=build.root,
    )
    text = workflow.read_text(encoding="utf-8")
    target = resolve_fabro_factory(cwd=build.repository, factory=factory)
    configured = resolve_fabro_sandbox_image(cwd=build.repository)
    source = sandbox_image_source(
        factory_environment=factory_environment_id(factory=target),
        configured_image=unsafe_perform_io(configured.unwrap()),
    )
    return _resolved(build=build, source=source, workflow=workflow, text=text)


def _resolved(
    *, build: BuildRoot, source: SandboxImageSource, workflow: Path, text: str
) -> SandboxImageEntry:
    if source.source != COMMITTED_RUN_CONFIG_SOURCE:
        return SandboxImageEntry(
            repository=build.repository,
            build=build.root,
            build_kind=build.kind,
            source=source.source,
            environment_id=source.environment_id,
            image=source.overlay_image,
            path=None,
        )
    environment = toml_section_string(text=text, section=_WORKFLOW_SECTION, key="id")
    image = toml_section_string(
        text=text, section=f"environments.{environment}.image", key=_IMAGE_KEY
    )
    return SandboxImageEntry(
        repository=build.repository,
        build=build.root,
        build_kind=build.kind,
        source=source.source,
        environment_id=None,
        image=image,
        path=workflow,
    )
