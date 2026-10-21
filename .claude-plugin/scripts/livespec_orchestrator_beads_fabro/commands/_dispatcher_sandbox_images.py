"""ONE repository's sandbox-image entries, decided by dispatch's own resolution.

The read-only answer to "which sandbox image would a dispatch to this factory
pull, right now, for this repository" -- the question the host's image-warm
timer has to answer BEFORE the first run that needs the tag, and which no
existing surface can answer. The dispatch journal cannot: on the
`committed_run_config` arm it writes `sandbox_image` null, deliberately, for
the reason `_dispatcher_sandbox_image_source` records.

EVERY ENTRY IS DECIDED BY THE FUNCTIONS A DISPATCH CALLS, never by a copy of
their ladders: `has_fabro_factory` for the declaration, `resolve_fabro_factory`
plus `factory_environment_id` for the catalog environment,
`resolve_fabro_sandbox_image` for the configured image, `sandbox_image_source`
for which of the three sources governs, and `workflow_toml` for which run
config a dispatch would read. A second derivation would produce a well-formed
answer on each side with nothing announcing the divergence, which is the exact
shape of the defect the image-source decision was extracted to repair -- and
here it would be worse, because the whole point of the enumeration is that the
warm timer and a real dispatch cannot disagree about the tag.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

from returns.unsafe import unsafe_perform_io

from livespec_orchestrator_beads_fabro.commands._config import (
    dispatcher_block,
    has_fabro_factory,
    resolve_fabro_factory,
    resolve_fabro_sandbox_image,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_factory_environment import (
    factory_environment_id,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import workflow_toml
from livespec_orchestrator_beads_fabro.commands._dispatcher_sandbox_image_source import (
    COMMITTED_RUN_CONFIG_SOURCE,
    sandbox_image_source,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_toml_read import toml_section_string
from livespec_orchestrator_beads_fabro.commands._workflow_variants import workflow_registry

__all__: list[str] = [
    "BUNDLED_RUN_CONFIG_SOURCE",
    "FACTORY_UNDECLARED_SOURCE",
    "NAMED_VARIANT_SOURCE",
    "BuildRoot",
    "SandboxImageEntry",
    "sandbox_images",
]

# The three sources this module NAMES itself, beside the three
# `_dispatcher_sandbox_image_source` already owns. Each names what it IS rather
# than ranking it, exactly as the three over there do.
FACTORY_UNDECLARED_SOURCE = "factory_undeclared"
NAMED_VARIANT_SOURCE = "named_variant"
BUNDLED_RUN_CONFIG_SOURCE = "bundled_run_config"

# Where a run config declares the environment whose image table carries the
# docker pin. Read in two steps because the second section NAMES the first's
# value: `[run.environment] id` selects the environment, and that environment's
# own `[environments.<id>.image] docker` is the tag a launch pulls. This is the
# same pair `_dispatcher_overlay` reads to decide which table its own overlay
# rewrites, so the enumeration reports the key a dispatch would actually act on.
_RUN_ENVIRONMENT_SECTION = "run.environment"
_ENVIRONMENT_ID_KEY = "id"
_IMAGE_SECTION_TEMPLATE = "environments.{environment}.image"
_DOCKER_KEY = "docker"


@dataclass(frozen=True, kw_only=True)
class BuildRoot:
    """ONE executing build: the payload root its assets are read from, and its identity."""

    identity: str
    root: Path


@dataclass(frozen=True, kw_only=True)
class SandboxImageEntry:
    """ONE enumerated sandbox-image source, as reported.

    Every field but `repository` and `source` defaults to absent, because each
    one is the EVIDENCE of its own arm: an `environment_id` belongs only to the
    catalog arm, a `variant` only to a named variant, and a `build` only to a
    bundled pin. A field populated on an arm that cannot own it would describe
    a resolution that did not happen.
    """

    repository: Path
    source: str
    environment_id: str | None = None
    image: str | None = None
    path: Path | None = None
    build: str | None = None
    variant: str | None = None


def sandbox_images(
    *, factory: str, repo: Path, builds: tuple[BuildRoot, ...]
) -> tuple[SandboxImageEntry, ...]:
    """Every sandbox-image source a dispatch of `repo` to `factory` can resolve now.

    Reported in the order a dispatch resolves them: the factory declaration
    first, because an undeclared factory has no placement to resolve anything
    against; then the one source `sandbox_image_source` names; and only on its
    `committed_run_config` arm the per-workflow entries, which is the one arm
    where WHICH run config a dispatch reads decides the image.
    """
    if not has_fabro_factory(cwd=repo, factory=factory):
        return (SandboxImageEntry(repository=repo, source=FACTORY_UNDECLARED_SOURCE),)
    source = sandbox_image_source(
        factory_environment=factory_environment_id(
            factory=resolve_fabro_factory(cwd=repo, factory=factory)
        ),
        configured_image=unsafe_perform_io(resolve_fabro_sandbox_image(cwd=repo).unwrap()),
    )
    if source.source != COMMITTED_RUN_CONFIG_SOURCE:
        return (
            SandboxImageEntry(
                repository=repo,
                source=source.source,
                environment_id=source.environment_id,
                image=source.overlay_image,
            ),
        )
    return _workflow_entries(repo=repo, builds=builds)


def _workflow_entries(
    *, repo: Path, builds: tuple[BuildRoot, ...]
) -> tuple[SandboxImageEntry, ...]:
    """Every run config a dispatch within this scope can select, variants first.

    Variants are enumerated in name order rather than in registry order so two
    invocations against one repository print the same array; a JSONC table's
    order is the operator's editing history and says nothing a consumer can use.
    """
    registry = workflow_registry(block=dispatcher_block(cwd=repo))
    entries = [
        _variant_entry(repo=repo, variant=variant, directory=directory)
        for variant, directory in sorted(registry.items())
    ]
    entries.extend(_reserved_entries(repo=repo, builds=builds))
    return tuple(entries)


def _variant_entry(*, repo: Path, variant: str, directory: str) -> SandboxImageEntry:
    path = workflow_toml(args=_resolution_args(repo=repo), variant_directory=directory)
    return SandboxImageEntry(
        repository=repo,
        source=NAMED_VARIANT_SOURCE,
        variant=variant,
        image=_declared_image(path=path),
        path=path,
    )


def _reserved_entries(
    *, repo: Path, builds: tuple[BuildRoot, ...]
) -> tuple[SandboxImageEntry, ...]:
    """The reserved workflow: the target's own copy, else one entry per build.

    The committed-or-bundled choice is not re-decided here — it is read off
    `workflow_toml`'s own answer, by asking it once per build and seeing whether
    the path it returned sits under that build. A target-local copy wins for
    EVERY build, so such a repository has exactly one reserved entry however
    many builds are executing; a target that commits none has one per build,
    because each build's own bundle carries its own pin.
    """
    resolved = tuple(
        (build, workflow_toml(args=_resolution_args(repo=repo), payload_root=build.root))
        for build in builds
    )
    committed = tuple(path for build, path in resolved if not path.is_relative_to(build.root))
    if committed:
        return (
            SandboxImageEntry(
                repository=repo,
                source=COMMITTED_RUN_CONFIG_SOURCE,
                image=_declared_image(path=committed[0]),
                path=committed[0],
            ),
        )
    return tuple(
        SandboxImageEntry(
            repository=repo,
            source=BUNDLED_RUN_CONFIG_SOURCE,
            build=build.identity,
            image=_declared_image(path=path),
            path=path,
        )
        for build, path in resolved
    )


def _resolution_args(*, repo: Path) -> argparse.Namespace:
    """The Namespace `workflow_toml` reads, with no `--workflow` of its own.

    `workflow=None` is the whole scope of this enumeration: the clause excludes
    a dispatch that passes an explicit workflow path, and that exclusion is
    expressed by handing the resolver the same absent flag such a dispatch does
    not have.
    """
    return argparse.Namespace(workflow=None, repo=str(repo))


def _declared_image(*, path: Path) -> str | None:
    text = path.read_text(encoding="utf-8")
    environment = toml_section_string(
        text=text, section=_RUN_ENVIRONMENT_SECTION, key=_ENVIRONMENT_ID_KEY
    )
    return toml_section_string(
        text=text,
        section=_IMAGE_SECTION_TEMPLATE.format(environment=environment),
        key=_DOCKER_KEY,
    )
