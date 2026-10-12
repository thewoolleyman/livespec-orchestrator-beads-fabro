"""WHICH source supplies ONE dispatch's sandbox image, decided once.

PURE, and a leaf: it imports nothing from this tree, because its consumers sit
above it. The decision is a VALUE rather than a ladder each consumer re-walks,
because a second derivation of this choice would produce a well-formed answer
on each side with nothing announcing the divergence — which is exactly the
shape the defect this module repairs had: on hp-candidate run 01M4PBFW4MP8 the
run record's `sandbox.plan.image` named the catalog's image while the container
Petri started ran the committed override, so a reader of the plan observed an
image that did not run.

THE CATALOG WINS, AND IT WINS BY THE OVERLAY DECLARING NOTHING. The catalog
lives on the factory server and the Dispatcher reads it at no point, so there
is no image value it could render on the catalog's behalf; the only way a
launch can carry the catalog's image is for the overlay to withhold the image
declaration for that environment entirely. That is why `overlay_image` is None
on the catalog arm and why `catalog_governs` is a question the renderer has to
ask separately: "render no image" and "withhold the committed declaration" are
different acts, and only the second leaves the catalog's image standing.

THE THIRD SOURCE IS NOT A WIDENING. A target that declares no catalog
environment and sets no `dispatcher.fabro_sandbox_image` launches from the
image its committed run config declares, which is a real launch the record must
account for: the clause requires the source to be recorded "for each launch",
so collapsing this case onto either named source would label one launch as
another.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__: list[str] = [
    "CATALOG_ENVIRONMENT_SOURCE",
    "COMMITTED_RUN_CONFIG_IMAGE",
    "COMMITTED_RUN_CONFIG_SOURCE",
    "CONFIGURED_IMAGE_SOURCE",
    "SandboxImageSource",
    "sandbox_image_source",
]

# The three sources, each NAMING what it is rather than ranking it. Two are the
# names the ratified clause enumerates; the third is the committed run config a
# target that declares neither falls back to.
CATALOG_ENVIRONMENT_SOURCE = "catalog_environment"
CONFIGURED_IMAGE_SOURCE = "dispatcher.fabro_sandbox_image"
COMMITTED_RUN_CONFIG_SOURCE = "committed_run_config"


@dataclass(frozen=True, kw_only=True)
class SandboxImageSource:
    """Where ONE dispatch's sandbox image comes from, and what the overlay renders.

    `environment_id` is populated only on the catalog arm, and `overlay_image`
    only on the configured arm, because each field is the evidence of its own
    source: a populated `overlay_image` IS the substitution the clause forbids
    on the catalog arm, and an `environment_id` beside one would describe a
    launch in which both sources acted.
    """

    source: str
    environment_id: str | None
    overlay_image: str | None

    @property
    def catalog_governs(self) -> bool:
        """Whether the factory server's environment catalog supplies the image.

        Asked rather than inferred from `overlay_image is None`, which is also
        true of the committed-run-config arm. The two need opposite handling:
        this one must WITHHOLD the committed image declaration so the catalog's
        stands, and that one must leave it exactly as shipped.
        """
        return self.source == CATALOG_ENVIRONMENT_SOURCE


# The answer for a target that declares no catalog environment and configures no
# image: the committed run config's own declaration stands, untouched. It is the
# DEFAULT every surface here carries, for the same reason `NO_FACTORY_ENVIRONMENT`
# is the factory entry's — a caller that wires nothing renders exactly the config
# it rendered before this decision existed.
COMMITTED_RUN_CONFIG_IMAGE = SandboxImageSource(
    source=COMMITTED_RUN_CONFIG_SOURCE,
    environment_id=None,
    overlay_image=None,
)


def sandbox_image_source(
    *,
    factory_environment: str | None,
    configured_image: str | None,
) -> SandboxImageSource:
    """Decide the sandbox image source from the resolved factory and configuration.

    `factory_environment` is the catalog environment id the resolved factory
    declares, already graded — an unusable declaration is refused before the
    claim, so what reaches here is either a usable id or None. `configured_image`
    is `dispatcher.fabro_sandbox_image` as resolved (the env override first, then
    the committed key), or None when neither is set.

    The catalog is checked FIRST and unconditionally, which is the whole rule: a
    factory naming a catalog environment takes its image from that catalog even
    when `dispatcher.fabro_sandbox_image` is set, because the configured key is a
    repository-wide pin and the catalog is the placement the dispatch was routed
    to.
    """
    if factory_environment is not None:
        return SandboxImageSource(
            source=CATALOG_ENVIRONMENT_SOURCE,
            environment_id=factory_environment,
            overlay_image=None,
        )
    if configured_image is not None:
        return SandboxImageSource(
            source=CONFIGURED_IMAGE_SOURCE,
            environment_id=None,
            overlay_image=configured_image,
        )
    return COMMITTED_RUN_CONFIG_IMAGE
