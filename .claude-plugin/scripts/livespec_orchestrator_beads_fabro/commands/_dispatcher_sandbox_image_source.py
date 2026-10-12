"""WHICH source supplies one dispatch's sandbox image, resolved once.

`SPECIFICATION/contracts.md` section "Sandbox image source" (Scenario 169): a
dispatch whose resolved factory declares a catalog environment MUST launch its
sandbox from the image that environment declares ON THE FACTORY SERVER, and the
launch overlay MUST NOT substitute `dispatcher.fabro_sandbox_image` for it. The
committed key supplies the image only for a dispatch whose factory names no
catalog environment.

WHY THE DECISION IS A MODULE RATHER THAN A CONDITIONAL AT THE REWRITE. It has
TWO consumers that must agree — the overlay, which needs the value to
substitute, and the dispatch-id journal record, which must name the source —
and they sit in different layers. A conditional at the rewrite site would leave
the journal re-deriving the same decision from the same inputs with nothing
holding the two readings together, which is the shape this repository's
resolve-once clause exists to prevent. Keeping it pure is what lets both read
it without either reaching the other's layer.

WHY A CATALOG ENVIRONMENT WINS OUTRIGHT RATHER THAN BY PRECEDENCE ORDER. On a
Petri-era server the environment is a server-managed catalog entry selected
from the run intent's id ALONE, and the image is a property OF that entry; the
host cannot read it, so it has nothing to compare a committed pin against. The
only honest action is therefore to withhold the pin and let the server's own
selection stand. Measured 2026-10-11 on hp-candidate run 01M4PBFW4MP8, the
alternative is not a conflict an operator can see: `inspect` reported
`sandbox.plan.image` at the catalog's `python-agent-v1.93.5` while the started
container ran the pinned `python-agent-v1.92.0`, so the plan named one image
and the container ran the other, and a run record reading the plan reported an
image that never ran.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__: list[str] = [
    "CATALOG_ENVIRONMENT_IMAGE_SOURCE",
    "COMMITTED_KEY_IMAGE_SOURCE",
    "SandboxImageSource",
    "overlay_sandbox_image",
    "sandbox_image_source",
]

# The two source names `contracts.md` section "Sandbox image source" enumerates,
# verbatim. The committed one is spelled as the CONFIGURATION KEY rather than as
# a label, because that is the thing an operator edits when the journal row says
# a launch took its image from there.
CATALOG_ENVIRONMENT_IMAGE_SOURCE = "catalog_environment"
COMMITTED_KEY_IMAGE_SOURCE = "dispatcher.fabro_sandbox_image"


@dataclass(frozen=True, kw_only=True)
class SandboxImageSource:
    """WHERE one launch's sandbox image came from, as the journal records it.

    `environment_id` is populated only on the catalog arm, because only that
    arm has an id to name; the committed key is a single global setting with no
    per-launch identity. The field is still journaled on both arms — an
    explicit null rather than an omission — so "which source supplied this
    image?" is answerable for every launch and not only for the unusual ones.
    """

    source: str
    environment_id: str | None = None


def overlay_sandbox_image(
    *,
    factory_environment: str | None,
    configured_image: str | None,
) -> str | None:
    """The image the launch overlay may substitute; None leaves the config alone.

    `factory_environment` is the catalog environment id the resolved factory
    declares, as `factory_environment_id` projects it off the dispatch's
    already-resolved target — None when that factory names none, which is a
    complete answer rather than an unread one.

    None is returned for a catalog dispatch because None is ALREADY the
    overlay's documented no-op: the committed workflow image table stays
    byte-for-byte as shipped. So this resolution adds no new arm to the
    rewrite; it decides whether the rewrite has anything to do.
    """
    if factory_environment is not None:
        return None
    return configured_image


def sandbox_image_source(*, factory_environment: str | None) -> SandboxImageSource:
    """The source the launch takes its sandbox image from, named for the journal.

    The SAME `factory_environment` the overlay reads, so the row the record
    carries and the substitution the overlay performs cannot disagree: one
    input, one pure resolution, two readings of it.

    The committed arm is reported whether or not `dispatcher.fabro_sandbox_image`
    is actually set, because an unset key is still the source this launch
    CONSULTED — the committed workflow's own image table is what it then falls
    through to, which is that key's documented no-op rather than a third source.
    """
    if factory_environment is None:
        return SandboxImageSource(source=COMMITTED_KEY_IMAGE_SOURCE)
    return SandboxImageSource(
        source=CATALOG_ENVIRONMENT_IMAGE_SOURCE, environment_id=factory_environment
    )
