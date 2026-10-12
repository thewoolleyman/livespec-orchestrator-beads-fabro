"""Rendering the resolved sandbox-image source into the run-config overlay.

`_dispatcher_sandbox_image_source` DECIDES which of the three sources supplies
one dispatch's sandbox image; this module renders that decision into the
submitted config's `[environments.<id>.image]` table. The two are separate
concerns and separate files for that reason — the decision is a pure function of
a target's configuration and its routed factory environment, while this is the
TOML surgery that makes the decision true of the bytes actually submitted.

Only `resolve_sandbox_image` crosses the module boundary. The two helpers below
it are reached from nowhere else and stay private here, because importing a
`_`-prefixed name across modules is what pyright strict's `reportPrivateUsage`
and this repository's `private_calls` check both reject.
"""

from __future__ import annotations

import json

from livespec_orchestrator_beads_fabro.commands._dispatcher_sandbox_image_source import (
    SandboxImageSource,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_toml_read import (
    toml_section_string,
)

__all__: list[str] = [
    "resolve_sandbox_image",
]


def resolve_sandbox_image(
    *,
    text: str,
    environment_id: str,
    sandbox_image: SandboxImageSource,
) -> str | None:
    """Render the resolved sandbox image source into `[environments.<id>.image]`.

    Three arms, one per source, and the catalog's is the one that removes rather
    than writes. On a Petri-era server the run intent's environment id selects
    the catalog environment, but the submitted config's own `environments.<id>`
    overlay still applies on top of that selection — so an image declared here
    overrides the catalog's whatever it says. Suppressing only the configured
    SUBSTITUTION would therefore leave the committed pin overriding the catalog
    instead, which satisfies the clause's prohibition while still breaking its
    requirement; withholding the declaration is what makes the catalog the one
    source (hp-candidate run 01M4PBFW4MP8, work-item bd-ib-jy7fuh).
    """
    section = f"environments.{environment_id}.image"
    if sandbox_image.catalog_governs:
        return _withhold_image_table(text=text, section=section)
    if sandbox_image.overlay_image is None:
        return text
    committed_image = toml_section_string(text=text, section=section, key="docker")
    if committed_image is None:
        return None
    needle = f'docker = "{committed_image}"'
    if needle not in text:
        return None
    return text.replace(needle, f"docker = {json.dumps(sandbox_image.overlay_image)}", 1)


def _withhold_image_table(*, text: str, section: str) -> str:
    """Drop the whole `[<section>]` table so the catalog's image stands.

    The TABLE goes, not just its `docker` key: an `[environments.<id>.image]`
    left declared but empty is a table the engine must still resolve an image
    out of, and an engine refusing that would turn a correct placement into a
    launch failure. Its comment block goes with it, because those comments
    document the pin that is no longer being asserted.

    A committed config declaring NO image table is returned unchanged rather
    than refused. Nothing is competing with the catalog there, so the launch is
    already correct, and a refusal would reject exactly the configuration the
    clause is asking for.
    """
    lines = text.splitlines(keepends=True)
    header = f"[{section}]"
    start = next((index for index, line in enumerate(lines) if line.strip() == header), None)
    if start is None:
        return text
    # The table runs to the next TOML table header (`[x]` or `[[x]]`) or to the
    # end of the file. Keyed on a stripped line that both opens and closes with
    # a bracket so a comment mentioning a table name does not end it early.
    # Taking the range right up to that header carries the table's own trailing
    # blank line away with it, which is what leaves the blank line ABOVE the
    # withheld header separating its neighbours rather than doubled.
    end = start + 1
    while end < len(lines) and not _opens_toml_table(line=lines[end]):
        end += 1
    return "".join(lines[:start] + lines[end:])


def _opens_toml_table(*, line: str) -> bool:
    stripped = line.strip()
    return stripped.startswith("[") and stripped.endswith("]")
